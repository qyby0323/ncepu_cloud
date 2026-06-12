from __future__ import annotations

from pathlib import Path

from ncepu_cloud_client.api.base import CloudDriveClient, ProgressCallback
from ncepu_cloud_client.api.models import CloudItem, CloudLibrary, CloudQuota


class CloudService:
    """Thin service facade around CloudDriveClient."""

    def __init__(self, client: CloudDriveClient):
        self.client = client

    def login(self) -> None:
        self.client.login()

    def logout(self) -> None:
        self.client.logout()

    def quota(self) -> CloudQuota:
        return self.client.get_quota()

    def doc_lib_quota(self, doc_lib_id: str) -> CloudQuota:
        return self.client.get_doc_lib_quota(doc_lib_id)

    def libraries(self) -> list[CloudLibrary]:
        return self.client.list_libraries()

    def list_dir(self, remote_path: str | None = None, parent_id: str | None = None) -> list[CloudItem]:
        return self.client.list_dir(remote_path=remote_path, parent_id=parent_id)

    def mkdir(self, remote_path: str) -> CloudItem:
        return self.client.mkdir(remote_path)

    def upload(self, local_path: Path, remote_dir_id: str, name: str | None = None, progress_cb: ProgressCallback | None = None) -> CloudItem:
        return self.client.upload_file(local_path, remote_dir_id, name, progress_cb)

    def download(self, item_id: str, local_path: Path, progress_cb: ProgressCallback | None = None) -> Path:
        return self.client.download_file(item_id, local_path, progress_cb)

    def delete(self, item_id: str) -> None:
        self.client.delete(item_id)

    def rename(self, item_id: str, new_name: str) -> CloudItem:
        return self.client.rename(item_id, new_name)

    def search(self, keyword: str) -> list[CloudItem]:
        return self.client.search(keyword)
