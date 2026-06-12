from pathlib import Path

from ncepu_cloud_client.api.models import CloudItemType
from ncepu_cloud_client.api.mock_client import MockCloudClient


def test_mock_client_upload_download_and_list(tmp_path):
    client = MockCloudClient()
    client.login()
    folder = client.mkdir("/测试目录")
    assert folder.type == CloudItemType.DIRECTORY
    local = tmp_path / "hello.txt"
    local.write_text("hello", encoding="utf-8")
    uploaded = client.upload_file(local, folder.id)
    assert uploaded.name == "hello.txt"
    assert client.list_dir(parent_id=folder.id)[0].id == uploaded.id
    target = tmp_path / "download.txt"
    client.download_file(uploaded.id, target)
    assert target.read_text(encoding="utf-8") == "hello"


def test_mock_search_and_fields(tmp_path):
    client = MockCloudClient()
    local = tmp_path / "report.txt"
    local.write_text("x", encoding="utf-8")
    item = client.upload_file(local, "root")
    assert client.search("report")[0].id == item.id
    assert client.get_item_fields(item.id, ["name"]) == {"name": "report.txt"}


def test_mock_move_and_copy(tmp_path):
    client = MockCloudClient()
    source_dir = client.mkdir("/源目录")
    target_dir = client.mkdir("/目标目录")
    local = tmp_path / "report.txt"
    local.write_text("x", encoding="utf-8")
    item = client.upload_file(local, source_dir.id)

    moved = client.move(item.id, target_dir.id)
    copied = client.copy(moved.id, source_dir.id)

    assert moved.parent_id == target_dir.id
    assert copied.parent_id == source_dir.id
    assert client.download_file(copied.id, tmp_path / "copy.txt").read_text(encoding="utf-8") == "x"
