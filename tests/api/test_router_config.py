"""設定 API ルーターテスト."""
from unittest.mock import patch


def test_get_config_success(client):
    models = {
        "databricks-meta-llama/Meta-Llama-3.3-70B-Instruct": {
            "display_name": "Llama 3.3 70B",
            "default": True,
        },
        "databricks-claude-3-7-sonnet": {
            "display_name": "Claude 3.7 Sonnet",
        },
    }
    with patch(
        "apx_deepagent_chat.backend.routers.config.load_models_config", return_value=models
    ):
        response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert "default_model" in data
    assert data["workspace_url"] == "https://test.azuredatabricks.net"
    assert len(data["models"]) == 2


def test_get_config_default_model(client):
    models = {
        "model-a": {"display_name": "Model A"},
        "model-b": {"display_name": "Model B", "default": True},
    }
    with patch(
        "apx_deepagent_chat.backend.routers.config.load_models_config", return_value=models
    ):
        response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json()["default_model"] == "model-b"


def test_get_config_model_display_names(client):
    models = {
        "model-x": {"display_name": "Model X", "default": True},
    }
    with patch(
        "apx_deepagent_chat.backend.routers.config.load_models_config", return_value=models
    ):
        response = client.get("/api/config")
    data = response.json()
    assert data["models"][0]["id"] == "model-x"
    assert data["models"][0]["display_name"] == "Model X"
