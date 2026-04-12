"""InterruptMiddleware のユニットテスト."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apx_deepagent_chat.backend.agent.middleware import InterruptMiddleware


# ─── ヘルパー ────────────────────────────────────────────────────────────────


def make_sync_store(interrupt: bool = False, subagent_interrupt: bool = False):
    """同期メソッドを持つ InMemoryJobStore 風のモック."""
    store = MagicMock()
    store.is_interrupt_requested.return_value = interrupt
    store.is_subagent_interrupt_requested.return_value = subagent_interrupt
    return store


def make_async_store(interrupt: bool = False, subagent_interrupt: bool = False):
    """コルーチンを返す SQLiteJobStore 風のモック."""
    store = MagicMock()
    store.is_interrupt_requested = AsyncMock(return_value=interrupt)
    store.is_subagent_interrupt_requested = AsyncMock(return_value=subagent_interrupt)
    return store


# ─── _check_interrupt ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_interrupt_sync_false():
    """同期ストアで割り込みなし → False."""
    store = make_sync_store(interrupt=False)
    mw = InterruptMiddleware(job_id="j1", job_store=store)
    assert await mw._check_interrupt() is False


@pytest.mark.asyncio
async def test_check_interrupt_sync_true():
    """同期ストアで割り込みあり → True."""
    store = make_sync_store(interrupt=True)
    mw = InterruptMiddleware(job_id="j1", job_store=store)
    assert await mw._check_interrupt() is True


@pytest.mark.asyncio
async def test_check_interrupt_async_false():
    """非同期ストアで割り込みなし → False."""
    store = make_async_store(interrupt=False)
    mw = InterruptMiddleware(job_id="j1", job_store=store)
    assert await mw._check_interrupt() is False


@pytest.mark.asyncio
async def test_check_interrupt_async_true():
    """非同期ストアで割り込みあり → True."""
    store = make_async_store(interrupt=True)
    mw = InterruptMiddleware(job_id="j1", job_store=store)
    assert await mw._check_interrupt() is True


@pytest.mark.asyncio
async def test_check_interrupt_subagent_sync():
    """check_subagent=True のとき subagent フラグを参照する（同期）."""
    store = make_sync_store(interrupt=False, subagent_interrupt=True)
    mw = InterruptMiddleware(job_id="j1", job_store=store, check_subagent=True)
    assert await mw._check_interrupt() is True
    store.is_subagent_interrupt_requested.assert_called_once_with("j1")
    store.is_interrupt_requested.assert_not_called()


@pytest.mark.asyncio
async def test_check_interrupt_subagent_async():
    """check_subagent=True のとき subagent フラグを参照する（非同期）."""
    store = make_async_store(interrupt=False, subagent_interrupt=True)
    mw = InterruptMiddleware(job_id="j1", job_store=store, check_subagent=True)
    assert await mw._check_interrupt() is True
    store.is_subagent_interrupt_requested.assert_called_once_with("j1")
    store.is_interrupt_requested.assert_not_called()


# ─── before_model（同期・キャッシュ参照）────────────────────────────────────


def test_before_model_no_interrupt_no_cache():
    """キャッシュ False → langgraph_interrupt を呼ばない."""
    store = make_sync_store()
    mw = InterruptMiddleware(job_id="j1", job_store=store)
    mw._cached_interrupt = False

    with patch(
        "apx_deepagent_chat.backend.agent.middleware.langgraph_interrupt"
    ) as mock_interrupt:
        mw.before_model(state=None, runtime=MagicMock())
        mock_interrupt.assert_not_called()


def test_before_model_interrupt_from_cache():
    """キャッシュ True → langgraph_interrupt を呼ぶ."""
    store = make_sync_store()
    mw = InterruptMiddleware(job_id="j1", job_store=store)
    mw._cached_interrupt = True

    with patch(
        "apx_deepagent_chat.backend.agent.middleware.langgraph_interrupt"
    ) as mock_interrupt:
        mw.before_model(state=None, runtime=MagicMock())
        mock_interrupt.assert_called_once_with({"reason": "user_interrupt"})


def test_before_model_does_not_call_store():
    """before_model は job_store を直接参照しない（キャッシュのみ使用）."""
    store = make_sync_store(interrupt=True)
    mw = InterruptMiddleware(job_id="j1", job_store=store)
    mw._cached_interrupt = False  # キャッシュは False

    with patch(
        "apx_deepagent_chat.backend.agent.middleware.langgraph_interrupt"
    ) as mock_interrupt:
        mw.before_model(state=None, runtime=MagicMock())
        # ストアが True を返しても、キャッシュが False なので呼ばれない
        mock_interrupt.assert_not_called()
    store.is_interrupt_requested.assert_not_called()


# ─── abefore_model（非同期・キャッシュ更新）─────────────────────────────────


@pytest.mark.asyncio
async def test_abefore_model_updates_cache_and_interrupts():
    """abefore_model: ストアが True → キャッシュ更新 & langgraph_interrupt 呼び出し."""
    store = make_sync_store(interrupt=True)
    mw = InterruptMiddleware(job_id="j1", job_store=store)
    assert mw._cached_interrupt is False

    with patch(
        "apx_deepagent_chat.backend.agent.middleware.langgraph_interrupt"
    ) as mock_interrupt:
        await mw.abefore_model(state=None, runtime=MagicMock())
        assert mw._cached_interrupt is True
        mock_interrupt.assert_called_once_with({"reason": "user_interrupt"})


@pytest.mark.asyncio
async def test_abefore_model_no_interrupt():
    """abefore_model: ストアが False → キャッシュ更新のみ、interrupt なし."""
    store = make_sync_store(interrupt=False)
    mw = InterruptMiddleware(job_id="j1", job_store=store)

    with patch(
        "apx_deepagent_chat.backend.agent.middleware.langgraph_interrupt"
    ) as mock_interrupt:
        await mw.abefore_model(state=None, runtime=MagicMock())
        assert mw._cached_interrupt is False
        mock_interrupt.assert_not_called()


@pytest.mark.asyncio
async def test_abefore_model_async_store():
    """abefore_model: 非同期ストアでも正しく動作する."""
    store = make_async_store(interrupt=True)
    mw = InterruptMiddleware(job_id="j1", job_store=store)

    with patch(
        "apx_deepagent_chat.backend.agent.middleware.langgraph_interrupt"
    ) as mock_interrupt:
        await mw.abefore_model(state=None, runtime=MagicMock())
        assert mw._cached_interrupt is True
        mock_interrupt.assert_called_once_with({"reason": "user_interrupt"})


# ─── aafter_model ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aafter_model_delegates_to_abefore_model():
    """aafter_model は abefore_model と同じ動作をする."""
    store = make_sync_store(interrupt=True)
    mw = InterruptMiddleware(job_id="j1", job_store=store)

    with patch(
        "apx_deepagent_chat.backend.agent.middleware.langgraph_interrupt"
    ) as mock_interrupt:
        await mw.aafter_model(state=None, runtime=MagicMock())
        assert mw._cached_interrupt is True
        mock_interrupt.assert_called_once_with({"reason": "user_interrupt"})


# ─── after_model ─────────────────────────────────────────────────────────────


def test_after_model_delegates_to_before_model():
    """after_model は before_model と同じ動作をする."""
    store = make_sync_store()
    mw = InterruptMiddleware(job_id="j1", job_store=store)
    mw._cached_interrupt = True

    with patch(
        "apx_deepagent_chat.backend.agent.middleware.langgraph_interrupt"
    ) as mock_interrupt:
        mw.after_model(state=None, runtime=MagicMock())
        mock_interrupt.assert_called_once_with({"reason": "user_interrupt"})
