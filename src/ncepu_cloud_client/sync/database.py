from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ncepu_cloud_client.app.paths import ensure_runtime_dirs, state_db_file
from ncepu_cloud_client.utils.time_utils import utc_now_iso


class SyncDatabase:
    """保存同步任务、同步文件和传输记录的 SQLite 状态库。

    同步程序不能只依赖内存，因为客户端关闭后仍要知道哪些文件已经同步、
    哪些远端 id 对应哪些本地路径，以及上次传输是否失败。
    SQLite 适合这种单机桌面应用：无需额外数据库服务，事务和文件锁由库内部处理。
    """

    def __init__(self, path: Path | None = None):
        ensure_runtime_dirs()
        self.path = path or state_db_file()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        # 每次操作使用短生命周期连接，避免多个 worker 线程共享同一个 sqlite3 连接，
        # 同时缩短写锁持有时间。
        # sqlite3 默认连接不建议跨线程复用，所以这里把连接创建限制在单个数据库操作内。
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            # 数据库是同步功能的持久化状态：tasks 定义同步任务，
            # items 维护本地路径到远端 id 的映射，transfers 支撑 UI 进度显示。
            # 三张表拆开可以避免把任务配置、文件状态和一次性传输日志混在一起。
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sync_tasks (
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
                );

                CREATE TABLE IF NOT EXISTS sync_items (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  sync_task_id INTEGER NOT NULL,
                  local_path TEXT NOT NULL,
                  remote_id TEXT,
                  remote_path TEXT,
                  item_type TEXT,
                  size INTEGER,
                  local_mtime TEXT,
                  remote_mtime TEXT,
                  checksum TEXT,
                  sync_state TEXT,
                  last_synced_at TEXT,
                  conflict_state TEXT,
                  UNIQUE(sync_task_id, local_path)
                );

                CREATE TABLE IF NOT EXISTS transfer_records (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  sync_task_id INTEGER,
                  local_path TEXT,
                  remote_id TEXT,
                  direction TEXT,
                  status TEXT,
                  progress REAL,
                  error_message TEXT,
                  created_at TEXT,
                  updated_at TEXT
                );
                """
            )

    def add_sync_task(
        self,
        name: str,
        local_root: str,
        remote_root_id: str,
        remote_root_path: str,
        direction: str,
        delete_sync_enabled: bool = False,
        encryption_enabled: bool = False,
    ) -> int:
        now = utc_now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO sync_tasks
                (name, local_root, remote_root_id, remote_root_path, direction, delete_sync_enabled, encryption_enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (name, local_root, remote_root_id, remote_root_path, direction, int(delete_sync_enabled), int(encryption_enabled), now, now),
            )
            return int(cur.lastrowid)

    def list_sync_tasks(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM sync_tasks ORDER BY id DESC")]

    def set_sync_task_enabled(self, task_id: int, enabled: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE sync_tasks SET enabled=?, updated_at=? WHERE id=?",
                (int(enabled), utc_now_iso(), task_id),
            )

    def update_sync_task_options(
        self,
        task_id: int,
        delete_sync_enabled: bool | None = None,
        encryption_enabled: bool | None = None,
        direction: str | None = None,
    ) -> None:
        fields: list[str] = []
        values: list[Any] = []
        # 这里按传入参数动态生成 UPDATE 字段，避免调用方只修改一个选项时误覆盖其他设置。
        # 字段名来自固定白名单分支，不接收用户输入，因此不会形成 SQL 注入入口。
        if delete_sync_enabled is not None:
            fields.append("delete_sync_enabled=?")
            values.append(int(delete_sync_enabled))
        if encryption_enabled is not None:
            fields.append("encryption_enabled=?")
            values.append(int(encryption_enabled))
        if direction is not None:
            fields.append("direction=?")
            values.append(direction)
        if not fields:
            return
        fields.append("updated_at=?")
        values.append(utc_now_iso())
        values.append(task_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE sync_tasks SET {','.join(fields)} WHERE id=?", values)

    def upsert_sync_item(self, sync_task_id: int, local_path: str, **values: Any) -> None:
        now = utc_now_iso()
        allowed = {
            "remote_id",
            "remote_path",
            "item_type",
            "size",
            "local_mtime",
            "remote_mtime",
            "checksum",
            "sync_state",
            "last_synced_at",
            "conflict_state",
        }
        payload = {key: value for key, value in values.items() if key in allowed}
        payload.setdefault("last_synced_at", now)
        columns = ["sync_task_id", "local_path", *payload.keys()]
        placeholders = ",".join("?" for _ in columns)
        update = ",".join(f"{key}=excluded.{key}" for key in payload.keys())
        with self.connect() as conn:
            # 唯一键让 local_path 成为某个同步任务内的稳定身份。
            # ON CONFLICT 会把重复同步转化为状态更新。
            # 这比先 SELECT 再 INSERT/UPDATE 更简洁，也减少并发 worker 下的竞态窗口。
            conn.execute(
                f"""
                INSERT INTO sync_items ({",".join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(sync_task_id, local_path)
                DO UPDATE SET {update}
                """,
                [sync_task_id, local_path, *payload.values()],
            )

    def get_sync_item(self, sync_task_id: int, local_path: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sync_items WHERE sync_task_id=? AND local_path=?",
                (sync_task_id, local_path),
            ).fetchone()
            return dict(row) if row else None

    def add_transfer(self, sync_task_id: int | None, local_path: str | None, remote_id: str | None, direction: str) -> int:
        now = utc_now_iso()
        with self.connect() as conn:
            # transfer_records 记录的是“一次传输尝试”，不是文件的最终状态。
            # 因此同一个文件可以有多条上传/下载记录，方便 UI 展示历史和失败原因。
            cur = conn.execute(
                """
                INSERT INTO transfer_records
                (sync_task_id, local_path, remote_id, direction, status, progress, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', 0, ?, ?)
                """,
                (sync_task_id, local_path, remote_id, direction, now, now),
            )
            return int(cur.lastrowid)

    def update_transfer(self, transfer_id: int, status: str | None = None, progress: float | None = None, error_message: str | None = None) -> None:
        fields: list[str] = []
        values: list[Any] = []
        # 与任务配置更新一样，这里只写入发生变化的字段。
        # 进度回调可能非常频繁，保持 SQL 简单有助于降低数据库写入开销。
        if status is not None:
            fields.append("status=?")
            values.append(status)
        if progress is not None:
            fields.append("progress=?")
            values.append(progress)
        if error_message is not None:
            fields.append("error_message=?")
            values.append(error_message)
        fields.append("updated_at=?")
        values.append(utc_now_iso())
        values.append(transfer_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE transfer_records SET {','.join(fields)} WHERE id=?", values)

    def list_transfers(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM transfer_records ORDER BY id DESC LIMIT ?", (limit,))]
