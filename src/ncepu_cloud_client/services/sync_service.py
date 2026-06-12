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
        extra_rules = self._split_ignore_rules(settings.sync.custom_ignore_rules) if settings else []
        self.engine = SyncEngine(client, self.database, max_workers=max_workers, extra_ignore_rules=extra_rules)

    def add_task(
        self,
        name: str,
        local_root: Path,
        remote_root_id: str,
        remote_root_path: str,
        direction: SyncDirection = SyncDirection.BIDIRECTIONAL,
        delete_sync_enabled: bool = False,
        encryption_enabled: bool = False,
    ) -> int:
        task_id = self.database.add_sync_task(
            name=name,
            local_root=str(local_root),
            remote_root_id=remote_root_id,
            remote_root_path=remote_root_path,
            direction=direction.value,
            delete_sync_enabled=delete_sync_enabled,
            encryption_enabled=encryption_enabled,
        )
        for task in self.database.list_sync_tasks():
            if task["id"] == task_id:
                self.engine.add_running_task(task)
                break
        return task_id

    def start(self) -> None:
        self.engine.start()

    def stop(self) -> None:
        self.engine.stop()

    @staticmethod
    def _split_ignore_rules(rules: str) -> list[str]:
        return [line.strip() for line in rules.splitlines() if line.strip() and not line.strip().startswith("#")]
