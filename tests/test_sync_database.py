from ncepu_cloud_client.sync.database import SyncDatabase


def test_sync_database_creates_tables_and_upserts(tmp_path):
    db = SyncDatabase(tmp_path / "state.db")
    task_id = db.add_sync_task(
        name="demo",
        local_root=str(tmp_path),
        remote_root_id="root",
        remote_root_path="/",
        direction="bidirectional",
        ignore_rules="build/\n*.bak",
    )
    assert task_id == 1
    task = db.list_sync_tasks()[0]
    assert task["ignore_rules"] == "build/\n*.bak"
    db.update_sync_task_options(task_id, ignore_rules="dist/")
    assert db.list_sync_tasks()[0]["ignore_rules"] == "dist/"
    db.upsert_sync_item(task_id, str(tmp_path / "a.txt"), remote_id="r1", checksum="abc", sync_state="synced")
    db.upsert_sync_item(task_id, str(tmp_path / "a.txt"), remote_id="r2", checksum="def", sync_state="synced")
    item = db.get_sync_item(task_id, str(tmp_path / "a.txt"))
    assert item is not None
    assert item["remote_id"] == "r2"
    transfer_id = db.add_transfer(task_id, str(tmp_path / "a.txt"), "r2", "upload")
    db.update_transfer(transfer_id, status="success", progress=1.0)
    assert db.list_transfers()[0]["status"] == "success"
    db.delete_sync_task(task_id)
    assert db.list_sync_tasks() == []
    assert db.get_sync_item(task_id, str(tmp_path / "a.txt")) is None
    assert db.list_transfers() == []


def test_sync_database_migrates_old_tasks_table(tmp_path):
    path = tmp_path / "old-state.db"
    db = SyncDatabase(path)
    with db.connect() as conn:
        conn.execute("DROP TABLE sync_tasks")
        conn.execute(
            """
            CREATE TABLE sync_tasks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT,
              local_root TEXT NOT NULL,
              remote_root_id TEXT NOT NULL,
              remote_root_path TEXT,
              direction TEXT NOT NULL,
              enabled INTEGER NOT NULL DEFAULT 1,
              delete_sync_enabled INTEGER NOT NULL DEFAULT 0,
              encryption_enabled INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )

    db.initialize()
    task_id = db.add_sync_task("demo", str(tmp_path), "root", "/", "bidirectional", ignore_rules="*.tmp")

    assert db.list_sync_tasks()[0]["id"] == task_id
    assert db.list_sync_tasks()[0]["ignore_rules"] == "*.tmp"
