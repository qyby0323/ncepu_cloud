from pathlib import Path

from ncepu_cloud_client.api.models import CloudItem, CloudItemType
from ncepu_cloud_client.sync.checksum import sha256_file
from ncepu_cloud_client.sync.database import SyncDatabase
from ncepu_cloud_client.sync.engine import SyncEngine
from ncepu_cloud_client.sync.models import SyncDirection, SyncJob, SyncJobType
from ncepu_cloud_client.sync.queue import SyncQueue
from ncepu_cloud_client.sync.worker import SyncWorkerPool


class FakeRemoteClient:
    def __init__(self):
        self.calls = []

    def list_dir(self, remote_path=None, parent_id=None):
        self.calls.append((remote_path, parent_id))
        if parent_id == "root":
            return [
                CloudItem(id="dir-1", name="课程资料", type=CloudItemType.DIRECTORY, path="gns://root/course"),
                CloudItem(id="file-1", name="a:b?.txt", type=CloudItemType.FILE, path="gns://root/a"),
                CloudItem(id="file-ignored", name="token.secret", type=CloudItemType.FILE, path="gns://root/token"),
            ]
        if parent_id == "dir-1":
            return [CloudItem(id="file-2", name="lesson.pdf", type=CloudItemType.FILE, path="gns://root/course/lesson.pdf")]
        return []


class FakeRootResolvingClient:
    def __init__(self):
        self.calls = []

    def resolve_default_root(self):
        self.calls.append(("resolve_default_root", None))
        return CloudItem(id="gns://real/root", name="个人文档库", type=CloudItemType.DIRECTORY, path="gns://real/root")

    def list_dir(self, remote_path=None, parent_id=None):
        self.calls.append((remote_path, parent_id))
        if parent_id == "gns://real/root":
            return [CloudItem(id="file-1", name="report.txt", type=CloudItemType.FILE, path="gns://real/root/report.txt")]
        return []


class FakeDownloadClient:
    def download_file(self, item_id, local_path, progress_cb=None):
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        Path(local_path).write_bytes(b"hello")
        if progress_cb:
            progress_cb(5, 5)
        return Path(local_path)


def test_remote_scan_enqueues_downloads_and_applies_filter(tmp_path):
    db = SyncDatabase(tmp_path / "state.db")
    local_root = tmp_path / "sync"
    task_id = db.add_sync_task(
        name="remote",
        local_root=str(local_root),
        remote_root_id="root",
        remote_root_path="/",
        direction=SyncDirection.REMOTE_TO_LOCAL.value,
        ignore_rules="*.secret",
    )
    engine = SyncEngine(FakeRemoteClient(), db)

    engine._enqueue_remote_tree(db.list_sync_tasks()[0])

    first = engine.queue.get(timeout=0.1)
    second = engine.queue.get(timeout=0.1)
    jobs = sorted([first, second], key=lambda job: str(job.local_path))
    assert [job.job_type for job in jobs] == [SyncJobType.DOWNLOAD, SyncJobType.DOWNLOAD]
    assert jobs[0].sync_task_id == task_id
    assert jobs[0].local_path == local_root / "a_b_.txt"
    assert jobs[0].remote_id == "file-1"
    assert jobs[1].local_path == local_root / "课程资料" / "lesson.pdf"
    assert jobs[1].remote_path == "gns://root/course/lesson.pdf"
    assert engine.queue.empty()


def test_remote_scan_resolves_configured_root_before_listing(tmp_path):
    db = SyncDatabase(tmp_path / "state.db")
    local_root = tmp_path / "sync"
    db.add_sync_task(
        name="remote",
        local_root=str(local_root),
        remote_root_id="root",
        remote_root_path="/",
        direction=SyncDirection.REMOTE_TO_LOCAL.value,
    )
    client = FakeRootResolvingClient()
    engine = SyncEngine(client, db)

    engine._enqueue_remote_tree(db.list_sync_tasks()[0])

    job = engine.queue.get(timeout=0.1)
    assert client.calls[0] == ("resolve_default_root", None)
    assert client.calls[1] == ("gns://real/root", "gns://real/root")
    assert job.remote_id == "file-1"
    assert job.local_path == local_root / "report.txt"


def test_local_scan_enqueues_existing_files_for_upload(tmp_path):
    db = SyncDatabase(tmp_path / "state.db")
    local_root = tmp_path / "sync"
    local_root.mkdir()
    (local_root / "upload.txt").write_text("hello", encoding="utf-8")
    (local_root / "skip.tmp").write_text("ignored", encoding="utf-8")
    task_id = db.add_sync_task(
        name="local",
        local_root=str(local_root),
        remote_root_id="gns://remote/root",
        remote_root_path="gns://remote/root",
        direction=SyncDirection.LOCAL_TO_REMOTE.value,
        ignore_rules="*.tmp",
    )
    engine = SyncEngine(FakeRemoteClient(), db)

    engine._enqueue_local_tree(db.list_sync_tasks()[0])

    job = engine.queue.get(timeout=0.1)
    assert job.job_type == SyncJobType.UPLOAD
    assert job.sync_task_id == task_id
    assert job.local_path == local_root / "upload.txt"
    assert job.remote_dir_id == "gns://remote/root"
    assert engine.queue.empty()


def test_download_worker_records_sync_item_mapping(tmp_path):
    db = SyncDatabase(tmp_path / "state.db")
    task_id = db.add_sync_task(
        name="download",
        local_root=str(tmp_path),
        remote_root_id="root",
        remote_root_path="/",
        direction=SyncDirection.REMOTE_TO_LOCAL.value,
    )
    pool = SyncWorkerPool(FakeDownloadClient(), db, SyncQueue())
    local_path = tmp_path / "downloaded.txt"

    pool._download(SyncJob(SyncJobType.DOWNLOAD, task_id, local_path=local_path, remote_id="remote-1", remote_path="gns://remote-1"))

    item = db.get_sync_item(task_id, str(local_path))
    assert item is not None
    assert item["remote_id"] == "remote-1"
    assert item["remote_path"] == "gns://remote-1"
    assert item["sync_state"] == "synced"


def test_download_worker_preserves_local_conflict_copy(tmp_path, monkeypatch):
    monkeypatch.setattr("ncepu_cloud_client.sync.conflict.local_timestamp_compact", lambda: "20260605-130000")
    db = SyncDatabase(tmp_path / "state.db")
    task_id = db.add_sync_task(
        name="download",
        local_root=str(tmp_path),
        remote_root_id="root",
        remote_root_path="/",
        direction=SyncDirection.BIDIRECTIONAL.value,
    )
    local_path = tmp_path / "downloaded.txt"
    local_path.write_bytes(b"synced")
    db.upsert_sync_item(
        task_id,
        str(local_path),
        remote_id="remote-1",
        remote_path="gns://remote-1",
        item_type="file",
        size=local_path.stat().st_size,
        checksum=sha256_file(local_path),
        sync_state="synced",
    )
    local_path.write_bytes(b"local edit")
    pool = SyncWorkerPool(FakeDownloadClient(), db, SyncQueue())

    pool._download(SyncJob(SyncJobType.DOWNLOAD, task_id, local_path=local_path, remote_id="remote-1", remote_path="gns://remote-1"))

    conflict_path = tmp_path / "downloaded.conflict-20260605-130000.txt"
    assert local_path.read_bytes() == b"hello"
    assert conflict_path.read_bytes() == b"local edit"
    conflict_item = db.get_sync_item(task_id, str(conflict_path))
    assert conflict_item is not None
    assert conflict_item["remote_id"] is None
    assert conflict_item["sync_state"] == "conflict"
    assert conflict_item["conflict_state"] == "keep_both_local_copy"
