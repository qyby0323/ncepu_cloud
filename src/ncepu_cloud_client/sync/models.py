from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class SyncDirection(str, Enum):
    LOCAL_TO_REMOTE = "local_to_remote"
    REMOTE_TO_LOCAL = "remote_to_local"
    BIDIRECTIONAL = "bidirectional"


class SyncJobType(str, Enum):
    UPLOAD = "UPLOAD"
    DOWNLOAD = "DOWNLOAD"
    DELETE_LOCAL = "DELETE_LOCAL"
    DELETE_REMOTE = "DELETE_REMOTE"
    MKDIR_REMOTE = "MKDIR_REMOTE"
    RENAME_REMOTE = "RENAME_REMOTE"
    CONFLICT_RESOLVE = "CONFLICT_RESOLVE"


class TransferStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class SyncJob:
    job_type: SyncJobType
    sync_task_id: int
    local_path: Path | None = None
    remote_id: str | None = None
    remote_path: str | None = None
    remote_dir_id: str | None = None
    remote_name: str | None = None
