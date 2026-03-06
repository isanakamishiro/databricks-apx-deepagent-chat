import io
from pathlib import PurePosixPath
from typing import Optional

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound, ResourceDoesNotExist
from fastapi import File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from mlflow.genai.agent_server import AgentServer, setup_mlflow_git_based_version_tracking
from pydantic import BaseModel

# Import agent to register @invoke / @stream handlers with AgentServer
from . import agent  # noqa: F401
from .agent import AVAILABLE_MODELS, DEFAULT_MODEL
from .agent_utils import to_real_path, to_virtual_path
from .chat_history import ChatHistoryStore
from .core._config import AppConfig
from .core._static import CachedStaticFiles, add_not_found_handler
from .router import router as api_router
from .._metadata import dist_dir

# AgentServer provides /invocations and /responses endpoints
agent_server = AgentServer("ResponsesAgent")
app = agent_server.app


@app.on_event("startup")
async def startup():
    app.state.config = AppConfig()
    app.state.workspace_client = WorkspaceClient()


# Add existing APX API routes (/api/version, /api/current-user, etc.)
app.include_router(api_router)

# /responses ハンドラを /api/chat にも登録（dev プロキシは /api のみバックエンドへ転送するため）
from fastapi.routing import APIRoute  # noqa: E402

for route in list(app.routes):
    if isinstance(route, APIRoute) and route.path == "/responses":
        app.add_api_route("/api/chat", route.endpoint, methods=["POST"], operation_id="chat")
        break


# ---------------------------------------------------------------------------
# モデル設定エンドポイント
# ---------------------------------------------------------------------------


@app.get("/api/config")
async def get_config():
    return {
        "models": AVAILABLE_MODELS,
        "default_model": DEFAULT_MODEL,
    }


# ---------------------------------------------------------------------------
# チャット履歴 REST エンドポイント (UC Volumes バックエンド)
# ---------------------------------------------------------------------------

_history_stores: dict[str, ChatHistoryStore] = {}


def _get_history_store(volume_path: str) -> ChatHistoryStore:
    if volume_path not in _history_stores:
        _history_stores[volume_path] = ChatHistoryStore(
            volume_path=volume_path,
            workspace_client=WorkspaceClient(),
        )
    return _history_stores[volume_path]


def _extract_volume_path(request: Request) -> str:
    vp = request.headers.get("x-uc-volume-path", "")
    if not vp:
        raise HTTPException(status_code=400, detail="x-uc-volume-path header required")
    return vp


class SaveChatRequest(BaseModel):
    id: str
    userId: str
    title: str
    createdAt: str
    visibility: str = "private"


class SaveMessagesRequest(BaseModel):
    userId: str
    messages: list[dict]


@app.get("/api/chat-history")
async def list_chats(
    request: Request,
    user_id: str = Query(...),
    limit: int = Query(20),
    ending_before: Optional[str] = Query(None),
):
    volume_path = _extract_volume_path(request)
    store = _get_history_store(volume_path)
    return store.get_chats_by_user(user_id, limit, ending_before)


@app.get("/api/chat-history/{chat_id}")
async def get_chat(chat_id: str, request: Request, user_id: str = Query(...)):
    volume_path = _extract_volume_path(request)
    store = _get_history_store(volume_path)
    chat = store.get_chat(user_id, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@app.post("/api/chat-history")
async def save_chat(body: SaveChatRequest, request: Request):
    volume_path = _extract_volume_path(request)
    store = _get_history_store(volume_path)
    store.save_chat(body.userId, body.model_dump())
    return {"ok": True}


@app.get("/api/chat-history/{chat_id}/messages")
async def get_messages(chat_id: str, request: Request, user_id: str = Query(...)):
    volume_path = _extract_volume_path(request)
    store = _get_history_store(volume_path)
    return store.get_messages(user_id, chat_id)


@app.post("/api/chat-history/{chat_id}/messages")
async def save_messages_endpoint(
    chat_id: str, body: SaveMessagesRequest, request: Request
):
    volume_path = _extract_volume_path(request)
    store = _get_history_store(volume_path)
    store.save_messages(body.userId, chat_id, body.messages)
    return {"ok": True}


@app.delete("/api/chat-history/{chat_id}")
async def delete_chat(chat_id: str, request: Request, user_id: str = Query(...)):
    volume_path = _extract_volume_path(request)
    store = _get_history_store(volume_path)
    store.delete_chat(user_id, chat_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# ファイルエクスプローラ REST エンドポイント (UC Volumes)
# ---------------------------------------------------------------------------


def _get_workspace_client() -> WorkspaceClient:
    return WorkspaceClient()


@app.get("/api/files/list")
async def files_list(request: Request, path: str = Query("/")):
    volume_path = _extract_volume_path(request)
    real_path = to_real_path(volume_path, path)
    w = _get_workspace_client()

    try:
        entries = list(w.files.list_directory_contents(real_path))
    except (NotFound, ResourceDoesNotExist):
        raise HTTPException(status_code=404, detail="Directory not found")

    result = []
    for entry in entries:
        if entry.path is None:
            continue
        basename = PurePosixPath(entry.path).name
        if basename.startswith("."):
            continue
        is_dir = entry.is_directory or False
        virtual = to_virtual_path(volume_path, entry.path)
        item: dict = {
            "name": basename,
            "path": virtual + "/" if is_dir else virtual,
            "is_dir": is_dir,
        }
        if not is_dir and entry.file_size is not None:
            item["size"] = int(entry.file_size)
        if entry.last_modified is not None:
            item["modified_at"] = str(entry.last_modified)
        result.append(item)

    result.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    return result


@app.get("/api/files/download")
async def files_download(request: Request, path: str = Query(...)):
    volume_path = _extract_volume_path(request)
    real_path = to_real_path(volume_path, path)
    w = _get_workspace_client()

    try:
        resp = w.files.download(real_path)
    except (NotFound, ResourceDoesNotExist):
        raise HTTPException(status_code=404, detail="File not found")

    if resp.contents is None:
        raise HTTPException(status_code=404, detail="File not found")

    filename = PurePosixPath(path).name
    contents = resp.contents

    def iterfile():
        while True:
            chunk = contents.read(8192)
            if not chunk:
                break
            yield chunk

    return StreamingResponse(
        iterfile(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/files/upload")
async def files_upload(
    request: Request,
    path: str = Form(...),
    file: UploadFile = File(...),
):
    volume_path = _extract_volume_path(request)
    upload_dir = path if path.endswith("/") else path + "/"
    virtual_path = upload_dir + (file.filename or "upload")
    real_path = to_real_path(volume_path, virtual_path)
    w = _get_workspace_client()

    content = await file.read()
    try:
        w.files.upload(real_path, io.BytesIO(content), overwrite=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    return {"ok": True, "path": virtual_path}


class MkdirRequest(BaseModel):
    path: str  # 作成先の仮想パス (例: "/reports/2024/")


@app.post("/api/files/mkdir")
async def files_mkdir(body: MkdirRequest, request: Request):
    volume_path = _extract_volume_path(request)
    dir_path = body.path if body.path.endswith("/") else body.path + "/"
    real_path = to_real_path(volume_path, dir_path)
    w = _get_workspace_client()
    try:
        w.files.create_directory(real_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create directory: {e}")
    return {"ok": True, "path": dir_path}


def _delete_directory_recursive(w: WorkspaceClient, dir_path: str):
    """ディレクトリ内を再帰削除し、ディレクトリ自体も削除する."""
    try:
        entries = list(w.files.list_directory_contents(dir_path))
    except (NotFound, ResourceDoesNotExist):
        return
    for entry in entries:
        if entry.path is None:
            continue
        if entry.is_directory:
            _delete_directory_recursive(w, entry.path)
        else:
            w.files.delete(entry.path)
    w.files.delete_directory(dir_path)


@app.delete("/api/files/delete")
async def files_delete(
    request: Request, path: str = Query(...), is_dir: bool = Query(False)
):
    volume_path = _extract_volume_path(request)
    real_path = to_real_path(volume_path, path)
    w = _get_workspace_client()
    try:
        if is_dir:
            _delete_directory_recursive(w, real_path)
        else:
            w.files.delete(real_path)
    except (NotFound, ResourceDoesNotExist):
        raise HTTPException(status_code=404, detail="File or directory not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")
    return {"ok": True}


# Serve frontend static files
if dist_dir.exists():
    app.mount("/", CachedStaticFiles(directory=dist_dir, html=True))
    add_not_found_handler(app)

setup_mlflow_git_based_version_tracking()
