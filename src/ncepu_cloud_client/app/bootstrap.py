from __future__ import annotations

from ncepu_cloud_client.api.aishu_client import AishuCloudClient
from ncepu_cloud_client.api.base import CloudDriveClient
from ncepu_cloud_client.api.mock_client import MockCloudClient
from ncepu_cloud_client.config.config_manager import ConfigManager
from ncepu_cloud_client.config.settings import Settings
from ncepu_cloud_client.utils.logger import setup_logging


def load_settings() -> Settings:
    return ConfigManager().load()


def build_client(settings: Settings | None = None) -> CloudDriveClient:
    settings = settings or load_settings()
    if settings.app.mode == "mock":
        return MockCloudClient()
    return AishuCloudClient(settings)


def bootstrap() -> tuple[Settings, CloudDriveClient]:
    setup_logging()
    settings = load_settings()
    return settings, build_client(settings)

