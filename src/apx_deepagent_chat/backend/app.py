# これらは環境変数等の設定を鑑みて先にロードする
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.routing import APIRoute

from .core._base import LifespanDependency
from .core._factory import _chain_dep_lifespans
from .core._static import CachedStaticFiles, add_not_found_handler
from .core.dependencies import Dependencies
from .router import router as api_router
from .._metadata import dist_dir
from .agent_utils import _injected_user_ws_client, _injected_sp_ws_client

# normal import

import logging

from mlflow.genai.agent_server import AgentServer, setup_mlflow_git_based_version_tracking


# Import agent to register @invoke / @stream handlers with AgentServer
from . import agent  # noqa: F401

logging.getLogger("mlflow.utils.autologging_utils").setLevel(logging.ERROR)


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
        async with _chain_dep_lifespans(_all_deps, app):
            yield

    app.router.lifespan_context = _composed_lifespan

    # Add existing APX API routes (/api/version, /api/current-user, etc.)
    app.include_router(api_router)

    # /responses ハンドラを /api/chat にも登録（dev プロキシは /api のみバックエンドへ転送するため）
    _responses_handler = next(
        (r.endpoint for r in app.routes if isinstance(r, APIRoute) and r.path == "/responses"),
        None,
    )

    if _responses_handler:
        _handler = _responses_handler  # Pyright narrowing: non-None capture

        @app.post("/api/chat", operation_id="chat")
        async def chat_endpoint(
            request: Request,
            user_client: Dependencies.UserClient,
            sp_client: Dependencies.Client,
        ):
            tok_user = _injected_user_ws_client.set(user_client)
            tok_sp = _injected_sp_ws_client.set(sp_client)
            try:
                return await _handler(request)
            finally:
                _injected_user_ws_client.reset(tok_user)
                _injected_sp_ws_client.reset(tok_sp)

    # Serve frontend static files
    if dist_dir.exists():
        app.mount("/", CachedStaticFiles(directory=dist_dir, html=True))
        add_not_found_handler(app)

    return app


app = create_server_app()
