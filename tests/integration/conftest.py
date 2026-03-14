"""統合テスト用フィクスチャ: 実 WorkspaceClient と一時 Volume パス."""
import os
from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def real_ws():
    """環境変数から認証した実 WorkspaceClient を返す."""
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


@pytest.fixture
def temp_volume_path(real_ws):
    """一時的な Volume パスを生成して yield し、テスト後にクリーンアップする.

    環境変数 TEST_VOLUME_PATH にベースパスを設定すること:
      export TEST_VOLUME_PATH=/Volumes/catalog/schema/volume
    """
    from databricks.sdk.errors import NotFound, ResourceDoesNotExist

    base_vol = os.environ.get("TEST_VOLUME_PATH")
    if not base_vol:
        pytest.skip("TEST_VOLUME_PATH environment variable is not set")

    path = f"{base_vol.rstrip('/')}/pytest-{uuid4()}"
    yield path

    # teardown: 一時データを削除
    try:
        entries = list(real_ws.files.list_directory_contents(path))
        for entry in entries:
            if entry.path:
                try:
                    if entry.is_directory:
                        _cleanup_dir(real_ws, entry.path)
                    else:
                        real_ws.files.delete(entry.path)
                except Exception:
                    pass
        real_ws.files.delete_directory(path)
    except (NotFound, ResourceDoesNotExist):
        pass


def _cleanup_dir(ws, dir_path: str) -> None:
    """ディレクトリを再帰的に削除する."""
    from databricks.sdk.errors import NotFound, ResourceDoesNotExist

    try:
        entries = list(ws.files.list_directory_contents(dir_path))
        for entry in entries:
            if entry.path:
                if entry.is_directory:
                    _cleanup_dir(ws, entry.path)
                else:
                    try:
                        ws.files.delete(entry.path)
                    except Exception:
                        pass
        ws.files.delete_directory(dir_path)
    except (NotFound, ResourceDoesNotExist):
        pass
