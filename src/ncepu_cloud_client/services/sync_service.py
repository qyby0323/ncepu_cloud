from __future__ import annotations

from pathlib import Path

from ncepu_cloud_client.api.base import CloudDriveClient
from ncepu_cloud_client.config.settings import Settings
from ncepu_cloud_client.sync.database import SyncDatabase
from ncepu_cloud_client.sync.engine import SyncEngine
from ncepu_cloud_client.sync.models import SyncDirection


class SyncService:
    def __init__(self, client: CloudDriveClient, database: SyncDatabase | None = None, settings: Settings | None = None):
        self.database = database or SyncDatabase()
        max_workers = settings.sync.max_workers if settings else 4
        self.engine = SyncEngine(client, self.database, max_workers=max_workers)

    def add_task(
        self,
        name: str,
        local_root: Path,
        remote_root_id: str,
        remote_root_path: str,
        direction: SyncDirection = SyncDirection.BIDIRECTIONAL,
        delete_sync_enabled: bool = False,
        encryption_enabled: bool = False,
        ignore_rules: str = "",
    ) -> int:
        task_id = self.database.add_sync_task(
            name=name,
            local_root=str(local_root),
            remote_root_id=remote_root_id,
            remote_root_path=remote_root_path,
            direction=direction.value,
            delete_sync_enabled=delete_sync_enabled,
            encryption_enabled=encryption_enabled,
            ignore_rules=ignore_rules,
        )
        for task in self.database.list_sync_tasks():
            if task["id"] == task_id:
                self.engine.add_running_task(task)
                break
        return task_id

    def delete_task(self, task_id: int) -> None:
        was_running = self.engine.is_running
        if was_running:
            self.engine.stop()
        self.engine.queue.discard_for_task(task_id)
        self.database.delete_sync_task(task_id)
        if was_running:
            self.engine.start()

    def start(self) -> None:
        self.engine.start()

    def stop(self) -> None:
        self.engine.stop()
