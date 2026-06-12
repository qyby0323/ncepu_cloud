from __future__ import annotations

import os
import sys
from pathlib import Path

from .constants import APP_NAME


def is_windows() -> bool:
    return sys.platform.startswith("win")


def app_config_dir() -> Path:
    override = os.environ.get("NCEPU_CLOUD_CONFIG_DIR")
    if override:
        return Path(override)
    if is_windows():
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return root / APP_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ncepu-cloud-client"


def app_data_dir() -> Path:
    override = os.environ.get("NCEPU_CLOUD_DATA_DIR")
    if override:
        return Path(override)
    if is_windows():
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return root / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "ncepu-cloud-client"


def app_cache_dir() -> Path:
    override = os.environ.get("NCEPU_CLOUD_CACHE_DIR")
    if override:
        return Path(override)
    if is_windows():
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / APP_NAME
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "ncepu-cloud-client"


def config_file() -> Path:
    return app_config_dir() / "config.toml"


def state_db_file() -> Path:
    return app_data_dir() / "state.db"


def token_file() -> Path:
    return app_data_dir() / "tokens.json"


def log_dir() -> Path:
    return app_data_dir() / "logs"


def log_file() -> Path:
    return log_dir() / "app.log"


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path.cwd()))
    candidate = base / relative
    if candidate.exists():
        return candidate
    return Path(__file__).resolve().parents[3] / relative


def ensure_runtime_dirs() -> None:
    for directory in (app_config_dir(), app_data_dir(), app_cache_dir(), log_dir()):
        directory.mkdir(parents=True, exist_ok=True)

