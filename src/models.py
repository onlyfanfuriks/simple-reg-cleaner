from datetime import datetime

from pydantic import BaseModel
from enum import StrEnum


class WorkMode(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"


class RepositoryInfo(BaseModel):
    name: str
    tags_total_count: int
    tags_to_delete: list[dict[str, datetime | None]]
    tags_to_delete_count: int
    tags_saved: list[dict[str, datetime | None]]
    tags_saved_count: int


class CleanupResult(BaseModel):
    job_name: str
    mode: WorkMode
    started_at: datetime
    finished_at: datetime
    success: bool
    errors: list[str]
    found_tags: list[dict[str, datetime | None]]
    found_tags_count: int
    repo_stats: list[RepositoryInfo]


class Tag(BaseModel):
    repository: str
    name: str
    deletion_hash: str = ""
    config_hash: str = ""
    creation_date: datetime | None = None
