from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def local_timestamp_compact() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")

