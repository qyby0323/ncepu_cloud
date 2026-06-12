from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path

from ncepu_cloud_client.api.base import CloudDriveClient, ProgressCallback
from ncepu_cloud_client.api.models import CloudItem, CloudItemType, CloudLibrary, CloudQuota


class MockCloudClient(CloudDriveClient):
    """In-memory cloud adapter for tests and no-network demos."""

    def __init__(self):
        self.logged_in = False
        self.items: dict[str, CloudItem] = {
            "root": CloudItem(id="root", name="全部文件", type=CloudItemType.DIRECTORY, path="/")
        }
        self.children: dict[str, list[str]] = {"root": []}
        self.contents: dict[str, bytes] = {}

    def login(self) -> None:
        self.logged_in = True

    def logout(self) -> None:
        self.logged_in = False

    def refresh_token(self) -> None:
        self.logged_in = True

    def list_libraries(self) -> list[CloudLibrary]:
        return [CloudLibrary(id="personal", name="个人云盘", owner="mock")]

    def get_quota(self) -> CloudQuota:
        used = sum(len(data) for data in self.contents.values())
        return CloudQuota(total=100 * 1024 * 1024 * 1024, used=used)

    def get_doc_lib_quota(self, doc_lib_id: str) -> CloudQuota:
        return self.get_quota()

    def list_dir(self, remote_path: str | None = None, parent_id: str | None = None) -> list[CloudItem]:
        parent = parent_id or self._path_to_id(remote_path or "/") or "root"
        return [self.items[item_id] for item_id in self.children.get(parent, [])]

    def mkdir(self, remote_path: str) -> CloudItem:
        parent_path, name = str(Path(remote_path).parent).replace("\\", "/"), Path(remote_path).name
        if parent_path == ".":
            parent_path = "/"
        parent_id = self._path_to_id(parent_path) or "root"
        item = CloudItem(id=str(uuid.uuid4()), name=name, type=CloudItemType.DIRECTORY, path=remote_path, parent_id=parent_id)
        self.items[item.id] = item
        self.children[item.id] = []
        self.children.setdefault(parent_id, []).append(item.id)
        return item

    def delete(self, item_id: str) -> None:
        item = self.items.pop(item_id, None)
        if item and item.parent_id in self.children:
            self.children[item.parent_id] = [child for child in self.children[item.parent_id] if child != item_id]
        self.children.pop(item_id, None)
        self.contents.pop(item_id, None)

    def rename(self, item_id: str, new_name: str) -> CloudItem:
        item = self.items[item_id]
        item.name = new_name
        if item.path:
            parent = str(Path(item.path).parent).replace("\\", "/")
            item.path = f"{'' if parent == '/' else parent}/{new_name}"
        return item

    def move(self, item_id: str, target_dir_id: str) -> CloudItem:
        item = self.items[item_id]
        if item.parent_id in self.children:
            self.children[item.parent_id] = [child for child in self.children[item.parent_id] if child != item_id]
        self.children.setdefault(target_dir_id, []).append(item_id)
        item.parent_id = target_dir_id
        item.path = self._child_path(target_dir_id, item.name)
        return item

    def copy(self, item_id: str, target_dir_id: str) -> CloudItem:
        source = self.items[item_id]
        item = CloudItem(
            id=str(uuid.uuid4()),
            name=source.name,
            type=source.type,
            size=source.size,
            path=self._child_path(target_dir_id, source.name),
            parent_id=target_dir_id,
            modified_at=source.modified_at,
        )
        self.items[item.id] = item
        self.children.setdefault(target_dir_id, []).append(item.id)
        if source.id in self.contents:
            self.contents[item.id] = self.contents[source.id]
        return item

    def upload_file(self, local_path: Path, remote_dir_id: str, remote_name: str | None = None, progress_cb: ProgressCallback | None = None) -> CloudItem:
        data = local_path.read_bytes()
        if progress_cb:
            progress_cb(0, len(data))
            progress_cb(len(data), len(data))
        name = remote_name or local_path.name
        item = CloudItem(
            id=str(uuid.uuid4()),
            name=name,
            type=CloudItemType.FILE,
            size=len(data),
            path=self._child_path(remote_dir_id, name),
            parent_id=remote_dir_id,
            modified_at=str(time.time()),
        )
        self.items[item.id] = item
        self.children.setdefault(remote_dir_id, []).append(item.id)
        self.contents[item.id] = data
        return item

    def download_file(self, item_id: str, local_path: Path, progress_cb: ProgressCallback | None = None) -> Path:
        data = self.contents[item_id]
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        if progress_cb:
            progress_cb(len(data), len(data))
        return local_path

    def get_item_by_path(self, remote_path: str) -> CloudItem | None:
        item_id = self._path_to_id(remote_path)
        return self.items[item_id] if item_id else None

    def get_item_fields(self, item_id: str, fields: list[str]) -> dict:
        item = self.items[item_id]
        data = item.__dict__
        return {field: data.get(field) for field in fields}

    def search(self, keyword: str) -> list[CloudItem]:
        return [item for item in self.items.values() if keyword.lower() in item.name.lower()]

    def _path_to_id(self, remote_path: str) -> str | None:
        normalized = "/" if remote_path in ("", ".") else remote_path.replace("\\", "/")
        for item_id, item in self.items.items():
            if item.path == normalized:
                return item_id
        return None

    def _child_path(self, parent_id: str, name: str) -> str:
        parent = self.items.get(parent_id)
        parent_path = parent.path if parent and parent.path else "/"
        return f"{parent_path.rstrip('/')}/{name}" if parent_path != "/" else f"/{name}"
