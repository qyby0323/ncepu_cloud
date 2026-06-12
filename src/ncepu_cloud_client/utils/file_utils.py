from __future__ import annotations

import os
import time
from pathlib import Path


def human_size(size: int | None) -> str:
    if size is None:
        return "-"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def wait_until_size_stable(path: Path, checks: int = 3, interval: float = 0.5) -> bool:
    if not path.exists() or not path.is_file():
        return False
    last = -1
    stable = 0
    while stable < checks:
        try:
            current = os.path.getsize(path)
        except OSError:
            return False
        if current == last:
            stable += 1
        else:
            stable = 0
            last = current
        time.sleep(interval)
    return True

