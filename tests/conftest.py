"""共有フィクスチャ: TestClient、モック群."""
import pytest
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_ws():
    ws = MagicMock()
    ws.config.host = "https://test.azuredatabricks.net"
    return ws


@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.app_name = "Test App"
    return cfg


@pytest.fixture
def app(mock_ws, mock_config):
    from apx_deepagent_chat.backend.core._defaults import (
        _WorkspaceClientDependency,
        _get_user_ws,
    )
    from apx_deepagent_chat.backend.routers.chat_history import router as chat_history_router
    from apx_deepagent_chat.backend.routers.files import router as files_router
    from apx_deepagent_chat.backend.routers.volumes import router as volumes_router
    from apx_deepagent_chat.backend.routers.system import router as system_router

    test_app = FastAPI()
    test_app.state.config = mock_config
    test_app.state.workspace_client = mock_ws

    # DI オーバーライド
    test_app.dependency_overrides[_WorkspaceClientDependency.__call__] = lambda: mock_ws
    test_app.dependency_overrides[_get_user_ws] = lambda: mock_ws

    test_app.include_router(chat_history_router, prefix="/api")
    test_app.include_router(files_router, prefix="/api")
    test_app.include_router(volumes_router, prefix="/api")
    test_app.include_router(system_router, prefix="/api")

    return test_app


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def vol_headers():
    return {"x-uc-volume-path": "/Volumes/cat/schema/vol"}
