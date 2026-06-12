from __future__ import annotations

import tomllib
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar

from ncepu_cloud_client.app.constants import DEFAULT_AUTH_URL, DEFAULT_BASE_URL, LEGACY_AUTH_URL, LEGACY_BASE_URL
from ncepu_cloud_client.app.paths import config_file, ensure_runtime_dirs
from ncepu_cloud_client.config.settings import (
    ApiSettings,
    AppSettings,
    ProxySettings,
    SecuritySettings,
    Settings,
    SyncSettings,
)

T = TypeVar("T")


class ConfigManager:
    """Create, load and save TOML configuration."""

    def __init__(self, path: Path | None = None):
        self.path = path or config_file()

    def ensure_exists(self) -> None:
        ensure_runtime_dirs()
        if not self.path.exists():
            self.save(Settings())

    def load(self) -> Settings:
        self.ensure_exists()
        with self.path.open("rb") as fh:
            raw = tomllib.load(fh)
        settings = Settings(
            app=self._section(AppSettings, raw.get("app", {})),
            api=self._section(ApiSettings, raw.get("api", {})),
            proxy=self._section(ProxySettings, raw.get("proxy", {})),
            sync=self._section(SyncSettings, raw.get("sync", {})),
            security=self._section(SecuritySettings, raw.get("security", {})),
        )
        migrated = self._migrate_legacy_ncepu_domain(settings)
        migrated = self._migrate_legacy_oauth_prompt(settings) or migrated
        if migrated:
            self.save(settings)
        return settings

    def save(self, settings: Settings) -> None:
        ensure_runtime_dirs()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(self._to_toml(asdict(settings)), encoding="utf-8")

    def update(self, **sections: Any) -> Settings:
        settings = self.load()
        for name, values in sections.items():
            target = getattr(settings, name)
            for key, value in values.items():
                if hasattr(target, key):
                    setattr(target, key, value)
        self.save(settings)
        return settings

    @staticmethod
    def _migrate_legacy_ncepu_domain(settings: Settings) -> bool:
        migrated = False
        if settings.api.base_url.rstrip("/") == LEGACY_BASE_URL:
            settings.api.base_url = DEFAULT_BASE_URL
            migrated = True
        if settings.api.auth_url.rstrip("/") == LEGACY_AUTH_URL:
            settings.api.auth_url = DEFAULT_AUTH_URL
            migrated = True
        return migrated

    @staticmethod
    def _migrate_legacy_oauth_prompt(settings: Settings) -> bool:
        if settings.api.extra_oauth_params.get("prompt") != "login":
            return False
        settings.api.extra_oauth_params.pop("prompt", None)
        return True

    @staticmethod
    def _section(cls: type[T], raw: dict[str, Any]) -> T:
        allowed = {field.name for field in fields(cls)}
        data = {key: value for key, value in raw.items() if key in allowed}
        return cls(**data)

    @staticmethod
    def _to_toml(data: dict[str, Any]) -> str:
        lines: list[str] = []
        for section, values in data.items():
            lines.append(f"[{section}]")
            for key, value in values.items():
                lines.append(f"{key} = {ConfigManager._format_value(value)}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _format_value(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, dict):
            parts = ", ".join(f"{ConfigManager._quote(str(k))} = {ConfigManager._quote(str(v))}" for k, v in value.items())
            return "{ " + parts + " }"
        return ConfigManager._quote(str(value))

    @staticmethod
    def _quote(value: str) -> str:
        escaped = (
            value.replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
            .replace('"', '\\"')
        )
        return '"' + escaped + '"'
