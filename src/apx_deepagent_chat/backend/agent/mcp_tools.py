import asyncio
import time
from pathlib import Path

import yaml
from databricks.sdk import WorkspaceClient
from databricks_langchain import DatabricksMCPServer, DatabricksMultiServerMCPClient

from .clients import get_databricks_host_from_env

# --- MCP ツールキャッシュ ---
_MCP_TOOLS_TTL_SECONDS = 30 * 60  # 30 minutes
_mcp_tools_cache: list | None = None
_mcp_tools_cached_at: float = 0.0
_mcp_tools_lock = asyncio.Lock()

_ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"
_MCP_SETTINGS_PATH = _ASSETS_DIR / "mcp_settings.yaml"


def load_mcp_settings() -> dict[str, dict]:
    """mcp_settings.yaml を読み込み、サーバ設定の辞書を返す。"""
    with open(_MCP_SETTINGS_PATH) as f:
        return yaml.safe_load(f)["mcp_servers"]


def _init_mcp_client(
    workspace_client: WorkspaceClient,
) -> DatabricksMultiServerMCPClient:
    host_name = get_databricks_host_from_env()
    settings = load_mcp_settings()

    mcp_servers: list = [
        DatabricksMCPServer(
            name=name,
            url=f"{host_name}{Path('/') / cfg['path']}",
            workspace_client=workspace_client,
        )
        for name, cfg in settings.items()
    ]

    return DatabricksMultiServerMCPClient(mcp_servers)


async def get_mcp_tools(workspace_client: WorkspaceClient) -> list:
    """MCP ツール一覧を取得しキャッシュする（TTL: 30分）。"""
    global _mcp_tools_cache, _mcp_tools_cached_at
    now = time.monotonic()
    if (
        _mcp_tools_cache is not None
        and (now - _mcp_tools_cached_at) < _MCP_TOOLS_TTL_SECONDS
    ):
        return _mcp_tools_cache

    async with _mcp_tools_lock:
        if (
            _mcp_tools_cache is not None
            and (now - _mcp_tools_cached_at) < _MCP_TOOLS_TTL_SECONDS
        ):
            return _mcp_tools_cache
        mcp_client = _init_mcp_client(workspace_client)
        tools = await mcp_client.get_tools()
        _mcp_tools_cache = tools
        _mcp_tools_cached_at = time.monotonic()
        return tools
