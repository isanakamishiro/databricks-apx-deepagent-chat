"""InMemoryJobStore と create_job_store() のユニットテスト."""

import asyncio
from unittest.mock import MagicMock

import pytest

from apx_deepagent_chat.backend.agent.job_store import InMemoryJobStore, JobStore, create_job_store


# ─── InMemoryJobStore ────────────────────────────────────────────────────────


def test_inmemory_is_alias_for_job_store():
    """JobStore は InMemoryJobStore の後方互換エイリアスであること."""
    assert JobStore is InMemoryJobStore


def test_create_job():
    store = InMemoryJobStore()
    job = store.create_job("job-1")
    assert job.job_id == "job-1"
    assert job.status == "pending"


def test_get_job_existing():
    store = InMemoryJobStore()
    store.create_job("job-1")
    job = store.get_job("job-1")
    assert job is not None
    assert job.job_id == "job-1"


def test_get_job_missing():
    store = InMemoryJobStore()
    assert store.get_job("nonexistent") is None


def test_append_event():
    store = InMemoryJobStore()
    store.create_job("job-1")
    event_id = store.append_event("job-1", "message", {"text": "hello"})
    assert event_id == 0
    job = store.get_job("job-1")
    assert job is not None
    assert len(job.events) == 1
    assert job.events[0].event_type == "message"


def test_mark_done():
    store = InMemoryJobStore()
    store.create_job("job-1")
    store.mark_done("job-1")
    job = store.get_job("job-1")
    assert job is not None
    assert job.status == "done"


def test_mark_error():
    store = InMemoryJobStore()
    store.create_job("job-1")
    store.mark_error("job-1", "something went wrong")
    job = store.get_job("job-1")
    assert job is not None
    assert job.status == "error"
    assert job.error == "something went wrong"


def test_request_interrupt():
    store = InMemoryJobStore()
    store.create_job("job-1")
    assert not store.is_interrupt_requested("job-1")
    store.request_interrupt("job-1")
    assert store.is_interrupt_requested("job-1")
    assert not store.is_subagent_interrupt_requested("job-1")


def test_request_deep_interrupt():
    store = InMemoryJobStore()
    store.create_job("job-1")
    store.request_interrupt("job-1", deep=True)
    assert store.is_interrupt_requested("job-1")
    assert store.is_subagent_interrupt_requested("job-1")


# ─── register_task / running_tasks ──────────────────────────────────────────


def test_register_task_associates_task_with_job():
    store = InMemoryJobStore()
    store.create_job("job-1")

    async def dummy():
        await asyncio.sleep(0)

    loop = asyncio.new_event_loop()
    try:
        task = loop.create_task(dummy())
        store.register_task("job-1", task)
        job = store.get_job("job-1")
        assert job is not None
        assert job.task is task
    finally:
        loop.close()


def test_register_task_ignores_missing_job():
    """存在しない job_id を渡しても例外が発生しないこと."""
    store = InMemoryJobStore()
    task = MagicMock(spec=asyncio.Task)
    store.register_task("nonexistent", task)  # should not raise


def test_running_tasks_returns_non_done_tasks():
    store = InMemoryJobStore()
    store.create_job("job-1")
    store.create_job("job-2")

    done_task = MagicMock(spec=asyncio.Task)
    done_task.done.return_value = True

    running_task = MagicMock(spec=asyncio.Task)
    running_task.done.return_value = False

    store.register_task("job-1", done_task)
    store.register_task("job-2", running_task)

    result = store.running_tasks()
    assert result == [running_task]


def test_running_tasks_excludes_jobs_without_task():
    store = InMemoryJobStore()
    store.create_job("job-1")
    assert store.running_tasks() == []


# ─── create_job_store ────────────────────────────────────────────────────────


def test_create_job_store_default_returns_inmemory():
    config = MagicMock()
    config.job_store_backend = "memory"
    store = create_job_store(config)
    assert isinstance(store, InMemoryJobStore)


def test_create_job_store_missing_attr_defaults_to_memory():
    """job_store_backend 属性がない config でも InMemoryJobStore を返すこと."""
    config = MagicMock(spec=[])  # no attributes
    store = create_job_store(config)
    assert isinstance(store, InMemoryJobStore)
