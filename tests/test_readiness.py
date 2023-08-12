import json
import re
from datetime import timedelta
from pathlib import Path

from src.config import Args, CacheFiles, Config, Job
from src.utils import is_job_ready, true_utcnow


def test_is_job_ready_without_last_scans():
    files = CacheFiles(
        last_clean=Path("tests/files/last_clean_blank.json"),
        history=Path("tests/files/history.log"),
    )
    args = Args(debug=False, watch=True, jobs=None, http_logs=False)
    job = Job(
        name="test_job",
        repositories={"repo1", "repo2"},
        tag_regexps={re.compile(r"v\d+\.\d+\.\d+")},
        save_last=2,
        clean_every_n_hours=12,
        older_than_days=3,
    )
    config = Config(
        registry_url="https://example.com/v2",
        username="user",
        password="pass",
        max_concurrent_requests=10,
        proxy=None,
        timeout=20,
        jobs=[job],
        files=files,
        args=args,
    )

    is_ready, next_scan = is_job_ready(job, config)

    assert is_ready is True
    assert next_scan == ""


def test_is_job_ready_with_old_last_scan():
    files = CacheFiles(
        last_clean=Path("tests/files/last_clean.json"),
        history=Path("tests/files/history.log"),
    )
    args = Args(debug=False, watch=True, jobs=None, http_logs=False)
    job = Job(
        name="test_job",
        repositories={"repo1", "repo2"},
        tag_regexps={re.compile(r"v\d+\.\d+\.\d+")},
        save_last=2,
        clean_every_n_hours=12,
        older_than_days=3,
    )
    config = Config(
        registry_url="https://example.com",
        username="user",
        password="pass",
        max_concurrent_requests=10,
        proxy=None,
        timeout=20,
        jobs=[job],
        files=files,
        args=args,
    )

    is_ready, next_scan = is_job_ready(job, config)

    assert is_ready is True
    assert next_scan == ""


def test_is_job_ready_with_recent_last_scan():
    files = CacheFiles(
        last_clean=Path("tests/files/last_clean_recent.json"),
        history=Path("tests/files/history.log"),
    )
    args = Args(debug=False, watch=True, jobs=None, http_logs=False)
    job = Job(
        name="test_job",
        repositories={"repo1", "repo2"},
        tag_regexps={re.compile(r"v\d+\.\d+\.\d+")},
        save_last=2,
        clean_every_n_hours=35,
        older_than_days=3,
    )
    config = Config(
        registry_url="https://example.com",
        username="user",
        password="pass",
        max_concurrent_requests=10,
        proxy=None,
        timeout=20,
        jobs=[job],
        files=files,
        args=args,
    )

    last_scans = {
        "test_job": {
            "job_name": "test_job",
            "finished_at": str(true_utcnow() - timedelta(hours=6)),
            "started_at": str(true_utcnow() - timedelta(hours=6)),
            "success": True,
            "found_tags": [],
            "found_tags_count": 0,
            "repo_stats": [],
            "errors": [],
            "mode": "auto",
        }
    }
    with open(config.files.last_clean, "w") as f:
        json.dump(last_scans, f)

    is_ready, next_scan = is_job_ready(job, config)

    assert is_ready is False
    assert next_scan != ""

    last_scans = {
        "test_job": {
            "job_name": "test_job",
            "finished_at": str(true_utcnow() - timedelta(hours=6)),
            "started_at": str(true_utcnow() - timedelta(hours=6)),
            "success": True,
            "found_tags": [],
            "found_tags_count": 0,
            "repo_stats": [],
            "errors": [],
            "mode": "manual",
        }
    }
    with open(config.files.last_clean, "w") as f:
        json.dump(last_scans, f)

    is_ready, next_scan = is_job_ready(job, config)

    assert is_ready is True
    assert next_scan == ""
