import asyncio
import logging

from src.cleaner import cleanup_registry
from src.config import Args, Config, load_config
from src.models import CleanupResult
from src.utils import init_logger, is_job_ready, update_latest_cleanup, write_history


async def perform_cleanup(config: Config) -> None:
    tasks: list[asyncio.Task[CleanupResult]] = []
    for job in config.jobs:
        ready, next_cleanup_in = is_job_ready(job, config)
        if not ready:
            skip = f"Skipping job '{job.name}', next cleanup in {next_cleanup_in}"
            await write_history(skip, config)
            logging.warning(skip)
            continue
        started = f"Started job '{job.name}'"
        await write_history(started, config)
        logging.info(started)
        tasks.append(asyncio.create_task(cleanup_registry(job, config)))

    for completed_task in asyncio.as_completed(tasks):
        res = await completed_task
        await update_latest_cleanup(res, config)
        finish = f"Finished '{res.job_name}' with {len(res.errors)} errors"
        await write_history(finish, config)
        logging.info(finish)


async def main(config) -> None:
    while True:
        await perform_cleanup(config)
        await asyncio.sleep(60 * 15)


if __name__ == "__main__":
    args = Args.from_args()
    config = load_config(args)
    init_logger(config)
    if config.args.debug:
        logging.warning("Running in debug mode, found tags will not be deleted")
    loop = asyncio.get_event_loop()
    try:
        if not config.args.watch:
            logging.warning("Running in manual mode; One-time cleanup")
            loop.run_until_complete(perform_cleanup(config))
        else:
            asyncio.ensure_future(main(config))
            loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
