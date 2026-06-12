from ncepu_cloud_client.sync.database import SyncDatabase


def test_sync_database_creates_tables_and_upserts(tmp_path):
    db = SyncDatabase(tmp_path / "state.db")
    task_id = db.add_sync_task(
        name="demo",
        local_root=str(tmp_path),
        remote_root_id="root",
        remote_root_path="/",
        direction="bidirectional",
    )
    assert task_id == 1
    db.upsert_sync_item(task_id, str(tmp_path / "a.txt"), remote_id="r1", checksum="abc", sync_state="synced")
    db.upsert_sync_item(task_id, str(tmp_path / "a.txt"), remote_id="r2", checksum="def", sync_state="synced")
    item = db.get_sync_item(task_id, str(tmp_path / "a.txt"))
    assert item is not None
    assert item["remote_id"] == "r2"
    transfer_id = db.add_transfer(task_id, str(tmp_path / "a.txt"), "r2", "upload")
    db.update_transfer(transfer_id, status="success", progress=1.0)
    assert db.list_transfers()[0]["status"] == "success"

