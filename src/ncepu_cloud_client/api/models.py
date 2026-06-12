from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class CloudItemType(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"
    UNKNOWN = "unknown"


@dataclass
class CloudItem:
    id: str
    name: str
    type: CloudItemType = CloudItemType.UNKNOWN
    size: int | None = None
    path: str | None = None
    parent_id: str | None = None
    modified_at: str | None = None
    raw: dict[str, Any] | None = None

    @property
    def is_dir(self) -> bool:
        return self.type == CloudItemType.DIRECTORY


@dataclass
class CloudQuota:
    total: int
    used: int
    raw: dict[str, Any] | None = None

    @property
    def available(self) -> int:
        return max(self.total - self.used, 0)

    @property
    def percent(self) -> float:
        return 0.0 if self.total <= 0 else min(self.used / self.total, 1.0)


@dataclass
class CloudLibrary:
    id: str
    name: str
    owner: str | None = None
    raw: dict[str, Any] | None = None


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str = ""
    expires_at: float | None = None
    token_type: str = "Bearer"

