from __future__ import annotations

import queue

from ncepu_cloud_client.sync.models import SyncJob


class SyncQueue:
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

