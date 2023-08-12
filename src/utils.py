import asyncio
import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from logging import LogRecord
from pathlib import Path
import re

from pydantic import ValidationError

from src.config import LOG_FORMAT, Config, Job
from src.models import CleanupResult, RepositoryInfo, Tag, WorkMode
import sys


class Colors(StrEnum):
    RED = "\033[31m"
    CRED = "\033[91m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    RESET = "\033[0m"


class ColoredFormatter(logging.Formatter):
    def __init__(self, fmt: str | None = None, *args, **kwargs) -> None:
        self.format_ = fmt
        self.FORMATS = {
            logging.WARNING: f"{Colors.YELLOW}{self.format_}{Colors.RESET}",
            logging.ERROR: f"{Colors.RED}{self.format_}{Colors.RESET}",
            logging.CRITICAL: f"{Colors.CRED}{self.format_}{Colors.RESET}",
        }
        super().__init__(fmt, *args, **kwargs)

    def format(self, record: LogRecord) -> str:
        log_fmt = self.FORMATS.get(record.levelno, self.format_)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def init_logger(config: Config) -> None:
    Path("logs").mkdir(parents=True, exist_ok=True)
    path: Path | None = None
    if not config.args.http_logs:
        logging.getLogger("httpx").disabled = True

    path = path or Path("logs/cleaner.log")
    file_handler = logging.FileHandler(path)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(ColoredFormatter(LOG_FORMAT))
    logging.basicConfig(
        level=logging.INFO, handlers=[file_handler, stream_handler], force=True
    )


async def write_history(msg: str, config: Config) -> None:
    async with asyncio.Lock():
        with open(config.files.history, "a") as f:
            f.write(f"[{datetime.now(tz=timezone.utc)}] {msg}\n")


async def update_latest_cleanup(results: CleanupResult, config: Config) -> None:
    info = {}
    async with asyncio.Lock():
        with open(config.files.last_clean, "r") as f:
            try:
                info = json.load(f)
            except Exception as err:
                logging.warning(
                    f"An error occurred while parsing the latest report: {err}. Seems it was blank"
                )
        with open(config.files.last_clean, "w") as f:
            info[results.job_name] = results.model_dump()
            json.dump(info, f, indent=4, default=str)


def hours_and_minutes_until_next_scan(
    previous_scan_time: datetime, scan_interval_hours: int
) -> str:
    next_scan_time = previous_scan_time + timedelta(hours=scan_interval_hours)
    time_difference = next_scan_time - true_utcnow()
    total_seconds = time_difference.total_seconds()
    hours_until_scan = int(total_seconds // 3600)
    minutes_until_scan = int((total_seconds % 3600) // 60)
    return f"{hours_until_scan} h. {minutes_until_scan} min."


def is_job_ready(job: Job, config: Config) -> tuple[bool, str]:
    report: CleanupResult | None = None
    with open(config.files.last_clean, "r") as f:
        try:
            if last_scans := json.load(f):
                last_scan = last_scans.get(job.name, {})
                if not last_scan:
                    return True, ""
                report = CleanupResult(**last_scan)
                if report.mode == WorkMode.MANUAL:
                    return True, ""
            if not report:
                return True, ""
        except (json.decoder.JSONDecodeError, IndexError):
            return True, ""
        except ValidationError as err:
            logging.error(f"An error occurred while parsing the latest report: {err}")
            return True, ""
    if (
        report.finished_at + timedelta(hours=job.clean_every_n_hours)
    ) <= true_utcnow() or not report.success:
        return True, ""
    return False, hours_and_minutes_until_next_scan(
        report.finished_at, job.clean_every_n_hours
    )


def build_headers(config: Config) -> dict[str, str]:
    basic_auth = base64.standard_b64encode(
        f"{config.username}:{config.password}".encode()
    ).decode()
    return {
        "Accept": "application/vnd.docker.distribution.manifest.v2+json",
        "User-Agent": "Registry cleaner",
        "Docker-Distribution-API-Version": "registry/2.0",
        "Authorization": f"Basic {basic_auth}",
    }


def true_utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def filtered_tags(job: Job, tags: list[Tag]) -> list[Tag]:
    res = []
    for tag in tags:
        for rule in job.tag_regexps:
            if rule.match(tag.name):
                res.append(tag)
                break
    return res


def group_by_rules(job: Job, tags: list[Tag]) -> list[list[Tag]]:
    groups = []
    for rule in job.tag_regexps:
        groups.append([tag for tag in tags if rule.match(tag.name)])
    return groups


def exclude_tags(job: Job, tags_all: list[Tag]) -> tuple[list[Tag], list[Tag]]:
    all_to_delete: list[Tag] = []
    all_to_save: list[Tag] = []

    for tags in group_by_rules(job, tags_all):
        to_delete = sorted(
            list(
                tag
                for tag in tags
                if tag.deletion_hash
                and tag.config_hash
                and tag.creation_date
                and (tag.creation_date + timedelta(days=job.older_than_days))
                <= true_utcnow()
            ),
            key=lambda tag: tag.creation_date,  # type: ignore
            reverse=True,
        )[job.save_last :]
        all_to_delete.extend(to_delete)
        all_to_save.extend([tag for tag in tags if tag not in to_delete])

    return all_to_delete, all_to_save


def unfold_repository_regexps(all_repositories: list[str], job: Job) -> None:
    found_repos: list[str] = []
    for repository in job.repositories:
        rule = repository
        if rule.startswith("r/") and rule.endswith("/"):
            rule = re.compile(rule.replace("r/", "").replace("/", ""))
            for repository in all_repositories:
                if rule.match(repository):
                    found_repos.append(repository)
            continue

        if rule in all_repositories:
            found_repos.append(rule)
    logging.info(f"Found repositories: {' '.join(found_repos)}")
    job.repositories = set(found_repos)


def check_job_names(config: Config) -> None:
    names = []
    for job in config.jobs:
        names.append(job.name)
    if list(set(names)) != [job.name for job in config.jobs]:
        logging.critical("Job names must be unique")
        sys.exit(1)

def make_repo_stats(
    repository: str, to_delete: list[Tag], to_save: list[Tag]
) -> RepositoryInfo:
    return RepositoryInfo(
        name=repository,
        tags_total_count=len(to_delete) + len(to_save),
        tags_to_delete=[{tag.name: tag.creation_date} for tag in to_delete],
        tags_to_delete_count=len(to_delete),
        tags_saved=[{tag.name: tag.creation_date} for tag in to_save],
        tags_saved_count=len(to_save),
    )
