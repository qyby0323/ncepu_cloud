from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from ncepu_cloud_client.sync.filter import SyncIgnore
from ncepu_cloud_client.sync.models import SyncJob, SyncJobType
from ncepu_cloud_client.sync.queue import SyncQueue

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except Exception:  # pragma: no cover
    FileSystemEventHandler = object
    Observer = None


class DebouncedLocalHandler(FileSystemEventHandler):
    """把频繁的文件系统事件合并成稳定的上传/删除任务。

    操作系统文件通知通常不是“一次保存对应一次事件”：
    编辑器可能先写临时文件、再重命名、再修改时间戳。
    debounce 的作用就是等事件安静一小段时间后再入队，减少重复上传。
    """

    def __init__(
        self,
        sync_task_id: int,
        remote_dir_id: str,
        queue: SyncQueue,
        root: Path,
        ignore: SyncIgnore,
        delete_sync_enabled: bool = False,
        debounce_seconds: float = 1.0,
    ):
        super().__init__()
        self.sync_task_id = sync_task_id
        self.remote_dir_id = remote_dir_id
        self.queue = queue
        self.root = root
        self.ignore = ignore
        self.delete_sync_enabled = delete_sync_enabled
        self.debounce_seconds = debounce_seconds
        # watchdog 回调可能在很短时间内连续到达。这里用锁保护 pending，
        # 保证事件写入和后台 flush 线程取出任务时不会发生竞态。
        # pending 的键是本地路径，值是最后一次事件到达时间。
        self.pending: dict[Path, float] = {}
        self._lock = threading.Lock()
        # flush 线程只负责把稳定的本地变更推入 SyncQueue，
        # 真正的上传仍然交给 worker 线程池执行。
        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()

    def on_created(self, event):  # noqa: N802
        self._schedule(Path(event.src_path), event.is_directory)

    def on_modified(self, event):  # noqa: N802
        self._schedule(Path(event.src_path), event.is_directory)

    def on_moved(self, event):  # noqa: N802
        # 移动/重命名后的目标路径需要作为新文件上传。
        # 源路径是否删除到云端由 delete_sync_enabled 控制，避免误删风险。
        self._schedule(Path(event.dest_path), event.is_directory)

    def on_deleted(self, event):  # noqa: N802
        path = Path(event.src_path)
        if event.is_directory or not self.delete_sync_enabled or self.ignore.should_ignore(path, self.root):
            return
        # 删除同步必须显式开启，因为把本地误删传播到云端是最高风险操作。
        self.queue.put(SyncJob(SyncJobType.DELETE_REMOTE, self.sync_task_id, local_path=path))

    def _schedule(self, path: Path, is_directory: bool) -> None:
        if is_directory or self.ignore.should_ignore(path, self.root):
            return
        with self._lock:
            # 每个路径只保留最新时间戳，连续保存触发的多次事件会合并成一次上传。
            self.pending[path] = time.time()

    def _flush_loop(self) -> None:
        while True:
            time.sleep(0.3)
            now = time.time()
            ready: list[Path] = []
            with self._lock:
                for path, ts in list(self.pending.items()):
                    if now - ts >= self.debounce_seconds:
                        ready.append(path)
                        self.pending.pop(path, None)
            for path in ready:
                # worker 在读取前还会检查文件是否稳定；这里仅判断事件是否已经安静到可以入队。
                # 双层保护可以应对大文件写入：watcher 负责“事件防抖”，worker 负责“文件大小稳定”。
                self.queue.put(SyncJob(SyncJobType.UPLOAD, self.sync_task_id, local_path=path, remote_dir_id=self.remote_dir_id))


class LocalWatcher:
    """对 watchdog 操作系统相关 observer 后端的轻量封装。

    watchdog 会根据平台选择不同后端：Windows 下通常使用 ReadDirectoryChangesW。
    本类把第三方库的 observer 生命周期包起来，避免 UI 或同步调度器直接依赖底层细节。
    """

    def __init__(self):
        self._observer = Observer() if Observer else None

    def watch(
        self,
        sync_task_id: int,
        local_root: Path,
        remote_dir_id: str,
        queue: SyncQueue,
        delete_sync_enabled: bool = False,
        extra_ignore_rules: list[str] | None = None,
    ) -> None:
        if self._observer is None:
            raise RuntimeError("watchdog 未安装，请执行 pip install watchdog")
        # .syncignore 是每个同步目录自己的过滤规则；
        # extra_ignore_rules 是设置页或配置文件传入的全局补充规则。
        ignore = SyncIgnore.from_file(local_root / ".syncignore", extra_rules=extra_ignore_rules)
        handler = DebouncedLocalHandler(sync_task_id, remote_dir_id, queue, local_root, ignore, delete_sync_enabled=delete_sync_enabled)
        self._observer.schedule(handler, str(local_root), recursive=True)

    def start(self) -> None:
        if self._observer:
            self._observer.start()

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            # observer 内部也有线程。join 等待它退出，避免下一次启动时残留旧监听器。
            self._observer.join(timeout=2)
            self._observer = Observer() if Observer else None
