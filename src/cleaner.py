import asyncio
import logging

import dateutil.parser
import httpx

from src.config import Config, Job
from src.models import CleanupResult, Tag
from src.utils import (
    build_headers,
    exclude_tags,
    filtered_tags,
    make_repo_stats,
    true_utcnow,
)


async def get_tags(
    session: httpx.AsyncClient, repository: str, config: Config
) -> tuple[list[Tag], list[str]]:
    try:
        response = await session.get(f"{config.registry_url}/{repository}/tags/list")
        response.raise_for_status()
        tags = [
            Tag(name=tag, repository=repository)
            for tag in response.json().get("tags", [])
        ]
        if not tags:
            logging.warning(f"No tags found for {repository}")
        return tags, []
    except httpx.HTTPStatusError as err:
        error = f"Error getting tags for {repository}. code: {err.response.status_code}, text: {err.response.text}"
        logging.critical(error)
        return [], [error]
    except Exception as err:
        error = f"Error getting tags for {repository}. Error: {err}"
    logging.critical(error)
    return [], [error]


async def tags_for_all_repos(
    session: httpx.AsyncClient, job: Job, limiter: asyncio.Semaphore, config: Config
) -> tuple[list[Tag], list[str]]:
    errors_total: list[str] = []
    found_tags: list[Tag] = []

    async with limiter:
        all_tasks = [
            asyncio.create_task(get_tags(session, repository, config))
            for repository in job.repositories
        ]

        for task in asyncio.as_completed(all_tasks):
            tags, errors = await task
            errors_total.extend(errors)
            if tags:
                found_tags.extend(filtered_tags(job, tags))

    return found_tags, errors_total


async def update_hashes(
    session: httpx.AsyncClient, tag: Tag, config: Config
) -> list[str]:
    response = await session.get(
        f"{config.registry_url}/{tag.repository}/manifests/{tag.name}"
    )
    if response.status_code != 200:
        error = (
            f"Error getting digest for {tag.repository}:{tag.name}. "
            f"code: {response.status_code}. text: {response.text}"
        )
        logging.error(error)
        return [error]
    deletion_hash = response.headers.get("Docker-Content-Digest", None)
    config_hash = (response.json()).get("config", {}).get("digest", None)
    if not deletion_hash or not config_hash:
        error = (
            f"Error getting digests for {tag.repository}:{tag.name}. "
            f"Invalid response: {response.json()}"
        )
        logging.error(error)
        return [error]

    tag.deletion_hash = deletion_hash
    tag.config_hash = config_hash
    return []


async def update_all_hashes(
    session: httpx.AsyncClient,
    tags: list[Tag],
    limiter: asyncio.Semaphore,
    config: Config,
) -> list[str]:
    errors_total = []
    tag_details_tasks: list[asyncio.Task[list[str]]] = []
    async with limiter:
        for tag in tags:
            tag_details_tasks.append(
                asyncio.create_task(update_hashes(session, tag, config))
            )
        for completed_task in asyncio.as_completed(tag_details_tasks):
            errors_total.extend(await completed_task)
    return errors_total


async def update_timestamp(
    session: httpx.AsyncClient, tag: Tag, config: Config
) -> list[str]:
    response = await session.get(
        f"{config.registry_url}/{tag.repository}/blobs/{tag.config_hash}"
    )
    if response.status_code != 200:
        error = (
            f"Error getting creation time for {tag.repository}:{tag.name}. "
            f"code: {response.status_code}. text: {response.text}"
        )
        logging.error(error)
        return [error]
    data = response.json()
    created = data.get("created")
    if not created:
        error = (
            f"Error getting creation time for {tag.repository}:{tag.name}. "
            f"Invalid response: {data}"
        )
        logging.error(error)
        return [error]
    tag.creation_date = dateutil.parser.parse(created)
    return []


async def update_all_timestamps(
    session: httpx.AsyncClient,
    tags: list[Tag],
    limiter: asyncio.Semaphore,
    config: Config,
) -> list[str]:
    errors_total = []
    tag_details_tasks: list[asyncio.Task[list[str]]] = []
    async with limiter:
        for tag in tags:
            tag_details_tasks.append(
                asyncio.create_task(update_timestamp(session, tag, config))
            )
        for completed_task in asyncio.as_completed(tag_details_tasks):
            errors_total.extend(await completed_task)
    return errors_total


async def delete_tag(session: httpx.AsyncClient, tag: Tag, config: Config) -> list[str]:
    try:
        response = await session.delete(
            f"{config.registry_url}/{tag.repository}/manifests/{tag.deletion_hash}",
        )
        response.raise_for_status()
        return []
    except httpx.HTTPStatusError as err:
        error = (
            f"Error deleting {tag.repository}:{tag.name}. "
            f"code: {err.response.status_code}, text: {err.response.text}"
        )
        logging.error(error)
        return [error]
    except Exception as err:
        error = f"Error deleting {tag.repository}:{tag.name}. {err}"
        logging.error(error)
        return [error]


async def delete_all_tags(
    session: httpx.AsyncClient,
    tags: list[Tag],
    limiter: asyncio.Semaphore,
    config: Config,
) -> list[str]:
    errors_total = []
    tag_deletion_tasks: list[asyncio.Task[list[str]]] = []
    async with limiter:
        for tag in tags:
            tag_deletion_tasks.append(
                asyncio.create_task(delete_tag(session, tag, config))
            )
        for completed_task in asyncio.as_completed(tag_deletion_tasks):
            errors_total.extend(await completed_task)
    return errors_total


async def cleanup_registry(job: Job, config: Config) -> CleanupResult:
    started_at = true_utcnow()
    errors_total: list[str] = []
    success = True

    max_concurrent_requests = config.max_concurrent_requests
    max_keepalive_connections = (max_concurrent_requests // 2) or 1

    try:
        async with httpx.AsyncClient(
            headers=build_headers(config),
            timeout=config.timeout,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=max_concurrent_requests,
                max_keepalive_connections=max_keepalive_connections,
            ),
            proxies=config.proxy,
            trust_env=False,
        ) as session:
            limiter = asyncio.Semaphore(max_concurrent_requests)
            found_tags, errors_total = await tags_for_all_repos(
                session, job, limiter, config
            )

            if not found_tags and errors_total:
                success = False

            errors_total.extend(
                await update_all_hashes(session, found_tags, limiter, config)
            )
            errors_total.extend(
                await update_all_timestamps(session, found_tags, limiter, config)
            )

            grouped_tags_by_repo: dict[str, list[Tag]] = {}
            for tag in found_tags:
                grouped_tags_by_repo.setdefault(tag.repository, []).append(tag)

            repo_stats = []
            all_to_delete = []
            for repository, tags in grouped_tags_by_repo.items():
                to_delete, to_save = exclude_tags(job, tags)
                all_to_delete.extend(to_delete)
                repo_stats.append(make_repo_stats(repository, to_delete, to_save))

            if not config.args.debug:
                errors_total.extend(
                    await delete_all_tags(session, all_to_delete, limiter, config)
                )

        return CleanupResult(
            job_name=job.name,
            started_at=started_at,
            finished_at=true_utcnow(),
            errors=errors_total,
            success=success,
            found_tags=[{tag.name: tag.creation_date} for tag in found_tags],
            found_tags_count=len(found_tags),
            repo_stats=repo_stats,
        )
    except Exception as err:
        logging.critical(f"Error when clearing the registry. Info: {err}")
        logging.info("Check your configuration, urls, proxies and try again.")
        exit(1)
