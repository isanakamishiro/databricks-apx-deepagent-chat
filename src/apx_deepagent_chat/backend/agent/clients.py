import logging
from contextvars import ContextVar
from functools import cache
from typing import Optional

from databricks.sdk import WorkspaceClient
from mlflow.genai.agent_server import get_request_headers

logger = logging.getLogger(__name__)

# ─── Databricks クライアント依存注入 ─────────────────────────────────────────

# OBOトークン文字列を保持する ContextVar（ストリーミング中も維持するためリセットしない）
_current_obo_token: ContextVar[str | None] = ContextVar(
    "_current_obo_token", default=None
)

# Dependencies.Client（SP）で注入された WorkspaceClient を受け取る ContextVar
_injected_sp_ws_client: ContextVar[WorkspaceClient | None] = ContextVar(
    "_injected_sp_ws_client", default=None
)


def get_user_workspace_client() -> WorkspaceClient:
    """ユーザー認証済み WorkspaceClient を返す（毎回新規生成）.

    _current_obo_token から OBOトークンを読み取り、毎回新しい WorkspaceClient を生成する。
    これによりストリーミングジェネレータ実行時も finally リセット後も正しいトークンが使われる。
    フォールバック順: _current_obo_token → get_request_headers() → WorkspaceClient()
    """
    token = _current_obo_token.get()
    if token:
        return WorkspaceClient(token=token, auth_type="pat")
    # フォールバック: mlflow Context Var からヘッダー経由で生成
    token = get_request_headers().get("x-forwarded-access-token")
    if token:
        return WorkspaceClient(token=token, auth_type="pat")
    return WorkspaceClient()


def get_sp_workspace_client() -> WorkspaceClient:
    """サービスプリンシパル WorkspaceClient を返す（DI優先、フォールバックあり）."""
    injected = _injected_sp_ws_client.get()
    if injected is not None:
        return injected
    return WorkspaceClient()


@cache
def get_databricks_host_from_env() -> Optional[str]:
    """環境変数から Databricks ホスト URL を取得して返す.

    結果はキャッシュされるため、WorkspaceClient の初期化は初回のみ実行される。
    取得に失敗した場合は None を返す。
    """
    try:
        w = WorkspaceClient()
        return w.config.host
    except Exception as e:
        logger.exception(f"Error getting databricks host from env: {e}")
        return None
