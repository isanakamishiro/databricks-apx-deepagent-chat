"""バックグラウンドエージェントジョブの状態とイベントバッファを管理するインメモリストア."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

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


class JobStore:
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
