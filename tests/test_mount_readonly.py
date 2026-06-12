import stat
from pathlib import Path

import pytest

from ncepu_cloud_client.api.models import CloudItem, CloudItemType
from ncepu_cloud_client.mount.fuse_readonly import ReadOnlyFusePrototype


class FakeCloudForMount:
    def __init__(self):
        self.items = {
            "/docs": CloudItem(id="dir-1", name="docs", type=CloudItemType.DIRECTORY, path="/docs"),
            "/docs/report.txt": CloudItem(id="file-1", name="report.txt", type=CloudItemType.FILE, size=11, path="/docs/report.txt"),
        }

    def list_dir(self, remote_path=None, parent_id=None):
        if remote_path == "/":
            return [self.items["/docs"]]
        if remote_path == "/docs":
            return [self.items["/docs/report.txt"]]
        return []

    def get_item_by_path(self, remote_path):
        return self.items.get(remote_path)

    def download_file(self, item_id, local_path, progress_cb=None):
        Path(local_path).write_bytes(b"hello world")
        return Path(local_path)


def test_readonly_fuse_core_lists_and_reads_file(tmp_path):
    mount = ReadOnlyFusePrototype(FakeCloudForMount(), cache_dir=tmp_path)

    assert mount.readdir("/") == [".", "..", "docs"]
    assert mount.readdir("/docs") == [".", "..", "report.txt"]

    folder_attr = mount.getattr("/docs")
    file_attr = mount.getattr("/docs/report.txt")
    assert stat.S_ISDIR(folder_attr["st_mode"])
    assert stat.S_ISREG(file_attr["st_mode"])
    assert file_attr["st_size"] == 11

    handle = mount.open("/docs/report.txt")
    assert mount.read("/docs/report.txt", size=5, offset=6, handle=handle) == b"world"
    mount.release("/docs/report.txt", handle)

    with pytest.raises(ValueError):
        mount.read("/docs/report.txt", size=1, offset=0, handle=handle)


def test_readonly_fuse_core_reports_missing_fuse_dependency(tmp_path):
    mount = ReadOnlyFusePrototype(FakeCloudForMount(), cache_dir=tmp_path)

    with pytest.raises(RuntimeError, match="fusepy"):
        mount.mount()
