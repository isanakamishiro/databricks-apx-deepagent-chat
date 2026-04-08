"""WAL モード SQLite を使ったマルチプロセス対応 JobStore."""

import asyncio
import json
import logging
import os
import sqlite3
import time
from typing import AsyncGenerator, Optional

from apx_deepagent_chat.backend.agent.job_store import JobEvent

logger = logging.getLogger(__name__)

_CREATE_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id                       TEXT    PRIMARY KEY,
    status                       TEXT    NOT NULL DEFAULT 'pending',
    error                        TEXT,
    created_at                   REAL    NOT NULL,
    updated_at                   REAL    NOT NULL,
    worker_pid                   INTEGER,
    interrupt_requested          INTEGER NOT NULL DEFAULT 0,
    subagent_interrupt_requested INTEGER NOT NULL DEFAULT 0,
    approval_decisions           TEXT
)
"""

_CREATE_JOB_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS job_events (
    rowid      INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     TEXT    NOT NULL,
    event_seq  INTEGER NOT NULL,
    event_type TEXT    NOT NULL,
    data       TEXT    NOT NULL,
    created_at REAL    NOT NULL
)
"""

_CREATE_JOB_EVENTS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_job_events ON job_events(job_id, event_seq)
"""


class _NoCloseConnection:
    """close() を no-op にしてラップした sqlite3.Connection プロキシ.

    :memory: データベースでは close() すると DB が消えてしまうため使用する。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def execute(self, *args, **kwargs):  # type: ignore[override]
        return self._conn.execute(*args, **kwargs)

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        # no-op: :memory: 接続は維持する
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class SQLiteJobStore:
    """WAL モードの SQLite を使ったジョブストア。マルチプロセス（uvicorn --workers N）対応."""

    def __init__(self, db_path: str = "/tmp/apx_jobs.db") -> None:
        self._db_path = db_path
        self._local_tasks: dict[str, asyncio.Task] = {}
        # :memory: の場合は接続を使い回す（新しい接続を開くたびに空のDBになるため）
        self._shared_conn: Optional[sqlite3.Connection] = None

    def _connect(self) -> sqlite3.Connection:
        """WAL モードの接続を返す（呼び出し元が close() すること）.

        :memory: の場合は共有接続を返す（close() は no-op になる）。
        ファイルパスの場合は毎回新しい接続を開く。
        """
        if self._db_path == ":memory:":
            if self._shared_conn is None:
                conn = sqlite3.connect(":memory:", check_same_thread=False)
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.row_factory = sqlite3.Row
                self._shared_conn = conn
            return _NoCloseConnection(self._shared_conn)  # type: ignore[return-value]

        conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _create_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute(_CREATE_JOBS_TABLE)
            conn.execute(_CREATE_JOB_EVENTS_TABLE)
            conn.execute(_CREATE_JOB_EVENTS_INDEX)
            conn.commit()
        finally:
            conn.close()

    async def initialize(self) -> None:
        """テーブルとインデックスを作成する。lifespan で呼ぶ。"""
        await asyncio.to_thread(self._create_schema)
        logger.info("SQLiteJobStore initialized at %s", self._db_path)

    def _do_recover(self) -> None:
        stale_threshold = time.time() - 300  # 5 minutes
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'error', error = 'Recovered from stale running state', updated_at = ?
                WHERE status = 'running' AND updated_at < ?
                """,
                (time.time(), stale_threshold),
            )
            conn.commit()
        finally:
            conn.close()

    async def recover_stale_jobs(self) -> None:
        """起動時リカバリ: status='running' かつ updated_at が5分以上前のジョブを 'error' に更新する."""
        await asyncio.to_thread(self._do_recover)

    def _do_create_job(self, job_id: str) -> None:
        now = time.time()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO jobs
                    (job_id, status, created_at, updated_at, worker_pid,
                     interrupt_requested, subagent_interrupt_requested)
                VALUES (?, 'pending', ?, ?, ?, 0, 0)
                """,
                (job_id, now, now, os.getpid()),
            )
            conn.commit()
        finally:
            conn.close()

    async def create_job(self, job_id: str) -> None:
        await asyncio.to_thread(self._do_create_job, job_id)

    def _do_mark_running(self, job_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE jobs SET status = 'running', updated_at = ? WHERE job_id = ?",
                (time.time(), job_id),
            )
            conn.commit()
        finally:
            conn.close()

    async def mark_running(self, job_id: str) -> None:
        """ジョブの status を 'running' に更新する."""
        await asyncio.to_thread(self._do_mark_running, job_id)

    def _do_mark_done(self, job_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE jobs SET status = 'done', updated_at = ? WHERE job_id = ?",
                (time.time(), job_id),
            )
            conn.commit()
        finally:
            conn.close()

    async def mark_done(self, job_id: str) -> None:
        await asyncio.to_thread(self._do_mark_done, job_id)

    def _do_mark_error(self, job_id: str, error: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE jobs SET status = 'error', error = ?, updated_at = ? WHERE job_id = ?",
                (error, time.time(), job_id),
            )
            conn.commit()
        finally:
            conn.close()

    async def mark_error(self, job_id: str, error: str) -> None:
        await asyncio.to_thread(self._do_mark_error, job_id, error)

    def _do_append_event(self, job_id: str, event_type: str, data: dict) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT COALESCE(MAX(event_seq) + 1, 0) FROM job_events WHERE job_id = ?",
                (job_id,),
            )
            event_seq: int = cur.fetchone()[0]
            conn.execute(
                """
                INSERT INTO job_events (job_id, event_seq, event_type, data, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, event_seq, event_type, json.dumps(data), time.time()),
            )
            conn.commit()
            return event_seq
        finally:
            conn.close()

    async def append_event(self, job_id: str, event_type: str, data: dict) -> int:
        """イベントを追加し event_seq を返す."""
        return await asyncio.to_thread(self._do_append_event, job_id, event_type, data)

    def _do_request_interrupt(self, job_id: str, deep: bool) -> None:
        conn = self._connect()
        try:
            if deep:
                conn.execute(
                    """
                    UPDATE jobs
                    SET interrupt_requested = 1, subagent_interrupt_requested = 1, updated_at = ?
                    WHERE job_id = ?
                    """,
                    (time.time(), job_id),
                )
            else:
                conn.execute(
                    "UPDATE jobs SET interrupt_requested = 1, updated_at = ? WHERE job_id = ?",
                    (time.time(), job_id),
                )
            conn.commit()
        finally:
            conn.close()

    async def request_interrupt(self, job_id: str, deep: bool = False) -> None:
        await asyncio.to_thread(self._do_request_interrupt, job_id, deep)

    def _do_is_interrupt_requested(self, job_id: str) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT interrupt_requested FROM jobs WHERE job_id = ?", (job_id,)
            )
            row = cur.fetchone()
            return bool(row["interrupt_requested"]) if row else False
        finally:
            conn.close()

    async def is_interrupt_requested(self, job_id: str) -> bool:
        return await asyncio.to_thread(self._do_is_interrupt_requested, job_id)

    def _do_is_subagent_interrupt_requested(self, job_id: str) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT subagent_interrupt_requested FROM jobs WHERE job_id = ?", (job_id,)
            )
            row = cur.fetchone()
            return bool(row["subagent_interrupt_requested"]) if row else False
        finally:
            conn.close()

    async def is_subagent_interrupt_requested(self, job_id: str) -> bool:
        return await asyncio.to_thread(self._do_is_subagent_interrupt_requested, job_id)

    def _get_approval_row(self, job_id: str) -> Optional[sqlite3.Row]:
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT approval_decisions, interrupt_requested FROM jobs WHERE job_id = ?",
                (job_id,),
            )
            return cur.fetchone()
        finally:
            conn.close()

    async def wait_for_approval(self, job_id: str) -> Optional[list[dict]]:
        """承認決定を待機する。割り込みが来たら None を返す。"""
        while True:
            row = await asyncio.to_thread(self._get_approval_row, job_id)
            if row is None:
                return None  # Job 消滅
            if row["approval_decisions"] is not None:
                return json.loads(row["approval_decisions"])
            if row["interrupt_requested"]:
                return None  # 割り込み
            await asyncio.sleep(1.0)

    def _do_set_approval(self, job_id: str, decisions: list[dict]) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE jobs SET approval_decisions = ?, updated_at = ? WHERE job_id = ?",
                (json.dumps(decisions), time.time(), job_id),
            )
            conn.commit()
        finally:
            conn.close()

    async def set_approval(self, job_id: str, decisions: list[dict]) -> None:
        await asyncio.to_thread(self._do_set_approval, job_id, decisions)

    def _fetch_events(self, job_id: str, from_seq: int) -> list[sqlite3.Row]:
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                SELECT event_seq, event_type, data
                FROM job_events
                WHERE job_id = ? AND event_seq >= ?
                ORDER BY event_seq ASC
                """,
                (job_id, from_seq),
            )
            return cur.fetchall()
        finally:
            conn.close()

    def _get_status_row(self, job_id: str) -> Optional[sqlite3.Row]:
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT status, error FROM jobs WHERE job_id = ?", (job_id,)
            )
            return cur.fetchone()
        finally:
            conn.close()

    async def iter_events(
        self, job_id: str, from_seq: int = 0
    ) -> AsyncGenerator[JobEvent, None]:
        """200ms ごとに新イベントをポーリングして yield する."""
        while True:
            rows = await asyncio.to_thread(self._fetch_events, job_id, from_seq)
            for row in rows:
                yield JobEvent(
                    id=row["event_seq"],
                    event_type=row["event_type"],
                    data=json.loads(row["data"]),
                )
                from_seq = row["event_seq"] + 1

            status_row = await asyncio.to_thread(self._get_status_row, job_id)
            if status_row is None:
                return  # Job not found
            if status_row["status"] == "error":
                error_msg = status_row["error"] or "Unknown error"
                yield JobEvent(
                    id=-1,
                    event_type="error",
                    data={"error": error_msg, "type": "error"},
                )
                return
            if status_row["status"] == "done":
                return

            await asyncio.sleep(0.2)

    def register_task(self, job_id: str, task: asyncio.Task) -> None:
        """このWorkerが起動したタスクを登録する."""
        self._local_tasks[job_id] = task

    def running_tasks(self) -> list[asyncio.Task]:
        """実行中のローカルタスクを返す."""
        return [t for t in self._local_tasks.values() if not t.done()]

    def _do_cleanup(self) -> None:
        cutoff = time.time() - 600  # 10 minutes
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT job_id FROM jobs WHERE status IN ('done', 'error') AND updated_at < ?",
                (cutoff,),
            )
            job_ids = [row["job_id"] for row in cur.fetchall()]
            if job_ids:
                placeholders = ",".join("?" * len(job_ids))
                conn.execute(
                    f"DELETE FROM job_events WHERE job_id IN ({placeholders})", job_ids
                )
                conn.execute(
                    f"DELETE FROM jobs WHERE job_id IN ({placeholders})", job_ids
                )
                conn.commit()
                logger.info("Cleaned up %d completed jobs from SQLite", len(job_ids))
        finally:
            conn.close()

    async def cleanup(self) -> None:
        """10分以上前に完了したジョブとそのイベントを削除する."""
        await asyncio.to_thread(self._do_cleanup)
