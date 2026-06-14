from __future__ import annotations

import queue

from ncepu_cloud_client.sync.models import SyncJob


class SyncQueue:
    """同步任务的线程安全生产者-消费者缓冲区。

    本地文件监听器和远端扫描线程是生产者，worker 线程是消费者。
    标准库 Queue 内部已经提供跨线程安全交接所需的锁和条件变量。
    """

    def __init__(self):
        self._queue: queue.Queue[SyncJob] = queue.Queue()

    def put(self, job: SyncJob) -> None:
        self._queue.put(job)

    def get(self, timeout: float = 0.5) -> SyncJob:
        return self._queue.get(timeout=timeout)

    def task_done(self) -> None:
        self._queue.task_done()

    def empty(self) -> bool:
        return self._queue.empty()
