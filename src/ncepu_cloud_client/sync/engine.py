from __future__ import annotations

import threading
from pathlib import Path

from ncepu_cloud_client.api.base import CloudDriveClient
from ncepu_cloud_client.sync.filter import SyncIgnore
from ncepu_cloud_client.sync.database import SyncDatabase
from ncepu_cloud_client.sync.models import SyncDirection, SyncJob, SyncJobType
from ncepu_cloud_client.sync.queue import SyncQueue
from ncepu_cloud_client.sync.watcher import LocalWatcher
from ncepu_cloud_client.sync.worker import SyncWorkerPool
from ncepu_cloud_client.utils.logger import get_logger

logger = get_logger("sync.engine")


class SyncEngine:
    """协调本地文件监听器、同步队列和 worker 线程池。"""

    def __init__(self, client: CloudDriveClient, database: SyncDatabase, max_workers: int = 4, extra_ignore_rules: list[str] | None = None):
        self.client = client
        self.database = database
        self.extra_ignore_rules = extra_ignore_rules or []
        self.queue = SyncQueue()
        self.watcher = LocalWatcher()
        self.workers = SyncWorkerPool(client, database, self.queue, max_workers=max_workers)
        self._started = False
        self._scan_stop = threading.Event()
        self._scan_threads: list[threading.Thread] = []

    def start(self) -> None:
        if self._started:
            return
        self._scan_stop.clear()
        # 先注册本地生产者，再启动远端扫描。已有文件可以立刻入队，
        # 较慢的网络扫描保持异步执行，不阻塞启动流程。
        for task in self.database.list_sync_tasks():
            self._start_task(task, start_remote_scan=False)
        self.workers.start()
        self.watcher.start()
        # 远端扫描可能阻塞在网络 I/O 上，因此放在服务启动后异步执行。
        for task in self.database.list_sync_tasks():
            self._start_remote_scan_if_needed(task)
        self._started = True

    def add_running_task(self, task: dict) -> None:
        if not self._started:
            return
        self._start_task(task, start_remote_scan=True)

    def stop(self) -> None:
        if not self._started:
            return
        # 使用协作式停止，避免线程正在写文件或更新 SQLite 时被强制中断。
        self._scan_stop.set()
        for thread in self._scan_threads:
            thread.join(timeout=2)
        self._scan_threads.clear()
        self.watcher.stop()
        self.workers.stop()
        self._started = False

    def _start_task(self, task: dict, start_remote_scan: bool) -> None:
        if not task["enabled"]:
            return
        local_root = Path(task["local_root"])
        local_root.mkdir(parents=True, exist_ok=True)
        if task["direction"] in (SyncDirection.LOCAL_TO_REMOTE.value, SyncDirection.BIDIRECTIONAL.value):
            self.watcher.watch(
                task["id"],
                local_root,
                task["remote_root_id"],
                self.queue,
                delete_sync_enabled=bool(task["delete_sync_enabled"]),
                extra_ignore_rules=self.extra_ignore_rules,
            )
            self._enqueue_local_tree(task)
        if start_remote_scan:
            self._start_remote_scan_if_needed(task)

    def _start_remote_scan_if_needed(self, task: dict) -> None:
        if not task["enabled"]:
            return
        if task["direction"] not in (SyncDirection.REMOTE_TO_LOCAL.value, SyncDirection.BIDIRECTIONAL.value):
            return
        # 每个同步任务独立一个扫描线程，避免某个远端目录很慢时阻塞其他任务。
        thread = threading.Thread(target=self._enqueue_remote_tree, args=(task,), name=f"remote-scan-{task['id']}", daemon=True)
        thread.start()
        self._scan_threads.append(thread)

    def _enqueue_local_tree(self, task: dict) -> None:
        local_root = Path(task["local_root"])
        ignore = SyncIgnore.from_file(local_root / ".syncignore", extra_rules=self.extra_ignore_rules)
        # 初始全量遍历用于覆盖 watchdog 开始监听之前就已经存在的文件。
        for path in local_root.rglob("*"):
            if self._scan_stop.is_set():
                return
            if not path.is_file() or ignore.should_ignore(path, local_root):
                continue
            self.queue.put(
                SyncJob(
                    SyncJobType.UPLOAD,
                    task["id"],
                    local_path=path,
                    remote_dir_id=task["remote_root_id"],
                    remote_name=path.name,
                )
            )

    def _enqueue_remote_tree(self, task: dict) -> None:
        local_root = Path(task["local_root"])
        try:
            local_root.mkdir(parents=True, exist_ok=True)
            ignore = SyncIgnore.from_file(local_root / ".syncignore", extra_rules=self.extra_ignore_rules)
            remote_id, remote_path = self._resolve_remote_root(task["remote_root_id"], task.get("remote_root_path") or None)
            self._enqueue_remote_dir(
                sync_task_id=task["id"],
                remote_id=remote_id,
                remote_path=remote_path,
                local_root=local_root,
                local_dir=local_root,
                ignore=ignore,
            )
        except Exception as exc:
            logger.exception("remote scan failed for sync task %s: %s", task.get("id"), exc)

    def _enqueue_remote_dir(
        self,
        sync_task_id: int,
        remote_id: str,
        remote_path: str | None,
        local_root: Path,
        local_dir: Path,
        ignore: SyncIgnore,
    ) -> None:
        if self._scan_stop.is_set():
            return
        items = self.client.list_dir(remote_path=remote_path, parent_id=remote_id)
        for item in items:
            if self._scan_stop.is_set():
                return
            if not item.name:
                continue
            local_path = local_dir / self._safe_local_name(item.name)
            if ignore.should_ignore(local_path, local_root):
                continue
            if item.is_dir:
                # 先在本地创建远端目录结构，再把目录下的文件加入下载队列，
                # 这样下载时本地路径是稳定存在的。
                local_path.mkdir(parents=True, exist_ok=True)
                self._enqueue_remote_dir(sync_task_id, item.id, item.path, local_root, local_path, ignore)
            elif item.id:
                self.queue.put(
                    SyncJob(
                        SyncJobType.DOWNLOAD,
                        sync_task_id,
                        local_path=local_path,
                        remote_id=item.id,
                        remote_path=item.path,
                    )
                )

    def _resolve_remote_root(self, remote_id: str, remote_path: str | None) -> tuple[str, str | None]:
        if remote_id not in ("", "/", "root"):
            return remote_id, remote_path if remote_path not in ("", "/", "root", None) else remote_id
        if remote_path not in ("", "/", "root", None):
            return remote_path, remote_path
        try:
            # "root" 只是 UI 层占位符。真实 API 通常需要文档库的 gns:// id，
            # 因此扫描前先解析成真正的远端根目录。
            resolver = getattr(self.client, "resolve_default_root", None)
            if callable(resolver):
                item = resolver()
            else:
                item = next((entry for entry in self.client.list_dir("/") if entry.is_dir and entry.id), None)
            if item and item.id:
                return item.id, item.path or item.id
        except Exception as exc:
            logger.warning("default remote root resolution failed, using configured root: %s", exc)
        return remote_id, remote_path

    @staticmethod
    def _safe_local_name(name: str) -> str:
        # 云端名称可能包含 Windows 不允许的文件名字符。这里只清洗本地文件名，
        # 远端 id/path 保持原样，避免影响 API 调用。
        invalid = '<>:"/\\|?*'
        cleaned = "".join("_" if char in invalid or ord(char) < 32 else char for char in name).strip()
        if not cleaned or cleaned in {".", ".."}:
            return "_"
        return cleaned.rstrip(". ") or "_"
