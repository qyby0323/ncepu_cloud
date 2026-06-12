from __future__ import annotations

import stat
import tempfile
import time
from pathlib import Path

from ncepu_cloud_client.api.base import CloudDriveClient
from ncepu_cloud_client.api.models import CloudItem


class ReadOnlyFusePrototype:
    """Read-only virtual filesystem core backed by a cloud client.

    The main desktop executable deliberately does not import fusepy. This
    class exposes the same small operation set a fusepy wrapper would call,
    so it can be demonstrated and unit-tested without requiring system FUSE
    components to be installed.
    """

    supported_operations = ["getattr", "readdir", "open", "read", "release"]

    def __init__(self, client: CloudDriveClient, cache_dir: Path | None = None):
        self.client = client
        self.cache_dir = cache_dir or Path(tempfile.gettempdir()) / "ncepu-cloud-client-fuse"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._handles: dict[int, Path] = {}
        self._next_handle = 1

    def getattr(self, path: str) -> dict[str, int | float]:
        remote_path = self._normalize(path)
        if remote_path == "/":
            return self._dir_attr()
        item = self._item(remote_path)
        if item.is_dir:
            return self._dir_attr()
        return self._file_attr(item)

    def readdir(self, path: str) -> list[str]:
        remote_path = self._normalize(path)
        items = self.client.list_dir(remote_path=remote_path)
        return [".", "..", *[item.name for item in items if item.name]]

    def open(self, path: str) -> int:
        item = self._item(self._normalize(path))
        if item.is_dir:
            raise IsADirectoryError(path)
        cache_path = self.cache_dir / self._cache_name(item)
        self.client.download_file(item.id, cache_path)
        handle = self._next_handle
        self._next_handle += 1
        self._handles[handle] = cache_path
        return handle

    def read(self, path: str, size: int, offset: int, handle: int) -> bytes:
        cache_path = self._handles.get(handle)
        if cache_path is None:
            raise ValueError(f"无效的文件句柄: {handle}")
        with cache_path.open("rb") as fh:
            fh.seek(offset)
            return fh.read(size)

    def release(self, path: str, handle: int) -> None:
        self._handles.pop(handle, None)

    def mount(self) -> None:
        raise RuntimeError("FUSE 原型需要单独安装 fusepy 和系统 FUSE 组件。")

    def _item(self, remote_path: str) -> CloudItem:
        item = self.client.get_item_by_path(remote_path)
        if item is None:
            raise FileNotFoundError(remote_path)
        return item

    @staticmethod
    def _normalize(path: str) -> str:
        path = path.replace("\\", "/")
        if not path or path == ".":
            return "/"
        if not path.startswith("/"):
            path = f"/{path}"
        while "//" in path:
            path = path.replace("//", "/")
        return path.rstrip("/") or "/"

    @staticmethod
    def _dir_attr() -> dict[str, int | float]:
        return {"st_mode": stat.S_IFDIR | 0o555, "st_nlink": 2, "st_size": 0, "st_mtime": time.time()}

    @staticmethod
    def _file_attr(item: CloudItem) -> dict[str, int | float]:
        return {"st_mode": stat.S_IFREG | 0o444, "st_nlink": 1, "st_size": int(item.size or 0), "st_mtime": time.time()}

    @staticmethod
    def _cache_name(item: CloudItem) -> str:
        safe_id = "".join(char if char.isalnum() else "_" for char in item.id) or "item"
        safe_name = "".join(char if char not in '<>:"/\\|?*' else "_" for char in item.name) or "file"
        return f"{safe_id}-{safe_name}"
