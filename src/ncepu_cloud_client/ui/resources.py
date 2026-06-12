from __future__ import annotations

from pathlib import Path

from ncepu_cloud_client.app.paths import resource_path


def asset_path(name: str) -> Path:
    return resource_path(f"assets/{name}")


def app_icon_path() -> Path:
    image_icon = resource_path("image/图标.png")
    if image_icon.exists():
        return image_icon
    png_icon = asset_path("app.png")
    if png_icon.exists():
        return png_icon
    return asset_path("app.ico")


def qss_path(theme: str) -> Path:
    return resource_path(f"assets/qss/{theme}.qss")
