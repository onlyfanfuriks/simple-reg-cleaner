import logging
import os
import re
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ValidationError, field_validator
from yaml import safe_load

CACHE_DIR = Path("cache")
MAX_CONCURRENT_REQUESTS = 20
DEFAULT_TIMEOUT = 20
LOG_FORMAT = "[%(asctime)s] [%(levelname)-8s] |> %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)


class Job(BaseModel):
    name: str
    description: str | None = None
    repositories: set[str]
    tag_regexps: set[re.Pattern]
    save_last: int
    clean_every_n_hours: int
    older_than_days: int

    @field_validator("tag_regexps")
    @classmethod
    def compile_tag_regexps(cls, tag_regexps: list[str]) -> set[re.Pattern]:
        if not tag_regexps:
            logging.critical(
                "In some jobs, there are no tag_regexps. You must provide at least one regexp."
            )
            exit(1)
        return {re.compile(r) for r in tag_regexps}

    @field_validator("repositories")
    @classmethod
    def strip_repository_names(cls, repos: list[str]) -> set[str]:
        if not repos:
            logging.critical(
                "In some jobs, there are no repositories. You must provide at least one repo."
            )
            exit(1)
        return {r.strip() for r in repos}


class CacheFiles(BaseModel):
    last_clean: Path
    history: Path

    @classmethod
    def create(cls) -> "CacheFiles":
        latest = CACHE_DIR / Path("latest_cleanup.json")
        history = CACHE_DIR / Path("history.log")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        latest.touch(exist_ok=True)
        history.touch(exist_ok=True)
        return cls(last_clean=latest, history=history)


class Args(BaseModel):
    debug: bool = False
    watch: bool = False
    jobs: list[str] | None = None
    http_logs: bool = False

    @classmethod
    def from_args(cls) -> "Args":
        parser = ArgumentParser(
            description="Automatic cleaner of old docker images",
            formatter_class=ArgumentDefaultsHelpFormatter,
        )
        parser.add_argument(
            "--debug",
            action="store_true",
            help="The application will generate logs without actually deleting the images",
            required=False,
            default=False,
        )
        parser.add_argument(
            "--watch",
            action="store_true",
            help="Endless operation of the application for auto cleanup. Will be used 'config.yaml'",
            required=False,
            default=False,
        )
        parser.add_argument(
            "--jobs",
            help="List of jobs in `manual.yaml` to run. Example: --jobs clean-dev-tags clean-prod-older-15",
            required=False,
            default=None,
            nargs="+",
        )
        parser.add_argument(
            "--http-logs",
            action="store_true",
            help="Enable http logs for every request",
            required=False,
            default=False,
        )
        args = parser.parse_args()
        if args.jobs and args.watch:
            logging.critical(
                "Args 'watch' and 'jobs' are mutually exclusive. Please use one of them"
            )
            parser.print_help()
            exit(1)

        return cls(
            debug=args.debug,
            watch=args.watch,
            jobs=args.jobs,
            http_logs=args.http_logs,
        )


class Config(BaseModel):
    registry_url: str
    username: str
    password: str
    max_concurrent_requests: int = MAX_CONCURRENT_REQUESTS
    proxy: str | None = None
    timeout: int | None = DEFAULT_TIMEOUT
    jobs: list[Job]
    files: CacheFiles
    args: Args

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Config":
        return Config.model_validate(data)

    @field_validator("username", "password")
    @classmethod
    def handle_env_vars(cls, v: str) -> str:
        if isinstance(v, str) and v.startswith("__ENV:"):
            value = os.environ.get(v[6:].strip(), "")
            if not value:
                logging.critical(
                    "Credentials are not set. Please set them in config.yaml"
                )
                logging.info(
                    "Use '<field>: string' or env vars as '<field>: \"__ENV: <YOUR_VAR_NAME>\"' for username and password"
                )
                exit(1)
            return value
        return v

    @field_validator("registry_url")
    @classmethod
    def set_registry_url(cls, value: str) -> str:
        logging.warning("For API endpoints, will be used '/v2' as path")
        return f"{value.strip('/')}/v2"

    @field_validator("max_concurrent_requests")
    @classmethod
    def set_max_concurrent_requests(cls, value: int) -> int:
        if value <= 0:
            logging.error("Max_concurrent_requests must be greater than 0. Set 10")
            return 10
        return value

    @field_validator("proxy")
    @classmethod
    def set_proxy(cls, value: str) -> str | None:
        if not value:
            return None
        error = "Field proxy must be a valid url: <scheme>://<address>[:port]; Remove value or fix it"
        if value.startswith("__ENV:"):
            value = os.environ.get(value[6:].strip(), "")
            if not value:
                return None

        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            logging.critical(error)
            exit(1)

        return value

    @field_validator("timeout")
    @classmethod
    def set_timeout(cls, value: int) -> int:
        if not value or 0 >= value > 120:
            logging.error("Timeout must be in range 1-120. Set 20")
            return 20
        return value


def get_config_files(args: Args, path: str = "") -> dict[str, str]:
    """Get config file names based on args."""
    path = path if path else "config"
    files = {}
    jobs_filename = "jobs" if args.watch else "manual"

    for ext in ("yml", "yaml"):
        config_file = f"{path}/config.{ext}"
        jobs_file = f"{path}/{jobs_filename}.{ext}"

        if Path(config_file).exists():
            files["config"] = config_file
        if Path(jobs_file).exists():
            files["jobs"] = jobs_file

    if len(files) != 2:
        logging.critical(
            f"Missing config files. Ensure you have config/config.yaml and config/{jobs_filename}.yaml"
        )
        exit(1)

    return files


def load_config(args: Args) -> Config:
    files = get_config_files(args)

    with open(files["config"], "r") as conf_file, open(files["jobs"], "r") as jobs_file:
        config = safe_load(conf_file)
        jobs = safe_load(jobs_file)

    if args.jobs:
        validate_jobs(jobs, args.jobs)

    if args.jobs or not args.watch:
        disable_periodic_clean(jobs)

    try:
        cache_files = CacheFiles.create()
        return Config.from_dict(
            {**config, "jobs": jobs, "args": args, "files": cache_files}
        )
    except ValidationError as e:
        logging.critical(f"Invalid config: {e}")
        exit(1)


def validate_jobs(jobs: list[dict], job_names: list[str]):
    missing = set(job_names) - {j["name"] for j in jobs}
    if missing:
        logging.critical(f"Missing jobs: {missing}")
        exit(1)


def disable_periodic_clean(jobs: list[dict[str, Any]]) -> None:
    for job in jobs:
        logging.info(f"Peroidic cleanup disabled for job {job['name']}")
        job["clean_every_n_hours"] = 0
