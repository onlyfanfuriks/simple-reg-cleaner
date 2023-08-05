import re
from datetime import datetime, timezone

from src.config import Job
from src.models import Tag
from src.utils import exclude_tags, true_utcnow


def test_exclude_tags():
    # Create some example tags
    tag1 = Tag(
        name="tag1",
        repository="repo1",
        deletion_hash="hash1",
        config_hash="hash1",
        creation_date=datetime(1990, 8, 1, tzinfo=timezone.utc),
    )
    tag2 = Tag(
        name="tag2",
        repository="repo1",
        deletion_hash="hash2",
        config_hash="hash2",
        creation_date=datetime(1990, 8, 2, tzinfo=timezone.utc),
    )
    tag3 = Tag(
        name="tag3",
        repository="repo2",
        deletion_hash="hash3",
        config_hash="hash3",
        creation_date=datetime(1990, 8, 1, tzinfo=timezone.utc),
    )
    tag4 = Tag(
        name="tag4",
        repository="repo2",
        deletion_hash="hash4",
        config_hash="hash4",
        creation_date=datetime(1990, 8, 2, tzinfo=timezone.utc),
    )
    tag5 = Tag(
        name="tag5",
        repository="repo2",
        deletion_hash="",
        config_hash="hash5",
        creation_date=datetime(1990, 8, 3, tzinfo=timezone.utc),
    )

    # Create a sample Job
    job = Job(
        name="job1",
        repositories={"repo1", "repo2"},
        tag_regexps={re.compile(r"tag\d")},
        save_last=1,
        clean_every_n_hours=24,
        older_than_days=2,
    )

    tags_all = [tag1, tag2, tag3, tag4, tag5]
    all_to_delete, all_to_save = exclude_tags(job, tags_all)
    assert len(all_to_delete) == 3
    assert len(all_to_save) == 2

    tag5.creation_date = true_utcnow()
    tag5.deletion_hash = "hash5"
    all_to_delete, all_to_save = exclude_tags(job, tags_all)
    assert len(all_to_delete) == 3
    assert len(all_to_save) == 2
