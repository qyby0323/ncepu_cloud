from __future__ import annotations

import queue

from ncepu_cloud_client.sync.models import SyncJob


class SyncQueue:
    """同步任务的线程安全生产者-消费者缓冲区。

    本地文件监听器和远端扫描线程是生产者，worker 线程是消费者。
    标准库 Queue 内部已经提供跨线程安全交接所需的锁和条件变量。
    这样业务代码不需要自己管理互斥锁、等待队列和唤醒逻辑，可以降低竞态和死锁风险。
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

    def discard_for_task(self, sync_task_id: int) -> None:
        """丢弃指定同步任务还没开始执行的队列项。

        删除任务时，数据库记录会先被移除，但队列里可能还残留该任务的上传/下载请求。
        这里把队列临时取空，再只放回其他任务，避免已删除任务继续被 worker 执行。
        """
        kept: list[SyncJob] = []
        while True:
            try:
                job = self._queue.get_nowait()
            except queue.Empty:
                break
            if job.sync_task_id != sync_task_id:
                kept.append(job)
            self._queue.task_done()
        for job in kept:
            self._queue.put(job)
