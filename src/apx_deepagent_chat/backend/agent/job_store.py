"""バックグラウンドエージェントジョブの状態とイベントバッファを管理するストア."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from apx_deepagent_chat.backend.core._config import AppConfig

logger = logging.getLogger(__name__)


@dataclass
class JobEvent:
    id: int
    event_type: str
    data: dict


@dataclass
class Job:
    job_id: str
    status: str = "pending"  # pending | running | done | error
    events: list[JobEvent] = field(default_factory=list)
    notify: asyncio.Event = field(default_factory=asyncio.Event)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = None
    task: Optional[asyncio.Task] = None
    interrupt_requested: bool = False
    subagent_interrupt_requested: bool = False
    # HITL tool approval
    approval_event: asyncio.Event = field(default_factory=asyncio.Event)
    approval_decisions: Optional[list[dict]] = None


class InMemoryJobStore:
    """ジョブ状態とイベントバッファのインメモリストア."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def create_job(self, job_id: str) -> Job:
        job = Job(job_id=job_id)
        self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def append_event(self, job_id: str, event_type: str, data: dict) -> int:
        """イベントを追加し、event_id を返す。待機中の SSE ジェネレータに通知する."""
        job = self._jobs[job_id]
        event_id = len(job.events)
        job.events.append(JobEvent(id=event_id, event_type=event_type, data=data))
        job.notify.set()
        return event_id

    def request_interrupt(self, job_id: str, deep: bool = False) -> None:
        """指定ジョブに割り込みフラグをセットする。deep=True のときはサブエージェントも対象にする."""
        job = self._jobs.get(job_id)
        if job:
            job.interrupt_requested = True
            if deep:
                job.subagent_interrupt_requested = True

    def is_interrupt_requested(self, job_id: str) -> bool:
        """指定ジョブの割り込みフラグを返す."""
        job = self._jobs.get(job_id)
        return job.interrupt_requested if job else False

    def is_subagent_interrupt_requested(self, job_id: str) -> bool:
        """指定ジョブのサブエージェント割り込みフラグを返す."""
        job = self._jobs.get(job_id)
        return job.subagent_interrupt_requested if job else False

    async def wait_for_approval(self, job_id: str) -> Optional[list[dict]]:
        """ツール承認を待機する。割り込みが要求された場合は None を返す."""
        job = self._jobs.get(job_id)
        if job is None:
            return None
        job.approval_event.clear()
        while True:
            try:
                await asyncio.wait_for(job.approval_event.wait(), timeout=1.0)
                return job.approval_decisions or []
            except asyncio.TimeoutError:
                if job.interrupt_requested:
                    return None

    def set_approval(self, job_id: str, decisions: list[dict]) -> None:
        """フロントエンドからの承認決定を受け取り、待機中のタスクを再開する."""
        job = self._jobs.get(job_id)
        if job:
            job.approval_decisions = decisions
            job.approval_event.set()

    def mark_done(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.status = "done"
            job.notify.set()

    def mark_error(self, job_id: str, error: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.status = "error"
            job.error = error
            job.notify.set()

    def all_jobs(self) -> list[Job]:
        """全ジョブを返す."""
        return list(self._jobs.values())

    def register_task(self, job_id: str, task: asyncio.Task) -> None:
        """バックグラウンドタスクを Job に関連付ける（graceful shutdown 用）."""
        job = self._jobs.get(job_id)
        if job:
            job.task = task

    def running_tasks(self) -> list[asyncio.Task]:
        """実行中の全タスクを返す（graceful shutdown で cancel するため）."""
        return [
            job.task
            for job in self._jobs.values()
            if job.task and not job.task.done()
        ]

    def cleanup(self) -> None:
        """10分以上前に完了したジョブを削除する."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        to_delete = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status in ("done", "error") and job.created_at < cutoff
        ]
        for job_id in to_delete:
            del self._jobs[job_id]
        if to_delete:
            logger.info("Cleaned up %d completed jobs", len(to_delete))


# Keep JobStore as an alias for backwards compatibility
JobStore = InMemoryJobStore


def create_job_store(config: "AppConfig") -> Any:
    """設定に基づいて適切な JobStore を返す。

    JOB_STORE_BACKEND=sqlite のとき SQLiteJobStore を返す。
    デフォルト（memory）では InMemoryJobStore を返す。
    """
    backend = getattr(config, "job_store_backend", "memory")
    if backend == "sqlite":
        from .sqlite_job_store import SQLiteJobStore  # type: ignore[import-not-found]

        db_path = getattr(config, "job_store_db_path", "/tmp/apx_jobs.db")
        return SQLiteJobStore(db_path=db_path)
    return InMemoryJobStore()
