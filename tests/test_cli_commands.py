from pathlib import Path

from ncepu_cloud_client.api.models import CloudItem, CloudItemType, CloudLibrary, CloudQuota
from ncepu_cloud_client.cli import commands
from ncepu_cloud_client.config.settings import Settings


class FakeCliClient:
    def __init__(self):
        self.deleted: list[str] = []
        self.renamed: list[tuple[str, str]] = []
        self.moved: list[tuple[str, str]] = []
        self.copied: list[tuple[str, str]] = []
        self.uploaded: list[tuple[Path, str]] = []

    def get_quota(self):
        return CloudQuota(total=1024, used=256)

    def get_doc_lib_quota(self, doc_lib_id):
        return CloudQuota(total=2048, used=512)

    def list_libraries(self):
        return [CloudLibrary(id="lib-1", name="个人文档库", owner="tester")]

    def list_dir(self, remote_path=None, parent_id=None):
        return [CloudItem(id="file-1", name="report.txt", type=CloudItemType.FILE, size=8, path="/report.txt")]

    def search(self, keyword):
        return [CloudItem(id="file-2", name=f"{keyword}.pdf", type=CloudItemType.FILE, path=f"/{keyword}.pdf")]

    def mkdir(self, remote_path):
        return CloudItem(id="dir-1", name=Path(remote_path).name, type=CloudItemType.DIRECTORY, path=remote_path)

    def delete(self, item_id):
        self.deleted.append(item_id)

    def rename(self, item_id, new_name):
        self.renamed.append((item_id, new_name))
        return CloudItem(id=item_id, name=new_name, type=CloudItemType.FILE)

    def move(self, item_id, target_dir_id):
        self.moved.append((item_id, target_dir_id))
        return CloudItem(id=item_id, name="moved.txt", type=CloudItemType.FILE)

    def copy(self, item_id, target_dir_id):
        self.copied.append((item_id, target_dir_id))
        return CloudItem(id="copied-id", name="copied.txt", type=CloudItemType.FILE)

    def get_item_fields(self, item_id, fields):
        return {field: f"{item_id}:{field}" for field in fields}

    def get_item_by_path(self, remote_path):
        return CloudItem(id="resolved-id", name=Path(remote_path).name, type=CloudItemType.FILE, path=remote_path)

    def upload_file(self, local_path, remote_dir_id, remote_name=None, progress_cb=None):
        self.uploaded.append((Path(local_path), remote_dir_id))
        return CloudItem(id="uploaded-1", name=remote_name or Path(local_path).name, type=CloudItemType.FILE)


def install_fake_bootstrap(monkeypatch):
    client = FakeCliClient()
    monkeypatch.setattr(commands, "bootstrap", lambda: (Settings(), client))
    return client


def test_cli_libraries_and_quota(monkeypatch, capsys):
    install_fake_bootstrap(monkeypatch)

    assert commands.main(["libraries"]) == 0
    assert "lib-1\t个人文档库\ttester" in capsys.readouterr().out

    assert commands.main(["doc-lib-quota", "lib-1"]) == 0
    assert "512 B / 总容量 2.0 KB" in capsys.readouterr().out


def test_cli_search_mkdir_delete_rename_and_fields(monkeypatch, capsys):
    client = install_fake_bootstrap(monkeypatch)

    assert commands.main(["search", "课程"]) == 0
    assert "课程.pdf" in capsys.readouterr().out

    assert commands.main(["mkdir", "/课程资料"]) == 0
    assert "创建完成" in capsys.readouterr().out

    assert commands.main(["delete", "/report.txt"]) == 0
    assert client.deleted == ["resolved-id"]

    assert commands.main(["rename", "file-1", "renamed.txt"]) == 0
    assert client.renamed == [("file-1", "renamed.txt")]

    assert commands.main(["move", "file-1", "/目标目录"]) == 0
    assert client.moved == [("file-1", "resolved-id")]

    assert commands.main(["copy", "/report.txt", "root"]) == 0
    assert client.copied == [("resolved-id", "root")]

    assert commands.main(["fields", "file-1", "name", "size"]) == 0
    output = capsys.readouterr().out
    assert '"name": "file-1:name"' in output
    assert '"size": "file-1:size"' in output


def test_cli_upload_resolves_remote_path(monkeypatch, capsys, tmp_path):
    client = install_fake_bootstrap(monkeypatch)
    local = tmp_path / "demo.txt"
    local.write_text("demo", encoding="utf-8")

    assert commands.main(["upload", str(local), "/目标目录"]) == 0

    assert client.uploaded == [(local, "resolved-id")]
    assert "上传完成" in capsys.readouterr().out


def test_cli_sync_add_accepts_task_ignore_rules(monkeypatch, capsys, tmp_path):
    install_fake_bootstrap(monkeypatch)
    captured = {}

    class FakeSyncService:
        def __init__(self, *args, **kwargs):
            pass

        def add_task(self, **kwargs):
            captured.update(kwargs)
            return 9

    monkeypatch.setattr(commands, "SyncService", FakeSyncService)

    assert commands.main(["sync-add", str(tmp_path), "gns://root", "--ignore-rule", "build/", "--ignore-rule", "*.bak"]) == 0

    assert captured["ignore_rules"] == "build/\n*.bak"
    assert "同步任务已创建: 9" in capsys.readouterr().out
