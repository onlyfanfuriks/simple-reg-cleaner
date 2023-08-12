import re
from src.config import Job
from src.utils import unfold_repository_regexps


def test_unfold_repository_regexps_no_regex():
    all_repositories = ["repo1", "repo2", "repo3"]
    job = Job(
        name="test",
        description="Test job",
        repositories={"repo1", "repo3"},
        tag_regexps={re.compile(r"\d+")},
        save_last=5,
        clean_every_n_hours=24,
        older_than_days=7,
    )

    unfold_repository_regexps(all_repositories, job)

    assert job.repositories == {"repo1", "repo3"}


def test_unfold_repository_regexps_with_regex():
    all_repositories = ["repo1", "repo2", "repo333", "repof"]
    job = Job(
        name="test",
        description="Test job",
        repositories={"r/repo\\d+/"},
        tag_regexps={re.compile(r"\d+")},
        save_last=5,
        clean_every_n_hours=24,
        older_than_days=7,
    )

    unfold_repository_regexps(all_repositories, job)

    assert job.repositories == {"repo1", "repo2", "repo333"}
