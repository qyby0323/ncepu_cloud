from __future__ import annotations

from pathlib import Path

from ncepu_cloud_client.utils.time_utils import local_timestamp_compact


def conflict_copy_path(path: Path) -> Path:
    suffix = path.suffix
    stem = path.stem
    timestamp = local_timestamp_compact()
    candidate = path.with_name(f"{stem}.conflict-{timestamp}{suffix}")
    if not candidate.exists():
        return candidate
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}.conflict-{timestamp}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"无法为冲突文件生成唯一副本路径: {path}")
