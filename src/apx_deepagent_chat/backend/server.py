# これらは環境変数等の設定を鑑みて先にロードする
from .core._config import AppConfig
from .core._static import CachedStaticFiles, add_not_found_handler
from .router import router as api_router
from .._metadata import dist_dir

# normal import

import logging

from mlflow.genai.agent_server import AgentServer, setup_mlflow_git_based_version_tracking


# Import agent to register @invoke / @stream handlers with AgentServer
from . import agent  # noqa: F401


logging.getLogger("mlflow.utils.autologging_utils").setLevel(logging.ERROR)

# AgentServer provides /invocations and /responses endpoints
agent_server = AgentServer("ResponsesAgent")
app = agent_server.app

# Optionally, set up MLflow git-based version tracking
# to correspond your agent's traces to a specific git commit
setup_mlflow_git_based_version_tracking()


@app.on_event("startup")
async def startup():
    app.state.config = AppConfig()


# Add existing APX API routes (/api/version, /api/current-user, etc.)
app.include_router(api_router)

# /responses ハンドラを /api/chat にも登録（dev プロキシは /api のみバックエンドへ転送するため）
from fastapi.routing import APIRoute  # noqa: E402

for route in list(app.routes):
    if isinstance(route, APIRoute) and route.path == "/responses":
        app.add_api_route("/api/chat", route.endpoint, methods=["POST"], operation_id="chat")
        break


# Serve frontend static files
if dist_dir.exists():
    app.mount("/", CachedStaticFiles(directory=dist_dir, html=True))
    add_not_found_handler(app)
