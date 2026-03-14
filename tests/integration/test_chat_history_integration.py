"""ChatHistoryStore 統合テスト: 実 Databricks 環境で実行."""
import pytest

from apx_deepagent_chat.backend.chat_history import ChatHistoryStore

pytestmark = pytest.mark.integration


def test_save_and_load_chat(real_ws, temp_volume_path):
    """save_chat → get_chat の整合性を検証する."""
    store = ChatHistoryStore(volume_path=temp_volume_path, workspace_client=real_ws)
    chat = {
        "id": "int-chat1",
        "userId": "test-user",
        "title": "Integration Test",
        "createdAt": "2024-01-01T00:00:00",
    }
    store.save_chat("test-user", chat)
    loaded = store.get_chat("test-user", "int-chat1")
    assert loaded is not None
    assert loaded["id"] == "int-chat1"
    assert loaded["title"] == "Integration Test"


def test_save_and_load_messages(real_ws, temp_volume_path):
    """save_messages → get_messages の整合性を検証する."""
    store = ChatHistoryStore(volume_path=temp_volume_path, workspace_client=real_ws)
    chat = {
        "id": "int-chat2",
        "userId": "test-user",
        "title": "Messages Test",
        "createdAt": "2024-01-02T00:00:00",
    }
    store.save_chat("test-user", chat)
    messages = [
        {"id": "msg1", "content": "Hello", "createdAt": "2024-01-02T00:00:00"},
        {"id": "msg2", "content": "World", "createdAt": "2024-01-02T00:00:01"},
    ]
    store.save_messages("test-user", "int-chat2", messages)
    loaded = store.get_messages("test-user", "int-chat2")
    assert len(loaded) == 2
    assert loaded[0]["id"] == "msg1"
    assert loaded[1]["id"] == "msg2"


def test_delete_chat_cleans_up(real_ws, temp_volume_path):
    """delete_chat 後、get_chat が None を返すことを検証する."""
    store = ChatHistoryStore(volume_path=temp_volume_path, workspace_client=real_ws)
    chat = {
        "id": "int-chat3",
        "userId": "test-user",
        "title": "Delete Test",
        "createdAt": "2024-01-03T00:00:00",
    }
    store.save_chat("test-user", chat)
    store.delete_chat("test-user", "int-chat3")
    loaded = store.get_chat("test-user", "int-chat3")
    assert loaded is None


def test_pagination_with_many_chats(real_ws, temp_volume_path):
    """25 件保存後、limit=20 で hasMore=True になることを検証する."""
    store = ChatHistoryStore(volume_path=temp_volume_path, workspace_client=real_ws)
    for i in range(25):
        chat = {
            "id": f"int-page-{i}",
            "userId": "test-user",
            "title": f"Chat {i}",
            "createdAt": f"2024-01-{i + 1:02d}T00:00:00",
        }
        store.save_chat("test-user", chat)
    result = store.get_chats_by_user("test-user", limit=20)
    assert len(result["chats"]) == 20
    assert result["hasMore"] is True
