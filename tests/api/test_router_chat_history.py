"""チャット履歴 API ルーターテスト."""
from unittest.mock import MagicMock, patch


def test_list_chats_success(client, vol_headers):
    with patch("apx_deepagent_chat.backend.routers.chat_history.ChatHistoryStore") as MockStore:
        mock_store = MagicMock()
        MockStore.return_value = mock_store
        mock_store.get_chats_by_user.return_value = {"chats": [], "hasMore": False}
        response = client.get(
            "/api/chat-history", params={"user_id": "user1"}, headers=vol_headers
        )
    assert response.status_code == 200
    assert response.json() == {"chats": [], "hasMore": False}


def test_list_chats_missing_volume_path(client):
    response = client.get("/api/chat-history", params={"user_id": "user1"})
    assert response.status_code == 400


def test_list_chats_missing_user_id(client, vol_headers):
    response = client.get("/api/chat-history", headers=vol_headers)
    assert response.status_code == 422


def test_get_chat_success(client, vol_headers):
    with patch("apx_deepagent_chat.backend.routers.chat_history.ChatHistoryStore") as MockStore:
        mock_store = MagicMock()
        MockStore.return_value = mock_store
        mock_store.get_chat.return_value = {"id": "chat1", "title": "Test"}
        response = client.get(
            "/api/chat-history/chat1", params={"user_id": "user1"}, headers=vol_headers
        )
    assert response.status_code == 200
    assert response.json()["id"] == "chat1"


def test_get_chat_not_found(client, vol_headers):
    with patch("apx_deepagent_chat.backend.routers.chat_history.ChatHistoryStore") as MockStore:
        mock_store = MagicMock()
        MockStore.return_value = mock_store
        mock_store.get_chat.return_value = None
        response = client.get(
            "/api/chat-history/nonexistent", params={"user_id": "user1"}, headers=vol_headers
        )
    assert response.status_code == 404


def test_save_chat_success(client, vol_headers):
    with patch("apx_deepagent_chat.backend.routers.chat_history.ChatHistoryStore") as MockStore:
        mock_store = MagicMock()
        MockStore.return_value = mock_store
        response = client.post(
            "/api/chat-history",
            json={
                "id": "chat1",
                "userId": "user1",
                "title": "Test",
                "createdAt": "2024-01-01",
                "visibility": "private",
            },
            headers=vol_headers,
        )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_get_messages_success(client, vol_headers):
    with patch("apx_deepagent_chat.backend.routers.chat_history.ChatHistoryStore") as MockStore:
        mock_store = MagicMock()
        MockStore.return_value = mock_store
        mock_store.get_messages.return_value = [{"id": "msg1", "content": "hello"}]
        response = client.get(
            "/api/chat-history/chat1/messages",
            params={"user_id": "user1"},
            headers=vol_headers,
        )
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_messages_empty(client, vol_headers):
    with patch("apx_deepagent_chat.backend.routers.chat_history.ChatHistoryStore") as MockStore:
        mock_store = MagicMock()
        MockStore.return_value = mock_store
        mock_store.get_messages.return_value = []
        response = client.get(
            "/api/chat-history/chat1/messages",
            params={"user_id": "user1"},
            headers=vol_headers,
        )
    assert response.status_code == 200
    assert response.json() == []


def test_save_messages_success(client, vol_headers):
    with patch("apx_deepagent_chat.backend.routers.chat_history.ChatHistoryStore") as MockStore:
        mock_store = MagicMock()
        MockStore.return_value = mock_store
        response = client.post(
            "/api/chat-history/chat1/messages",
            json={"userId": "user1", "messages": [{"id": "msg1", "content": "hello"}]},
            headers=vol_headers,
        )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_delete_chat_success(client, vol_headers):
    with patch("apx_deepagent_chat.backend.routers.chat_history.ChatHistoryStore") as MockStore:
        mock_store = MagicMock()
        MockStore.return_value = mock_store
        response = client.delete(
            "/api/chat-history/chat1",
            params={"user_id": "user1"},
            headers=vol_headers,
        )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
