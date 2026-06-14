from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from ncepu_cloud_client.api.base import CloudDriveClient
from ncepu_cloud_client.app.paths import app_cache_dir
from ncepu_cloud_client.security.encryptor import Encryptor
from ncepu_cloud_client.security.key_store import EncryptionKeyStore
from ncepu_cloud_client.sync.checksum import sha256_file
from ncepu_cloud_client.sync.conflict import conflict_copy_path
from ncepu_cloud_client.sync.database import SyncDatabase
from ncepu_cloud_client.sync.models import SyncJob, SyncJobType, TransferStatus
from ncepu_cloud_client.sync.queue import SyncQueue
from ncepu_cloud_client.utils.file_utils import wait_until_size_stable
from ncepu_cloud_client.utils.logger import get_logger

logger = get_logger("sync.worker")

ProgressHandler = Callable[[SyncJob, float], None]


class SyncWorkerPool:
    """用于网络和文件系统 I/O 的有界 worker 线程池。

    同步任务主要是 I/O 密集型，少量固定线程可以提升响应性，
    同时避免无限创建线程带来的上下文切换开销。
    """

    def __init__(self, client: CloudDriveClient, database: SyncDatabase, jobs: SyncQueue, max_workers: int = 4, progress_handler: ProgressHandler | None = None):
        self.client = client
        self.database = database
        self.jobs = jobs
        self.max_workers = max_workers
        self.progress_handler = progress_handler
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        if self._threads:
            return
        self._stop.clear()
        for index in range(self.max_workers):
            thread = threading.Thread(target=self._run, name=f"sync-worker-{index}", daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2)
        self._threads.clear()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                # 设置超时可以让线程定期检查停止事件，
                # 避免在空队列上永久阻塞。
                job = self.jobs.get(timeout=0.5)
            except Exception:
                continue
            try:
                self._execute(job)
            except Exception as exc:
                logger.exception("sync job failed: %s", exc)
            finally:
                self.jobs.task_done()

    def _execute(self, job: SyncJob) -> None:
        if job.job_type == SyncJobType.UPLOAD and job.local_path:
            self._upload(job)
        elif job.job_type == SyncJobType.DOWNLOAD and job.remote_id and job.local_path:
            self._download(job)
        elif job.job_type == SyncJobType.DELETE_REMOTE:
            remote_id = job.remote_id
            if not remote_id and job.local_path:
                item = self.database.get_sync_item(job.sync_task_id, str(job.local_path))
                remote_id = item.get("remote_id") if item else None
            if remote_id:
                self.client.delete(remote_id)

    def _upload(self, job: SyncJob) -> None:
        path = Path(job.local_path)
        # 编辑器经常在文件尚未完全写入时就触发变更事件。
        # 上传前等待文件大小稳定，可以降低上传半成品文件的概率。
        if not wait_until_size_stable(path):
            return
        task = self._sync_task(job.sync_task_id)
        upload_path = path
        remote_name = job.remote_name
        if task and task.get("encryption_enabled"):
            # 加密输出写入应用缓存目录，不替换用户原始本地文件。
            passphrase = EncryptionKeyStore().load_passphrase()
            if not passphrase:
                raise RuntimeError("同步任务已启用加密，但尚未在设置页保存加密口令。")
            encrypted_dir = app_cache_dir() / "encrypted_uploads"
            encrypted_dir.mkdir(parents=True, exist_ok=True)
            upload_path = Encryptor(passphrase).encrypt_file(path, encrypted_dir / f"{path.name}.ncepuenc")
            remote_name = remote_name or upload_path.name
        transfer_id = self.database.add_transfer(job.sync_task_id, str(path), None, "upload")
        total = upload_path.stat().st_size

        def progress(done: int, all_bytes: int) -> None:
            value = done / all_bytes if all_bytes else 0
            # 进度写入数据库，即使 UI 页面重建也能恢复最近状态。
            self.database.update_transfer(transfer_id, status=TransferStatus.RUNNING.value, progress=value)
            if self.progress_handler:
                self.progress_handler(job, value)

        try:
            item = self.client.upload_file(upload_path, job.remote_dir_id or "root", remote_name, progress)
            checksum = sha256_file(path)
            self.database.upsert_sync_item(
                job.sync_task_id,
                str(path),
                remote_id=item.id,
                remote_path=item.path,
                item_type=item.type.value,
                size=total,
                checksum=checksum,
                sync_state="synced",
            )
            self.database.update_transfer(transfer_id, status=TransferStatus.SUCCESS.value, progress=1.0)
        except Exception as exc:
            self.database.update_transfer(transfer_id, status=TransferStatus.FAILED.value, error_message=str(exc))
            raise

    def _sync_task(self, sync_task_id: int) -> dict | None:
        for task in self.database.list_sync_tasks():
            if task["id"] == sync_task_id:
                return task
        return None

    def _download(self, job: SyncJob) -> None:
        path = Path(job.local_path)
        transfer_id = self.database.add_transfer(job.sync_task_id, str(path), job.remote_id, "download")

        def progress(done: int, all_bytes: int) -> None:
            value = done / all_bytes if all_bytes else 0
            self.database.update_transfer(transfer_id, status=TransferStatus.RUNNING.value, progress=value)
            if self.progress_handler:
                self.progress_handler(job, value)

        try:
            # 远端版本写入同一路径前，先保护用户本地修改。
            self._preserve_local_conflict(job, path)
            self.client.download_file(job.remote_id or "", path, progress)
            final_path = path
            task = self._sync_task(job.sync_task_id)
            if task and task.get("encryption_enabled") and path.name.endswith(".ncepuenc"):
                passphrase = EncryptionKeyStore().load_passphrase()
                if not passphrase:
                    raise RuntimeError("同步任务已启用加密，但尚未在设置页保存加密口令。")
                target = path.with_name(path.name.removesuffix(".ncepuenc"))
                self._preserve_local_conflict(job, target)
                Encryptor(passphrase).decrypt_file(path, target)
                final_path = target
            checksum = sha256_file(final_path) if final_path.exists() and final_path.is_file() else None
            self.database.upsert_sync_item(
                job.sync_task_id,
                str(final_path),
                remote_id=job.remote_id,
                remote_path=job.remote_path,
                item_type="file",
                size=final_path.stat().st_size if final_path.exists() else None,
                checksum=checksum,
                sync_state="synced",
            )
            self.database.update_transfer(transfer_id, status=TransferStatus.SUCCESS.value, progress=1.0)
        except Exception as exc:
            self.database.update_transfer(transfer_id, status=TransferStatus.FAILED.value, error_message=str(exc))
            raise

    def _preserve_local_conflict(self, job: SyncJob, path: Path) -> Path | None:
        if not path.exists() or not path.is_file():
            return None
        current_checksum = sha256_file(path)
        sync_item = self.database.get_sync_item(job.sync_task_id, str(path))
        if sync_item and sync_item.get("checksum") == current_checksum:
            return None
        # keep_both 冲突策略：先把用户本地版本移到冲突副本，
        # 再允许下载的远端版本写入原路径。
        conflict_path = conflict_copy_path(path)
        path.replace(conflict_path)
        self.database.upsert_sync_item(
            job.sync_task_id,
            str(conflict_path),
            remote_id=None,
            remote_path=sync_item.get("remote_path") if sync_item else job.remote_path,
            item_type="file",
            size=conflict_path.stat().st_size,
            checksum=current_checksum,
            sync_state="conflict",
            conflict_state="keep_both_local_copy",
        )
        logger.warning("kept local conflict copy before download: %s", conflict_path)
        return conflict_path
