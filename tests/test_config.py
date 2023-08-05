from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config import (
    Args,
    CacheFiles,
    Config,
    Job,
    disable_periodic_clean,
    get_config_files,
    load_config,
    validate_jobs,
)

sample_config_data = {
    "registry_url": "https://example.com",
    "username": "test_user",
    "password": "test_password",
    "max_concurrent_requests": 10,
    "proxy": "http://proxy.example.com:8080",
    "timeout": 30,
    "jobs": [
        {
            "name": "job1",
            "description": "Job 1 description",
            "repositories": ["repo1", "repo2"],
            "tag_regexps": [r"\d+\.\d+\.\d+"],
            "save_last": 5,
            "clean_every_n_hours": 24,
            "older_than_days": 30,
        },
        {
            "name": "job2",
            "description": "Job 2 description",
            "repositories": ["repo3"],
            "tag_regexps": [r"v\d+\.\d+\.\d+"],
            "save_last": 3,
            "clean_every_n_hours": 0,
            "older_than_days": 60,
        },
    ],
    "files": CacheFiles(
        last_clean=Path("latest_cleanup.json"), history=Path("history.log")
    ),
    "args": Args(debug=False, watch=False, jobs=None, http_logs=False),
}


def test_compile_tag_regexps():
    job_data = {
        "name": "test_job",
        "repositories": ["repo1", "repo2"],
        "tag_regexps": [r"\d+\.\d+"],
        "save_last": 3,
        "clean_every_n_hours": 24,
        "older_than_days": 30,
    }
    job = Job(**job_data)
    assert len(job.tag_regexps) == 1


def test_strip_repository_names():
    job_data = {
        "name": "test_job",
        "repositories": ["  repo1  ", "repo2"],
        "tag_regexps": [r"\d+\.\d+"],
        "save_last": 3,
        "clean_every_n_hours": 24,
        "older_than_days": 30,
    }
    job = Job(**job_data)
    assert len(job.repositories) == 2


def test_validate_jobs():
    jobs_data = [
        {
            "name": "job1",
            "repositories": ["repo1"],
            "tag_regexps": [r"\d+\.\d+"],
            "save_last": 5,
        },
        {
            "name": "job2",
            "repositories": ["repo2"],
            "tag_regexps": [r"v\d+\.\d+"],
            "save_last": 3,
        },
    ]
    job_names = ["job1", "job3"]
    with pytest.raises(SystemExit):
        validate_jobs(jobs_data, job_names)


def test_disable_periodic_clean():
    jobs_data = [
        {
            "name": "job1",
            "repositories": ["repo1"],
            "tag_regexps": [r"\d+\.\d+"],
            "save_last": 5,
            "clean_every_n_hours": 24,
        },
        {
            "name": "job2",
            "repositories": ["repo2"],
            "tag_regexps": [r"v\d+\.\d+"],
            "save_last": 3,
            "clean_every_n_hours": 0,
        },
    ]
    disable_periodic_clean(jobs_data)
    assert jobs_data[0]["clean_every_n_hours"] == 0
    assert jobs_data[1]["clean_every_n_hours"] == 0


def test_load_config():
    args = Args(debug=True, watch=False, jobs=None, http_logs=False)
    with patch("src.config.get_config_files") as mock_get_config_files:
        mock_get_config_files.return_value = {
            "config": "config.yml",
            "jobs": "jobs.yml",
        }
        with patch("builtins.open") as mock_open:
            mock_open.side_effect = [
                StringIO(str(sample_config_data)),
                StringIO(str(sample_config_data["jobs"])),
            ]
            config = load_config(args)
            assert isinstance(config, Config)
            assert config.max_concurrent_requests == 10
            assert config.registry_url == "https://example.com/v2"


def test_get_config_files():
    args = Args(debug=True, watch=False, jobs=None, http_logs=False)
    config_files = get_config_files(args)
    assert config_files == {
        "config": "config/config.yaml",
        "jobs": "config/manual.yaml",
    }
