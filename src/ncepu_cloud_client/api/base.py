from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from ncepu_cloud_client.api.models import CloudItem, CloudLibrary, CloudQuota

ProgressCallback = Callable[[int, int], None]


class CloudDriveClient(ABC):
    @abstractmethod
    def login(self) -> None: ...

    @abstractmethod
    def logout(self) -> None: ...

    @abstractmethod
    def refresh_token(self) -> None: ...

    @abstractmethod
    def list_libraries(self) -> list[CloudLibrary]: ...

    @abstractmethod
    def get_quota(self) -> CloudQuota: ...

    @abstractmethod
    def get_doc_lib_quota(self, doc_lib_id: str) -> CloudQuota: ...

    @abstractmethod
    def list_dir(self, remote_path: str | None = None, parent_id: str | None = None) -> list[CloudItem]: ...

    @abstractmethod
    def mkdir(self, remote_path: str) -> CloudItem: ...

    @abstractmethod
    def delete(self, item_id: str) -> None: ...

    @abstractmethod
    def rename(self, item_id: str, new_name: str) -> CloudItem: ...

    @abstractmethod
    def move(self, item_id: str, target_dir_id: str) -> CloudItem: ...

    @abstractmethod
    def copy(self, item_id: str, target_dir_id: str) -> CloudItem: ...

    @abstractmethod
    def upload_file(self, local_path: Path, remote_dir_id: str, remote_name: str | None = None, progress_cb: ProgressCallback | None = None) -> CloudItem: ...

    @abstractmethod
    def download_file(self, item_id: str, local_path: Path, progress_cb: ProgressCallback | None = None) -> Path: ...

    @abstractmethod
    def get_item_by_path(self, remote_path: str) -> CloudItem | None: ...

    @abstractmethod
    def get_item_fields(self, item_id: str, fields: list[str]) -> dict: ...

    @abstractmethod
    def search(self, keyword: str) -> list[CloudItem]: ...
