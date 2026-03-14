"""UC Volumes 上のチャット履歴ストア.

Lakebase (PostgreSQL) を使わずに、UC Volumes の Files API を利用して
チャットメタデータとメッセージを JSON ファイルとして永続化する.

ストレージ構造::

    {volume_path}/.chat_history/
      {user_id}/
        _index.json              # チャットメタデータの配列
        {chat_id}/
          messages.json          # メッセージの配列
"""

from __future__ import annotations

import io
import json
import logging
from pathlib import PurePosixPath
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import DatabricksError, NotFound, ResourceDoesNotExist

logger = logging.getLogger(__name__)


class ChatHistoryStore:
    """UC Volumes を使ったチャット履歴の永続化.

    Args:
        volume_path: UC Volume のルートパス (例: ``/Volumes/catalog/schema/volume``).
        workspace_client: ``WorkspaceClient`` インスタンス.
    """

    def __init__(
        self,
        volume_path: str,
        workspace_client: WorkspaceClient | None = None,
    ) -> None:
        self._base = f"{volume_path.rstrip('/')}/.chat_history"
        self._w = workspace_client or WorkspaceClient()

    # ------------------------------------------------------------------
    # Low-level file helpers
    # ------------------------------------------------------------------

    @property
    def files(self):
        return self._w.files

    def _ensure_dir(self, path: str) -> None:
        parent = str(PurePosixPath(path).parent)
        try:
            self.files.create_directory(parent)
        except Exception:
            pass

    def _upload_json(self, path: str, data: Any) -> None:
        self._ensure_dir(path)
        content = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.files.upload(path, io.BytesIO(content), overwrite=True)

    def _download_json(self, path: str) -> Any | None:
        try:
            resp = self.files.download(path)
            return json.loads(resp.contents.read().decode("utf-8"))
        except (NotFound, ResourceDoesNotExist):
            return None
        except DatabricksError as e:
            logger.warning("_download_json failed for %s: %s", path, e)
            return None

    def _delete_file(self, path: str) -> None:
        try:
            self.files.delete(path)
        except (NotFound, ResourceDoesNotExist):
            pass

    def _delete_dir_recursive(self, path: str) -> None:
        try:
            entries = list(self.files.list_directory_contents(path))
        except (NotFound, ResourceDoesNotExist):
            return
        except DatabricksError as e:
            logger.warning("_delete_dir_recursive failed for %s: %s", path, e)
            return
        for entry in entries:
            if entry.path is None:
                continue
            if entry.is_directory:
                self._delete_dir_recursive(entry.path)
            else:
                self._delete_file(entry.path)
        try:
            self.files.delete_directory(path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _index_path(self, user_id: str) -> str:
        return f"{self._base}/{user_id}/_index.json"

    def _messages_path(self, user_id: str, chat_id: str) -> str:
        return f"{self._base}/{user_id}/{chat_id}/messages.json"

    def _chat_dir(self, user_id: str, chat_id: str) -> str:
        return f"{self._base}/{user_id}/{chat_id}"

    # ------------------------------------------------------------------
    # Index (chat metadata) operations
    # ------------------------------------------------------------------

    def _load_index(self, user_id: str) -> list[dict]:
        data = self._download_json(self._index_path(user_id))
        if data is None:
            return []
        if not isinstance(data, list):
            return []
        return data

    def _save_index(self, user_id: str, index: list[dict]) -> None:
        self._upload_json(self._index_path(user_id), index)

    # ------------------------------------------------------------------
    # Chat metadata CRUD
    # ------------------------------------------------------------------

    def save_chat(self, user_id: str, chat: dict) -> None:
        """チャットメタデータを保存 (upsert)."""
        index = self._load_index(user_id)
        chat_id = chat.get("id")
        # Update existing or append
        found = False
        for i, existing in enumerate(index):
            if existing.get("id") == chat_id:
                index[i] = {**existing, **chat}
                found = True
                break
        if not found:
            index.append(chat)
        self._save_index(user_id, index)

    def get_chats_by_user(
        self,
        user_id: str,
        limit: int = 20,
        ending_before: str | None = None,
    ) -> dict:
        """ユーザーの会話一覧を返す (createdAt 降順, ページネーション対応).

        Returns:
            ``{"chats": [...], "hasMore": bool}``
        """
        index = self._load_index(user_id)
        # Sort by createdAt descending
        index.sort(key=lambda c: c.get("createdAt", ""), reverse=True)

        if ending_before:
            # Find the chat and return only those created before it
            cutoff_idx = None
            for i, c in enumerate(index):
                if c.get("id") == ending_before:
                    cutoff_idx = i
                    break
            if cutoff_idx is not None:
                index = index[cutoff_idx + 1 :]
            else:
                index = []

        has_more = len(index) > limit
        chats = index[:limit] if has_more else index

        return {"chats": chats, "hasMore": has_more}

    def get_chat(self, user_id: str, chat_id: str) -> dict | None:
        """単一チャット取得."""
        index = self._load_index(user_id)
        for c in index:
            if c.get("id") == chat_id:
                return c
        return None

    def delete_chat(self, user_id: str, chat_id: str) -> None:
        """チャットとそのメッセージを削除."""
        # Remove from index
        index = self._load_index(user_id)
        index = [c for c in index if c.get("id") != chat_id]
        self._save_index(user_id, index)
        # Delete messages directory
        self._delete_dir_recursive(self._chat_dir(user_id, chat_id))

    # ------------------------------------------------------------------
    # Message CRUD
    # ------------------------------------------------------------------

    def save_messages(self, user_id: str, chat_id: str, messages: list[dict]) -> None:
        """メッセージを保存 (upsert)."""
        existing = self._load_messages(user_id, chat_id)
        existing_by_id = {m.get("id"): m for m in existing}

        for msg in messages:
            msg_id = msg.get("id")
            if msg_id and msg_id in existing_by_id:
                existing_by_id[msg_id].update(msg)
            else:
                existing.append(msg)
                if msg_id:
                    existing_by_id[msg_id] = msg

        self._upload_json(self._messages_path(user_id, chat_id), existing)

    def get_messages(self, user_id: str, chat_id: str) -> list[dict]:
        """チャットの全メッセージを返す (createdAt 昇順)."""
        messages = self._load_messages(user_id, chat_id)
        messages.sort(key=lambda m: m.get("createdAt", ""))
        return messages

    def _load_messages(self, user_id: str, chat_id: str) -> list[dict]:
        data = self._download_json(self._messages_path(user_id, chat_id))
        if data is None:
            return []
        if not isinstance(data, list):
            return []
        return data
