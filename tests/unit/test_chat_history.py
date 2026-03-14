"""ChatHistoryStore ユニットテスト."""
import json

import pytest
from databricks.sdk.errors import NotFound
from databricks.sdk.errors.base import DatabricksError
from unittest.mock import MagicMock

from apx_deepagent_chat.backend.chat_history import ChatHistoryStore


@pytest.fixture
def mock_ws():
    ws = MagicMock()
    return ws


@pytest.fixture
def store(mock_ws):
    return ChatHistoryStore(volume_path="/Volumes/cat/schema/vol", workspace_client=mock_ws)


def _make_download_response(data):
    """JSON データを返すモックダウンロードレスポンスを生成."""
    content = json.dumps(data, ensure_ascii=False).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.contents.read.return_value = content
    return mock_resp


def _get_uploaded_data(mock_ws):
    """upload 呼び出しからアップロードされた JSON データを取得."""
    call_args = mock_ws.files.upload.call_args
    content_bytes = call_args[0][1].read()
    return json.loads(content_bytes.decode("utf-8"))


# ─── save_chat ────────────────────────────────────────────────────────────────


def test_save_chat_new(store, mock_ws):
    """新規チャットをインデックスに追加する."""
    mock_ws.files.download.side_effect = NotFound("not found")
    store.save_chat("user1", {"id": "chat1", "title": "Test Chat"})
    mock_ws.files.upload.assert_called_once()
    uploaded = _get_uploaded_data(mock_ws)
    assert len(uploaded) == 1
    assert uploaded[0]["id"] == "chat1"


def test_save_chat_upsert(store, mock_ws):
    """既存 ID のチャットを更新する."""
    existing = [{"id": "chat1", "title": "Old Title"}]
    mock_ws.files.download.return_value = _make_download_response(existing)
    store.save_chat("user1", {"id": "chat1", "title": "New Title"})
    uploaded = _get_uploaded_data(mock_ws)
    assert len(uploaded) == 1
    assert uploaded[0]["title"] == "New Title"


def test_save_chat_appends_new_to_existing(store, mock_ws):
    """既存インデックスに新規チャットを追加する."""
    existing = [{"id": "chat1", "title": "First"}]
    mock_ws.files.download.return_value = _make_download_response(existing)
    store.save_chat("user1", {"id": "chat2", "title": "Second"})
    uploaded = _get_uploaded_data(mock_ws)
    assert len(uploaded) == 2
    assert uploaded[1]["id"] == "chat2"


# ─── get_chats_by_user ────────────────────────────────────────────────────────


def test_get_chats_sorted_descending(store, mock_ws):
    """createdAt 降順でソートされる."""
    chats = [
        {"id": "chat1", "createdAt": "2024-01-01"},
        {"id": "chat2", "createdAt": "2024-01-03"},
        {"id": "chat3", "createdAt": "2024-01-02"},
    ]
    mock_ws.files.download.return_value = _make_download_response(chats)
    result = store.get_chats_by_user("user1")
    ids = [c["id"] for c in result["chats"]]
    assert ids == ["chat2", "chat3", "chat1"]


def test_get_chats_pagination_has_more(store, mock_ws):
    """limit+1 件以上で hasMore=True."""
    chats = [{"id": f"chat{i}", "createdAt": f"2024-01-{i:02d}"} for i in range(1, 25)]
    mock_ws.files.download.return_value = _make_download_response(chats)
    result = store.get_chats_by_user("user1", limit=20)
    assert result["hasMore"] is True
    assert len(result["chats"]) == 20


def test_get_chats_no_more(store, mock_ws):
    """limit 以内の件数では hasMore=False."""
    chats = [{"id": f"chat{i}", "createdAt": f"2024-01-{i:02d}"} for i in range(1, 6)]
    mock_ws.files.download.return_value = _make_download_response(chats)
    result = store.get_chats_by_user("user1", limit=20)
    assert result["hasMore"] is False
    assert len(result["chats"]) == 5


def test_get_chats_empty_index(store, mock_ws):
    """インデックスが存在しない場合は空リストを返す."""
    mock_ws.files.download.side_effect = NotFound("not found")
    result = store.get_chats_by_user("user1")
    assert result == {"chats": [], "hasMore": False}


# ─── get_chat ─────────────────────────────────────────────────────────────────


def test_get_chat_found(store, mock_ws):
    """指定 ID のチャットを返す."""
    chats = [{"id": "chat1", "title": "Test"}]
    mock_ws.files.download.return_value = _make_download_response(chats)
    result = store.get_chat("user1", "chat1")
    assert result == {"id": "chat1", "title": "Test"}


def test_get_chat_not_found(store, mock_ws):
    """存在しない ID は None を返す."""
    mock_ws.files.download.side_effect = NotFound("not found")
    result = store.get_chat("user1", "nonexistent")
    assert result is None


# ─── delete_chat ──────────────────────────────────────────────────────────────


def test_delete_chat_removes_from_index(store, mock_ws):
    """削除後、インデックスから該当チャットが除かれる."""
    existing = [{"id": "chat1"}, {"id": "chat2"}]
    mock_ws.files.download.return_value = _make_download_response(existing)
    mock_ws.files.list_directory_contents.side_effect = NotFound("not found")
    store.delete_chat("user1", "chat1")
    uploaded = _get_uploaded_data(mock_ws)
    assert len(uploaded) == 1
    assert uploaded[0]["id"] == "chat2"


# ─── save_messages / get_messages ─────────────────────────────────────────────


def test_save_messages_new(store, mock_ws):
    """新規メッセージをアップロードする."""
    mock_ws.files.download.side_effect = NotFound("not found")
    messages = [{"id": "msg1", "content": "Hello", "createdAt": "2024-01-01T00:00:00"}]
    store.save_messages("user1", "chat1", messages)
    mock_ws.files.upload.assert_called_once()
    uploaded = _get_uploaded_data(mock_ws)
    assert len(uploaded) == 1
    assert uploaded[0]["id"] == "msg1"


def test_save_messages_upsert_existing(store, mock_ws):
    """既存メッセージを更新する（id が一致する場合）."""
    existing = [{"id": "msg1", "content": "Old"}]
    mock_ws.files.download.return_value = _make_download_response(existing)
    store.save_messages("user1", "chat1", [{"id": "msg1", "content": "New"}])
    uploaded = _get_uploaded_data(mock_ws)
    assert len(uploaded) == 1
    assert uploaded[0]["content"] == "New"


# ─── _download_json ───────────────────────────────────────────────────────────


def test_download_json_returns_none_on_not_found(store, mock_ws):
    """NotFound 例外の場合は None を返す."""
    mock_ws.files.download.side_effect = NotFound("not found")
    result = store._download_json("/some/path")
    assert result is None


def test_download_json_returns_none_on_databricks_error(store, mock_ws):
    """DatabricksError の場合も None を返す."""
    mock_ws.files.download.side_effect = DatabricksError("error")
    result = store._download_json("/some/path")
    assert result is None


# ─── _upload_json ─────────────────────────────────────────────────────────────


def test_upload_json_encodes_utf8(store, mock_ws):
    """日本語を含むデータが UTF-8 でエンコードされる."""
    store._upload_json("/test/path.json", {"message": "日本語テスト"})
    call_args = mock_ws.files.upload.call_args
    content_bytes = call_args[0][1].read()
    decoded = json.loads(content_bytes.decode("utf-8"))
    assert decoded["message"] == "日本語テスト"
