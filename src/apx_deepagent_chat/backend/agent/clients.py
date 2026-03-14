import logging
from contextvars import ContextVar
from functools import cache
from typing import Optional

from databricks.sdk import WorkspaceClient
from mlflow.genai.agent_server import get_request_headers

logger = logging.getLogger(__name__)

# ─── Databricks クライアント依存注入 ─────────────────────────────────────────

# Dependencies.UserClient で注入された WorkspaceClient を受け取る ContextVar
_injected_user_ws_client: ContextVar[WorkspaceClient | None] = ContextVar(
    "_injected_user_ws_client", default=None
)

# Dependencies.Client（SP）で注入された WorkspaceClient を受け取る ContextVar
_injected_sp_ws_client: ContextVar[WorkspaceClient | None] = ContextVar(
    "_injected_sp_ws_client", default=None
)


def get_user_workspace_client() -> WorkspaceClient:
    """ユーザー認証済み WorkspaceClient を返す（DI優先、フォールバックあり）.

    FastAPI DI 経由で注入された場合はそれを返し、
    mlflow ハンドラー経由の場合はリクエストヘッダーから生成する。
    """
    injected = _injected_user_ws_client.get()
    if injected is not None:
        return injected
    # フォールバック: mlflow Context Var からヘッダー経由で生成
    token = get_request_headers().get("x-forwarded-access-token")
    if not token:
        return WorkspaceClient()
    return WorkspaceClient(token=token, auth_type="pat")


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
