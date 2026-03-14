import asyncio
import time

from databricks.sdk import WorkspaceClient
from databricks_langchain import DatabricksMCPServer, DatabricksMultiServerMCPClient

from .clients import get_databricks_host_from_env

# --- MCP ツールキャッシュ ---
_MCP_TOOLS_TTL_SECONDS = 30 * 60  # 30 minutes
_mcp_tools_cache: list | None = None
_mcp_tools_cached_at: float = 0.0
_mcp_tools_lock = asyncio.Lock()


def _init_mcp_client(
    workspace_client: WorkspaceClient,
) -> DatabricksMultiServerMCPClient:
    host_name = get_databricks_host_from_env()
    return DatabricksMultiServerMCPClient(
        [
            DatabricksMCPServer(
                name="system-ai",
                url=f"{host_name}/api/2.0/mcp/functions/system/ai",
                workspace_client=workspace_client,
            ),
        ]
    )


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
