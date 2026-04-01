# これらは環境変数等の設定を鑑みて先にロードする
import asyncio
import json
import logging
import signal
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Literal
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
from .agent.job_store import JobStore
from .agent.uc_checkpointer import UCBundleCheckpointer
from .core._base import LifespanDependency
from .core._factory import _chain_dep_lifespans
from .core._static import CachedStaticFiles, add_not_found_handler
from .core.dependencies import Dependencies
from .routers import router as api_router

logging.getLogger("mlflow.utils.autologging_utils").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

# ─── JobStore シングルトン ────────────────────────────────────────────────────

_job_store = JobStore()


# ─── 定期クリーンアップ ───────────────────────────────────────────────────────


async def _periodic_cleanup(store: JobStore, interval: int = 300) -> None:
    """interval 秒ごとに完了ジョブをクリーンアップする."""
    while True:
        await asyncio.sleep(interval)
        store.cleanup()


# ─── バックグラウンドエージェントタスク ──────────────────────────────────────


async def _run_agent_background(job_id: str, body: dict) -> None:
    """エージェントをバックグラウンドで実行し、イベントを JobStore に蓄積する.

    HITL 承認が必要な場合は tool.approval_required イベントを発行し、
    ユーザー応答を待ってから Command(resume=...) でエージェントを再開する。
    """
    job = _job_store.get_job(job_id)
    if job is None:
        return
    job.status = "running"
    # InterruptMiddleware が job_id を参照できるよう custom_inputs に注入する
    body.setdefault("custom_inputs", {})["job_id"] = job_id
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
                        _job_store.append_event(job_id, event_type, data)
                finally:
                    await gen.aclose()

                if hitl_requests is None:
                    # 正常完了
                    _job_store.mark_done(job_id)
                    break

                # HITL 承認待ち: tool.approval_required を配信して待機
                _job_store.append_event(
                    job_id, "tool.approval_required", {"requests": hitl_requests}
                )
                decisions = await _job_store.wait_for_approval(job_id)

                if decisions is None:
                    # ユーザーが割り込み (スレッド切り替え等) → 終了
                    _job_store.mark_done(job_id)
                    break

                # 再開: resume_decisions を custom_inputs に注入して再呼び出し
                current_body = dict(body)
                current_body["custom_inputs"] = dict(body.get("custom_inputs", {}))
                current_body["custom_inputs"]["resume_decisions"] = decisions

            if last_data is not None:
                span.set_outputs(last_data)
    except asyncio.CancelledError:
        _job_store.mark_error(job_id, "Interrupted by server shutdown")
        raise
    except Exception:
        logger.exception("Background agent error for job %s", job_id)
        _job_store.mark_error(job_id, "Agent processing failed")


# ─── SSE ジェネレータ ─────────────────────────────────────────────────────────

# Databricks Apps の 120 秒 HTTP タイムアウトより先に接続をクローズする秒数
_SSE_CLOSE_AFTER = 100.0


async def _generate_sse(
    job_id: str, last_event_id: int, request: Request
) -> AsyncGenerator[str, None]:
    """SSE イベントをストリームする。Last-Event-ID から resume をサポートする."""
    job = _job_store.get_job(job_id)
    if job is None:
        yield f"event: error\ndata: {json.dumps({'error': 'Job not found', 'type': 'error'})}\n\n"
        return

    start_time = asyncio.get_event_loop().time()
    event_index = last_event_id + 1  # 次に送るべき event_id

    while True:
        # クライアント切断チェック
        if await request.is_disconnected():
            break

        # 100 秒経過したらフロントエンドに再接続を促してクローズ
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed >= _SSE_CLOSE_AFTER:
            yield f"event: stream.timeout\ndata: {json.dumps({'last_event_id': event_index - 1})}\n\n"
            break

        # 保留中のイベントをすべて送信
        while event_index < len(job.events):
            ev = job.events[event_index]
            data_str = json.dumps(ev.data)
            yield f"id: {ev.id}\nevent: {ev.event_type}\ndata: {data_str}\n\n"
            event_index += 1

        # ジョブ完了チェック
        if job.status == "done":
            break
        if job.status == "error":
            error_msg = job.error or "Unknown error"
            yield f"event: error\ndata: {json.dumps({'error': error_msg, 'type': 'error'})}\n\n"
            break

        # 残り時間を計算（これを超えて待機しない）
        remaining = _SSE_CLOSE_AFTER - (asyncio.get_event_loop().time() - start_time)
        if remaining <= 0:
            continue

        # 新イベント待機（race condition 安全パターン）
        job.notify.clear()
        # clear と wait の間に到着したイベントをキャッチ
        if event_index < len(job.events):
            continue
        if job.status in ("done", "error"):
            continue

        # min(30秒, 残り時間) でタイムアウト待機、タイムアウト時は keepalive コメントを送信
        try:
            await asyncio.wait_for(job.notify.wait(), timeout=min(30.0, remaining))
        except asyncio.TimeoutError:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= _SSE_CLOSE_AFTER:
                yield f"event: stream.timeout\ndata: {json.dumps({'last_event_id': event_index - 1})}\n\n"
                break
            yield ": keepalive\n\n"


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

    logger.debug(" ---- Checkpoint ---")

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

    logger.debug(f" tool_results: {tool_results}")

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
                    call_id = block.get("id", "")
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

    logger.debug(result)

    return result


class ChatStartResponse(BaseModel):
    job_id: str


class ChatInterruptResponse(BaseModel):
    ok: bool


from .models import ChatApproveRequest, ChatApproveResponse  # noqa: E402

# ─── アプリケーション生成 ─────────────────────────────────────────────────────


def create_server_app() -> FastAPI:
    # AgentServer provides /invocations and /responses endpoints
    agent_server = AgentServer("ResponsesAgent")
    app = agent_server.app

    # Optionally, set up MLflow git-based version tracking
    # to correspond your agent's traces to a specific git commit
    setup_mlflow_git_based_version_tracking()

    # LifespanDependency._registry から全 deps を compose して app に適用
    # (create_app() と同じパターン。app.router.lifespan_context は起動前であれば設定可能)
    _all_deps = [dep() for dep in LifespanDependency._registry]

    @asynccontextmanager
    async def _composed_lifespan(app):
        cleanup_task = asyncio.create_task(_periodic_cleanup(_job_store))

        async def _graceful_shutdown() -> None:
            """SIGTERM 受信時に実行中ジョブをキャンセルし MLflow トレースをフラッシュする."""
            tasks_to_cancel = [
                job.task
                for job in _job_store.all_jobs()
                if job.task and not job.task.done()
            ]
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
        _current_obo_token.set(obo_token)
        tok_sp = _injected_sp_ws_client.set(sp_client)
        tok_js = _injected_job_store.set(_job_store)

        body = await request.json()
        job_id = str(uuid4())
        job = _job_store.create_job(job_id)

        # ContextVar がコピーされた状態でバックグラウンドタスクを起動
        task = asyncio.create_task(_run_agent_background(job_id, body))
        job.task = task

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
        _job_store.request_interrupt(job_id, deep=deep)
        return ChatInterruptResponse(ok=True)

    # ─── POST /api/chat/approve/{job_id} ─────────────────────────────────────
    @app.post(
        "/api/chat/approve/{job_id}",
        operation_id="chatApprove",
        response_model=ChatApproveResponse,
    )
    async def chat_approve(job_id: str, body: ChatApproveRequest):
        """HITL ツール承認の決定を受け取り、待機中のエージェントを再開する."""
        _job_store.set_approval(job_id, [d.model_dump() for d in body.decisions])
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
            _generate_sse(job_id, last_event_id, request),
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
