from __future__ import annotations

from pathlib import Path

from ncepu_cloud_client.sync.checksum import sha256_file
from ncepu_cloud_client.utils.file_utils import wait_until_size_stable


class FileService:
    def checksum(self, path: Path) -> str:
        return sha256_file(path)

    def ready_for_upload(self, path: Path) -> bool:
        return wait_until_size_stable(path)

