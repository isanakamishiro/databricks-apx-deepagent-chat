from typing import Annotated, Optional, TypeAlias

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..chat_history import ChatHistoryStore
from ..core import Dependencies

import logging
logger = logging.getLogger(__name__)

router = APIRouter()


def _get_history_store(
    volume_path: Dependencies.VolumePath,
    ws: Dependencies.UserClient,
) -> ChatHistoryStore:
    # OBO トークンはリクエストごとに異なるため、キャッシュせず毎回生成する
    return ChatHistoryStore(volume_path=volume_path, workspace_client=ws)


HistoryStore: TypeAlias = Annotated[ChatHistoryStore, Depends(_get_history_store)]


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
    store: HistoryStore,
    user_id: str = Query(...),
    limit: int = Query(20),
    ending_before: Optional[str] = Query(None),
):
    return store.get_chats_by_user(user_id, limit, ending_before)


@router.get("/chat-history/{chat_id}", operation_id="getChat")
async def get_chat(chat_id: str, store: HistoryStore, user_id: str = Query(...)):
    chat = store.get_chat(user_id, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@router.post("/chat-history", operation_id="saveChat")
async def save_chat(body: SaveChatRequest, store: HistoryStore):
    store.save_chat(body.userId, body.model_dump())
    return {"ok": True}


@router.get("/chat-history/{chat_id}/messages", operation_id="getMessages")
async def get_messages(chat_id: str, store: HistoryStore, user_id: str = Query(...)):
    return store.get_messages(user_id, chat_id)


@router.post("/chat-history/{chat_id}/messages", operation_id="saveMessages")
async def save_messages_endpoint(
    chat_id: str, body: SaveMessagesRequest, store: HistoryStore
):
    store.save_messages(body.userId, chat_id, body.messages)
    return {"ok": True}


@router.delete("/chat-history/{chat_id}", operation_id="deleteChat")
async def delete_chat(chat_id: str, store: HistoryStore, user_id: str = Query(...)):
    store.delete_chat(user_id, chat_id)
    return {"ok": True}
