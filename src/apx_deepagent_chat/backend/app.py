import asyncio
import json
import logging
import signal
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Literal
from uuid import uuid4

import mlflow
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from mlflow.genai.agent_server import (
    AgentServer,
    setup_mlflow_git_based_version_tracking,
)
from mlflow.types.responses import ResponsesAgentRequest
from pydantic import BaseModel

from .._metadata import dist_dir
from .agent import (  # also registers @invoke / @stream handlers
    _current_obo_token,
    _injected_job_store,
    _injected_sp_ws_client,
    stream_handler,
)
from .agent.job_store import create_job_store
from .agent.uc_checkpointer import UCBundleCheckpointer
from .core._base import LifespanDependency
from .core._factory import _chain_dep_lifespans
from .core._static import CachedStaticFiles, add_not_found_handler
from .core.dependencies import Dependencies
from .routers import router as api_router

logging.getLogger("mlflow.utils.autologging_utils").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

# ─── ユーティリティ ──────────────────────────────────────────────────────────


async def _maybe_await(result: Any) -> Any:
    """同期・非同期両方の戻り値を透過的に await する."""
    if asyncio.iscoroutine(result):
        return await result
    return result


# ─── 定期クリーンアップ ───────────────────────────────────────────────────────


async def _periodic_cleanup(store: Any, interval: int = 300) -> None:
    """interval 秒ごとに完了ジョブをクリーンアップする."""
    while True:
        await asyncio.sleep(interval)
        await _maybe_await(store.cleanup())


# ─── バックグラウンドエージェントタスク ──────────────────────────────────────


async def _run_agent_background(job_id: str, body: dict, store: Any) -> None:
    """エージェントをバックグラウンドで実行し、イベントを JobStore に蓄積する.

    HITL 承認が必要な場合は tool.approval_required イベントを発行し、
    ユーザー応答を待ってから Command(resume=...) でエージェントを再開する。
    """
    await store.mark_running(job_id)
    # InterruptMiddleware が job_id を参照できるよう custom_inputs に注入する
    body = {**body, "custom_inputs": {**body.get("custom_inputs", {}), "job_id": job_id}}
    try:
        with mlflow.start_span(name="run_agent", span_type="AGENT") as span:
            input_msgs = body.get("input", [])
            span_input = body
            for message in reversed(input_msgs):
                if message.get("role") == "user":
                    span_input = message.get("content", "")
                    break
            span.set_inputs(span_input)

            current_body = body
            last_data = None

            while True:
                hitl_requests = None
                agent_request = ResponsesAgentRequest(**current_body)
                gen = stream_handler(agent_request)
                try:
                    async for event in gen:
                        event_type = str(event.type) if hasattr(event, "type") else ""
                        if event_type == "__tool_approval_interrupt__":
                            # HITL 割り込み: tool.approval_required をフロントへ配信
                            hitl_requests = (event.custom_outputs or {}).get(
                                "requests", []
                            )
                            break
                        data = event.model_dump(mode="json")
                        last_data = data
                        await _maybe_await(
                            store.append_event(job_id, event_type, data)
                        )
                finally:
                    await gen.aclose()

                if hitl_requests is None:
                    await _maybe_await(store.mark_done(job_id))
                    break

                await _maybe_await(
                    store.append_event(
                        job_id, "tool.approval_required", {"requests": hitl_requests}
                    )
                )
                decisions = await store.wait_for_approval(job_id)

                if decisions is None:
                    # ユーザーが割り込み (スレッド切り替え等) → 終了
                    await _maybe_await(store.mark_done(job_id))
                    break

                current_body = {
                    **body,
                    "custom_inputs": {
                        **body.get("custom_inputs", {}),
                        "resume_decisions": decisions,
                    },
                }

            if last_data is not None:
                span.set_outputs(last_data)
    except asyncio.CancelledError:
        await _maybe_await(
            store.mark_error(job_id, "Interrupted by server shutdown")
        )
        raise
    except Exception:
        logger.exception("Background agent error for job %s", job_id)
        await _maybe_await(store.mark_error(job_id, "Agent processing failed"))


# ─── SSE ジェネレータ ─────────────────────────────────────────────────────────

# Databricks Apps の 120 秒 HTTP タイムアウトより先に接続をクローズする秒数
_SSE_CLOSE_AFTER = 100.0


async def _generate_sse(
    job_id: str, last_event_id: int, request: Request, store: Any
) -> AsyncGenerator[str, None]:
    """SSE イベントをストリームする。Last-Event-ID から resume をサポートする."""
    loop = asyncio.get_event_loop()
    start_time = loop.time()
    from_seq = last_event_id + 1
    keepalive_sent_at = start_time

    async for ev in store.iter_events(job_id, from_seq=from_seq):
        if await request.is_disconnected():
            break

        now = loop.time()
        if now - start_time >= _SSE_CLOSE_AFTER:
            yield f"event: stream.timeout\ndata: {json.dumps({'last_event_id': from_seq - 1})}\n\n"
            break

        if now - keepalive_sent_at >= 30.0:
            yield ": keepalive\n\n"
            keepalive_sent_at = now

        data_str = json.dumps(ev.data)
        yield f"id: {ev.id}\nevent: {ev.event_type}\ndata: {data_str}\n\n"
        from_seq = ev.id + 1
        keepalive_sent_at = loop.time()


# ─── レスポンスモデル ─────────────────────────────────────────────────────────


class ThreadStateResponse(BaseModel):
    status: Literal["interrupted", "completed", "not_found"]
    messages: list[dict]


def _messages_to_frontend_format(lc_messages: list) -> list[dict]:
    """LangChain メッセージを UI 表示用の ChatMessage 形式に変換する.

    ツール呼び出し (tool_use)、ツール結果 (tool_result)、thinking ブロックを
    フロントエンドの blocks / thinking フィールドに変換する。

    連続する AIMessage（HumanMessage 間）はストリーミング時の挙動に合わせて
    1つの assistant メッセージにマージする。
    """
    import json as _json

    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    # ToolMessage を tool_call_id でインデックス化（AIMessage の tool_use に対応させる）
    tool_results: dict[str, str] = {}
    for msg in lc_messages:
        if isinstance(msg, ToolMessage):
            call_id = getattr(msg, "tool_call_id", "") or ""
            if call_id:
                raw = msg.content
                tool_results[call_id] = (
                    raw if isinstance(raw, str) else _json.dumps(raw)
                )

    result: list[dict] = []

    # 連続 AIMessage をまとめるアキュムレータ
    asst_thinking: str = ""
    asst_blocks: list[dict] = []
    asst_text: str = ""

    def flush_assistant() -> None:
        nonlocal asst_thinking, asst_blocks, asst_text
        if asst_blocks or asst_thinking:
            msg_out: dict = {
                "role": "assistant",
                "content": asst_text,
                "blocks": asst_blocks,
            }
            if asst_thinking:
                msg_out["thinking"] = asst_thinking
            result.append(msg_out)
        asst_thinking = ""
        asst_text = ""
        asst_blocks = []

    for msg in lc_messages:
        if isinstance(msg, HumanMessage):
            flush_assistant()
            content = msg.content if isinstance(msg.content, str) else ""
            if content:
                result.append({"role": "user", "content": content})

        elif isinstance(msg, AIMessage):
            # content_blocks を使う: Anthropic 固有形式を標準形式に変換済み
            # - "reasoning" type + "reasoning" フィールド (≒ thinking)
            # - "tool_call" type + "args" dict + "id" フィールド (≒ tool_use)
            # - "text" type + "text" フィールド

            for block in msg.content_blocks:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type", "")

                if block_type == "reasoning":
                    thinking_text = block.get("reasoning", "")
                    if thinking_text:
                        asst_thinking += thinking_text

                elif block_type == "text":
                    text = block.get("text", "")
                    if text:
                        asst_text += text
                        asst_blocks.append({"type": "text", "content": text})

                elif block_type == "tool_call":
                    call_id = block.get("id") or ""
                    name = block.get("name", "")
                    args = block.get("args", {})
                    arguments = (
                        _json.dumps(args) if isinstance(args, dict) else str(args)
                    )
                    result_str = tool_results.get(call_id)
                    state = (
                        "output-available"
                        if result_str is not None
                        else "input-available"
                    )
                    tool_block: dict = {
                        "type": "tool",
                        "callId": call_id,
                        "name": name,
                        "arguments": arguments,
                        "state": state,
                    }
                    if result_str is not None:
                        tool_block["result"] = result_str
                    asst_blocks.append(tool_block)

        # ToolMessage は AIMessage ブロック内に吸収済みのためスキップ

    flush_assistant()

    return result


class ChatStartResponse(BaseModel):
    job_id: str


class ChatInterruptResponse(BaseModel):
    ok: bool


from .models import ChatApproveRequest, ChatApproveResponse  # noqa: E402

# ─── アプリケーション生成 ─────────────────────────────────────────────────────


def create_server_app() -> FastAPI:
    from .core._config import AppConfig

    config = AppConfig()
    _job_store = create_job_store(config)

    # AgentServer provides /invocations and /responses endpoints
    agent_server = AgentServer("ResponsesAgent")
    app = agent_server.app

    setup_mlflow_git_based_version_tracking()

    # LifespanDependency._registry から全 deps を compose して app に適用
    # (create_app() と同じパターン。app.router.lifespan_context は起動前であれば設定可能)
    _all_deps = [dep() for dep in LifespanDependency._registry]

    @asynccontextmanager
    async def _composed_lifespan(app):
        # SQLiteJobStore の場合、起動時にテーブル作成とリカバリを実行する
        if hasattr(_job_store, "initialize"):
            await _job_store.initialize()
        if hasattr(_job_store, "recover_stale_jobs"):
            await _job_store.recover_stale_jobs()

        cleanup_task = asyncio.create_task(_periodic_cleanup(_job_store))

        async def _graceful_shutdown() -> None:
            """SIGTERM 受信時に実行中ジョブをキャンセルし MLflow トレースをフラッシュする."""
            tasks_to_cancel = _job_store.running_tasks()
            for task in tasks_to_cancel:
                task.cancel()
            if tasks_to_cancel:
                await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
            try:
                mlflow.flush_async_logging()
            except Exception:
                logger.exception("MLflow flush error during shutdown")

        loop = asyncio.get_event_loop()
        loop.add_signal_handler(
            signal.SIGTERM,
            lambda: asyncio.ensure_future(_graceful_shutdown()),
        )

        try:
            async with _chain_dep_lifespans(_all_deps, app):
                yield
        finally:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass

    app.router.lifespan_context = _composed_lifespan

    # Add existing APX API routes (/api/version, /api/current-user, etc.)
    app.include_router(api_router)

    # ─── POST /api/chat/start ─────────────────────────────────────────────────
    @app.post(
        "/api/chat/start", operation_id="chatStart", response_model=ChatStartResponse
    )
    async def chat_start(
        request: Request,
        headers: Dependencies.Headers,
        sp_client: Dependencies.Client,
    ):
        """エージェント処理をバックグラウンドで開始し、job_id を即座に返す."""
        obo_token = headers.token.get_secret_value() if headers.token else None
        token_obo = _current_obo_token.set(obo_token)
        tok_sp = _injected_sp_ws_client.set(sp_client)
        tok_js = _injected_job_store.set(_job_store)

        body = await request.json()
        job_id = str(uuid4())

        try:
            await _maybe_await(_job_store.create_job(job_id))
            task = asyncio.create_task(_run_agent_background(job_id, body, _job_store))
            _job_store.register_task(job_id, task)
        finally:
            _current_obo_token.reset(token_obo)
            _injected_sp_ws_client.reset(tok_sp)
            _injected_job_store.reset(tok_js)

        return ChatStartResponse(job_id=job_id)

    # ─── POST /api/chat/interrupt/{job_id} ───────────────────────────────────
    @app.post(
        "/api/chat/interrupt/{job_id}",
        operation_id="chatInterrupt",
        response_model=ChatInterruptResponse,
    )
    async def chat_interrupt(job_id: str, deep: bool = False):
        """指定ジョブに割り込みフラグをセットする。deep=True のときはサブエージェントも停止する（停止ボタン用）."""
        await _maybe_await(_job_store.request_interrupt(job_id, deep=deep))
        return ChatInterruptResponse(ok=True)

    # ─── POST /api/chat/approve/{job_id} ─────────────────────────────────────
    @app.post(
        "/api/chat/approve/{job_id}",
        operation_id="chatApprove",
        response_model=ChatApproveResponse,
    )
    async def chat_approve(job_id: str, body: ChatApproveRequest):
        """HITL ツール承認の決定を受け取り、待機中のエージェントを再開する."""
        await _maybe_await(
            _job_store.set_approval(job_id, [d.model_dump() for d in body.decisions])
        )
        return ChatApproveResponse(ok=True)

    # ─── GET /api/chat/stream/{job_id} ───────────────────────────────────────
    @app.get("/api/chat/stream/{job_id}")
    async def chat_stream(job_id: str, request: Request):
        """SSE で job のイベントをストリームする。Last-Event-ID ヘッダで resume に対応."""
        raw = request.headers.get("last-event-id", "-1")
        try:
            last_event_id = int(raw)
        except ValueError:
            last_event_id = -1

        return StreamingResponse(
            _generate_sse(job_id, last_event_id, request, _job_store),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ─── GET /api/chat/thread/{thread_id}/state ──────────────────────────────
    @app.get(
        "/api/chat/thread/{thread_id}/state",
        operation_id="chatThreadState",
        response_model=ThreadStateResponse,
    )
    async def chat_thread_state(
        thread_id: str,
        volume_path: Dependencies.VolumePath,
        user_ws: Dependencies.UserClient,
    ):
        """チェックポイントからスレッドの最終状態を取得する."""
        ckptr = UCBundleCheckpointer(
            volume_path=volume_path,
            thread_id=thread_id,
            workspace_client=user_ws,
        )
        try:
            await asyncio.to_thread(ckptr.load_bundle)
        except Exception:
            logger.exception("チェックポイント読み込み失敗: thread=%s", thread_id)
            return ThreadStateResponse(status="not_found", messages=[])

        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        tup = ckptr.get_tuple(config)  # type: ignore[arg-type]

        if tup is None:
            return ThreadStateResponse(status="not_found", messages=[])

        # __interrupt__ channel への pending write が存在すれば中断済み
        is_interrupted = bool(
            tup.pending_writes
            and any(channel == "__interrupt__" for _, channel, _ in tup.pending_writes)
        )

        raw_messages = tup.checkpoint.get("channel_values", {}).get("messages", [])
        simplified = _messages_to_frontend_format(raw_messages)

        return ThreadStateResponse(
            status="interrupted" if is_interrupted else "completed",
            messages=simplified,
        )

    # Serve frontend static files
    if dist_dir.exists():
        app.mount("/", CachedStaticFiles(directory=dist_dir, html=True))
        add_not_found_handler(app)

    return app


app = create_server_app()
