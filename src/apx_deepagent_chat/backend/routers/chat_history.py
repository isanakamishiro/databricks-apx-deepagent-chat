from typing import Optional

from databricks.sdk import WorkspaceClient
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from ..chat_history import ChatHistoryStore
from ..core import Dependencies

router = APIRouter()

_history_stores: dict[str, ChatHistoryStore] = {}


def _get_history_store(volume_path: str, ws: WorkspaceClient) -> ChatHistoryStore:
    if volume_path not in _history_stores:
        _history_stores[volume_path] = ChatHistoryStore(
            volume_path=volume_path,
            workspace_client=ws,
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


@router.get("/chat-history", operation_id="listChats")
async def list_chats(
    request: Request,
    ws: Dependencies.UserClient,
    user_id: str = Query(...),
    limit: int = Query(20),
    ending_before: Optional[str] = Query(None),
):
    volume_path = _extract_volume_path(request)
    store = _get_history_store(volume_path, ws)
    return store.get_chats_by_user(user_id, limit, ending_before)


@router.get("/chat-history/{chat_id}", operation_id="getChat")
async def get_chat(chat_id: str, request: Request, ws: Dependencies.UserClient, user_id: str = Query(...)):
    volume_path = _extract_volume_path(request)
    store = _get_history_store(volume_path, ws)
    chat = store.get_chat(user_id, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@router.post("/chat-history", operation_id="saveChat")
async def save_chat(body: SaveChatRequest, request: Request, ws: Dependencies.UserClient):
    volume_path = _extract_volume_path(request)
    store = _get_history_store(volume_path, ws)
    store.save_chat(body.userId, body.model_dump())
    return {"ok": True}


@router.get("/chat-history/{chat_id}/messages", operation_id="getMessages")
async def get_messages(chat_id: str, request: Request, ws: Dependencies.UserClient, user_id: str = Query(...)):
    volume_path = _extract_volume_path(request)
    store = _get_history_store(volume_path, ws)
    return store.get_messages(user_id, chat_id)


@router.post("/chat-history/{chat_id}/messages", operation_id="saveMessages")
async def save_messages_endpoint(
    chat_id: str, body: SaveMessagesRequest, request: Request, ws: Dependencies.UserClient
):
    volume_path = _extract_volume_path(request)
    store = _get_history_store(volume_path, ws)
    store.save_messages(body.userId, chat_id, body.messages)
    return {"ok": True}


@router.delete("/chat-history/{chat_id}", operation_id="deleteChat")
async def delete_chat(chat_id: str, request: Request, ws: Dependencies.UserClient, user_id: str = Query(...)):
    volume_path = _extract_volume_path(request)
    store = _get_history_store(volume_path, ws)
    store.delete_chat(user_id, chat_id)
    return {"ok": True}
