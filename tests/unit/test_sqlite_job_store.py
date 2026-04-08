"""SQLiteJobStore のユニットテスト."""

import asyncio
import time

import pytest
import pytest_asyncio

from apx_deepagent_chat.backend.agent.sqlite_job_store import SQLiteJobStore


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def store():
    """インメモリ SQLite を使った SQLiteJobStore インスタンスを返す."""
    s = SQLiteJobStore(db_path=":memory:")
    await s.initialize()
    return s


# ─── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_initialize_creates_tables(store: SQLiteJobStore):
    """initialize() 後にテーブルが存在すること."""
    conn = store._connect()
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('jobs', 'job_events')"
        )
        tables = {row["name"] for row in cur.fetchall()}
        assert "jobs" in tables
        assert "job_events" in tables
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_create_job(store: SQLiteJobStore):
    """Job が作成され status='pending' であること."""
    await store.create_job("job-1")
    conn = store._connect()
    try:
        cur = conn.execute("SELECT * FROM jobs WHERE job_id = ?", ("job-1",))
        row = cur.fetchone()
        assert row is not None
        assert row["status"] == "pending"
        assert row["interrupt_requested"] == 0
        assert row["subagent_interrupt_requested"] == 0
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_append_event_and_iter_events(store: SQLiteJobStore):
    """イベントを追加して iter_events で取得できること."""
    await store.create_job("job-1")
    seq0 = await store.append_event("job-1", "message", {"text": "hello"})
    seq1 = await store.append_event("job-1", "message", {"text": "world"})

    assert seq0 == 0
    assert seq1 == 1

    await store.mark_done("job-1")

    events = []
    async for event in store.iter_events("job-1"):
        events.append(event)

    assert len(events) == 2
    assert events[0].id == 0
    assert events[0].event_type == "message"
    assert events[0].data == {"text": "hello"}
    assert events[1].id == 1
    assert events[1].data == {"text": "world"}


@pytest.mark.asyncio
async def test_mark_done_stops_iter_events(store: SQLiteJobStore):
    """mark_done() 後 iter_events が終了すること."""
    await store.create_job("job-1")
    await store.mark_done("job-1")

    events = []
    async for event in store.iter_events("job-1"):
        events.append(event)

    # No events and the generator should have terminated (not hang)
    assert events == []


@pytest.mark.asyncio
async def test_mark_error_yields_error_event(store: SQLiteJobStore):
    """mark_error() 後 iter_events がエラーイベントを yield すること."""
    await store.create_job("job-1")
    await store.mark_error("job-1", "something went wrong")

    events = []
    async for event in store.iter_events("job-1"):
        events.append(event)

    assert len(events) == 1
    assert events[0].event_type == "error"
    assert events[0].data["error"] == "something went wrong"
    assert events[0].id == -1


@pytest.mark.asyncio
async def test_request_interrupt(store: SQLiteJobStore):
    """interrupt フラグが設定されること."""
    await store.create_job("job-1")
    assert not await store.is_interrupt_requested("job-1")
    assert not await store.is_subagent_interrupt_requested("job-1")

    await store.request_interrupt("job-1")

    assert await store.is_interrupt_requested("job-1")
    assert not await store.is_subagent_interrupt_requested("job-1")


@pytest.mark.asyncio
async def test_request_deep_interrupt(store: SQLiteJobStore):
    """subagent フラグも設定されること."""
    await store.create_job("job-1")
    await store.request_interrupt("job-1", deep=True)

    assert await store.is_interrupt_requested("job-1")
    assert await store.is_subagent_interrupt_requested("job-1")


@pytest.mark.asyncio
async def test_set_and_wait_for_approval(store: SQLiteJobStore):
    """承認フローが動作すること."""
    await store.create_job("job-1")
    decisions = [{"tool": "bash", "approved": True}]

    # set_approval を非同期に実行し、wait_for_approval が決定を返すことを確認
    async def set_after_delay():
        await asyncio.sleep(0.1)
        await store.set_approval("job-1", decisions)

    setter_task = asyncio.create_task(set_after_delay())
    result = await store.wait_for_approval("job-1")
    await setter_task

    assert result == decisions


@pytest.mark.asyncio
async def test_wait_for_approval_returns_none_on_interrupt(store: SQLiteJobStore):
    """割り込みで None を返すこと."""
    await store.create_job("job-1")

    async def interrupt_after_delay():
        await asyncio.sleep(0.1)
        await store.request_interrupt("job-1")

    interrupt_task = asyncio.create_task(interrupt_after_delay())
    result = await store.wait_for_approval("job-1")
    await interrupt_task

    assert result is None


@pytest.mark.asyncio
async def test_recover_stale_jobs(store: SQLiteJobStore):
    """古い running ジョブが error になること."""
    await store.create_job("job-stale")

    # Force status to 'running' with an old updated_at
    stale_time = time.time() - 400  # 6+ minutes ago
    conn = store._connect()
    try:
        conn.execute(
            "UPDATE jobs SET status = 'running', updated_at = ? WHERE job_id = ?",
            (stale_time, "job-stale"),
        )
        conn.commit()
    finally:
        conn.close()

    await store.recover_stale_jobs()

    conn = store._connect()
    try:
        cur = conn.execute("SELECT status FROM jobs WHERE job_id = ?", ("job-stale",))
        row = cur.fetchone()
        assert row["status"] == "error"
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_recover_stale_jobs_does_not_affect_recent_running(store: SQLiteJobStore):
    """最近の running ジョブは recover_stale_jobs で変更されないこと."""
    await store.create_job("job-recent")

    # Force status to 'running' with a recent updated_at
    conn = store._connect()
    try:
        conn.execute(
            "UPDATE jobs SET status = 'running', updated_at = ? WHERE job_id = ?",
            (time.time(), "job-recent"),
        )
        conn.commit()
    finally:
        conn.close()

    await store.recover_stale_jobs()

    conn = store._connect()
    try:
        cur = conn.execute("SELECT status FROM jobs WHERE job_id = ?", ("job-recent",))
        row = cur.fetchone()
        assert row["status"] == "running"
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_cleanup_removes_old_completed_jobs(store: SQLiteJobStore):
    """10分超の完了 Job が削除されること."""
    await store.create_job("job-old")
    await store.append_event("job-old", "message", {"text": "hi"})
    await store.mark_done("job-old")

    # Backdate updated_at to more than 10 minutes ago
    old_time = time.time() - 700  # 11+ minutes ago
    conn = store._connect()
    try:
        conn.execute(
            "UPDATE jobs SET updated_at = ? WHERE job_id = ?",
            (old_time, "job-old"),
        )
        conn.commit()
    finally:
        conn.close()

    await store.cleanup()

    conn = store._connect()
    try:
        cur = conn.execute("SELECT COUNT(*) FROM jobs WHERE job_id = ?", ("job-old",))
        assert cur.fetchone()[0] == 0

        cur = conn.execute("SELECT COUNT(*) FROM job_events WHERE job_id = ?", ("job-old",))
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_cleanup_keeps_recent_completed_jobs(store: SQLiteJobStore):
    """最近完了したジョブは cleanup で削除されないこと."""
    await store.create_job("job-recent-done")
    await store.mark_done("job-recent-done")

    await store.cleanup()

    conn = store._connect()
    try:
        cur = conn.execute("SELECT COUNT(*) FROM jobs WHERE job_id = ?", ("job-recent-done",))
        assert cur.fetchone()[0] == 1
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_register_and_running_tasks(store: SQLiteJobStore):
    """タスク管理が動作すること."""
    await store.create_job("job-1")
    await store.create_job("job-2")

    async def dummy():
        await asyncio.sleep(100)

    loop = asyncio.get_event_loop()
    running_task = loop.create_task(dummy())
    try:
        store.register_task("job-1", running_task)

        tasks = store.running_tasks()
        assert running_task in tasks
        assert len(tasks) == 1
    finally:
        running_task.cancel()
        try:
            await running_task
        except asyncio.CancelledError:
            pass

    # After cancellation, the task is done and should not appear in running_tasks
    tasks_after = store.running_tasks()
    assert running_task not in tasks_after
