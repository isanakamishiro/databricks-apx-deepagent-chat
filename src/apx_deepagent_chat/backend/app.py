# これらは環境変数等の設定を鑑みて先にロードする
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
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
    _injected_sp_ws_client,
    streaming,
)
from .agent.job_store import JobStore
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


async def _periodic_cleanup(store: JobStore, interval: int = 60) -> None:
    """interval 秒ごとに完了ジョブをクリーンアップする."""
    while True:
        await asyncio.sleep(interval)
        store.cleanup()


# ─── バックグラウンドエージェントタスク ──────────────────────────────────────


# @mlflow.trace(name="run_agent", span_type="AGENT")
async def _run_agent_background(job_id: str, body: dict) -> None:
    """エージェントをバックグラウンドで実行し、イベントを JobStore に蓄積する."""

    job = _job_store.get_job(job_id)
    if job is None:
        return
    job.status = "running"
    try:
        with mlflow.start_span(name="run_agent", span_type="AGENT") as span:
            # MLflow Tracing の span に入力内容をタグ付けする。タグは後から MLflow UI で検索やフィルタリングに使える。
            input = body.get("input", [])
            span_input = body
            # Find the last human message
            for message in reversed(input):
                if message.get("role") == "user":
                    span_input = message.get("content", "")
                    break
            span.set_inputs(span_input)

            agent_request = ResponsesAgentRequest(**body)
            async for event in streaming(agent_request):
                event_type = str(event.type) if hasattr(event, "type") else ""
                data = event.model_dump(mode="json")
                _job_store.append_event(job_id, event_type, data)
            _job_store.mark_done(job_id)
    except Exception:
        logger.exception("Background agent error for job %s", job_id)
        _job_store.mark_error(job_id, "Agent processing failed")


# ─── SSE ジェネレータ ─────────────────────────────────────────────────────────


async def _generate_sse(
    job_id: str, last_event_id: int, request: Request
) -> AsyncGenerator[str, None]:
    """SSE イベントをストリームする。Last-Event-ID から resume をサポートする."""
    job = _job_store.get_job(job_id)
    if job is None:
        yield f"event: error\ndata: {json.dumps({'error': 'Job not found', 'type': 'error'})}\n\n"
        return

    event_index = last_event_id + 1  # 次に送るべき event_id

    while True:
        # クライアント切断チェック
        if await request.is_disconnected():
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

        # 新イベント待機（race condition 安全パターン）
        job.notify.clear()
        # clear と wait の間に到着したイベントをキャッチ
        if event_index < len(job.events):
            continue
        if job.status in ("done", "error"):
            continue

        # 30秒タイムアウトで待機、タイムアウト時は keepalive コメントを送信
        try:
            await asyncio.wait_for(job.notify.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            yield ": keepalive\n\n"


# ─── レスポンスモデル ─────────────────────────────────────────────────────────


class ChatStartResponse(BaseModel):
    job_id: str


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

        body = await request.json()
        job_id = str(uuid4())
        job = _job_store.create_job(job_id)

        # ContextVar がコピーされた状態でバックグラウンドタスクを起動
        task = asyncio.create_task(_run_agent_background(job_id, body))
        job.task = task

        _injected_sp_ws_client.reset(tok_sp)

        return ChatStartResponse(job_id=job_id)

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

    # Serve frontend static files
    if dist_dir.exists():
        app.mount("/", CachedStaticFiles(directory=dist_dir, html=True))
        add_not_found_handler(app)

    return app


app = create_server_app()
