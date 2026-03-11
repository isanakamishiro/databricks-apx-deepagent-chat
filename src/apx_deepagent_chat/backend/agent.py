import asyncio
import functools
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

import mlflow
import mlflow.config
import uuid_utils
import yaml
from databricks.sdk import WorkspaceClient
from databricks_langchain import (
    ChatDatabricks,
    DatabricksMCPServer,
    DatabricksMultiServerMCPClient,
)
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend
from deepagents.backends.utils import create_file_data
from langchain.agents.middleware import wrap_model_call, wrap_tool_call
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import tool as langchain_tool
from mlflow.genai.agent_server import invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
    to_chat_completions_input,
)

from .core._base import LifespanDependency
from .uc_backend import UCVolumesBackend
from .uc_checkpointer import UCBundleCheckpointer
from .agent_utils import (
    get_databricks_host_from_env,
    get_sp_workspace_client,
    get_user_workspace_client,
    process_agent_astream_events,
)

mlflow.langchain.autolog()
# Enable async logging
mlflow.config.enable_async_logging()

MODEL = "databricks-qwen3-next-80b-a3b-instruct"
# MODEL = "databricks-gpt-oss-120b"
USE_FAKE_MODEL = os.getenv("USE_FAKE_MODEL", "false").lower() == "true"
ASSETS_DIR = Path(__file__).parent.parent / "assets"
_SYSTEM_PROMPT_PATH = ASSETS_DIR / "system_prompt.md"
_SUBAGENTS_CONFIG_PATH = ASSETS_DIR / "subagents.yaml"
_TEXT_SUFFIXES = {".md", ".py", ".txt"}


def _make_fake_model():
    """FakeListChatModel を構築して返す（開発モード用）."""
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    FAKE_RESPONSE = "こんにちは！私は元気です！"

    class ToolCapableFakeModel(FakeListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    return ToolCapableFakeModel(responses=[FAKE_RESPONSE] * 20)


# --- Module-level caches ---
_MCP_TOOLS_TTL_SECONDS = 30 * 60  # 30 minutes
_mcp_tools_cache: list | None = None
_mcp_tools_cached_at: float = 0.0
_mcp_tools_lock = asyncio.Lock()
_tool_call_semaphore = asyncio.Semaphore(4)


@wrap_tool_call  # type: ignore[arg-type]
async def strip_content_block_ids(request, handler):
    """MCP ツール結果の content block から id/index フィールドを除去し、同時実行数を制限する.

    langchain_core の create_text_block() が自動付与する id フィールドが
    Databricks Model Serving 経由の Anthropic API でバリデーションエラーを
    引き起こすため、ツール実行後に除去する。
    また、MCP ツールの同時実行数をセマフォで制限し TaskGroup エラーを防ぐ。
    """
    async with _tool_call_semaphore:
        result = await handler(request)
    if isinstance(result, ToolMessage) and isinstance(result.content, list):
        result.content = [
            (
                {k: v for k, v in block.items() if k not in ("id", "index")}
                if isinstance(block, dict)
                else block
            )
            for block in result.content
        ]
    return result


@wrap_model_call  # type: ignore[arg-type]
async def flatten_system_message(request, handler):
    """SystemMessage の content block リストをプレーン文字列に正規化する.

    deepagents の append_to_system_message が生成する
    [{"type": "text", "text": "..."}] 形式を、Gemini API が受け付ける
    単純な文字列に変換する。
    """
    if request.system_message and isinstance(request.system_message.content, list):
        parts = []
        for block in request.system_message.content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        request.system_message = SystemMessage(content="\n\n".join(parts))
    return await handler(request)


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


async def _get_mcp_tools(workspace_client: WorkspaceClient) -> list:
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


def _get_volume_path(request: ResponsesAgentRequest) -> str:
    """Extract volume_path from custom_inputs."""
    ci = dict(request.custom_inputs or {})
    if "volume_path" in ci and ci["volume_path"]:
        return str(ci["volume_path"])
    raise ValueError(
        "UC Volume Path が設定されていません。"
        "サイドバーの設定から Volume Path を入力してください。"
    )


def _get_or_create_thread_id(request: ResponsesAgentRequest) -> str:
    """Extract thread_id from request, falling back to a generated UUID7.

    Priority:
      1. ``custom_inputs["thread_id"]``
      2. ``context.conversation_id``
      3. Auto-generated UUID7
    """
    ci = dict(request.custom_inputs or {})

    if "thread_id" in ci and ci["thread_id"]:
        return str(ci["thread_id"])

    if request.context and getattr(request.context, "conversation_id", None):
        return str(request.context.conversation_id)

    return str(uuid_utils.uuid7())


# --- クロージャ不要なツール（モジュールレベルで1回だけ生成） ---


@langchain_tool
def web_search(query: str, max_results: int = 5, region: str = "jp-jp") -> str:
    """DuckDuckGoでWeb検索を行い、結果を返します。最新情報や不明な事実を調べる場合に使用してください。

    Args:
        query: 検索クエリ。
        max_results: 返す検索結果の最大件数。デフォルトは5。
        region: 検索対象の地域コード。デフォルトは"jp-jp"(日本)。例: "us-en", "uk-en", "de-de"。
    """
    from ddgs import DDGS

    try:
        results = list(DDGS().text(query, region=region, max_results=max_results))
    except TimeoutError:
        return (
            "検索エラー: リクエストがタイムアウトしました。後でもう一度試してください。"
        )
    except Exception as e:
        return f"検索エラー: 予期しないエラーが発生しました: {type(e).__name__}: {e}"

    if not results:
        return "検索結果が見つかりませんでした。"

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"### {i}. {r.get('title', '(タイトルなし)')}")
        lines.append(f"URL: {r.get('href', '(URLなし)')}")
        lines.append(f"{r.get('body', '')}\n")
    return "\n".join(lines)


@langchain_tool
def web_fetch(url: str, max_length: int = 50000) -> str:
    """URLのWebページを取得し、Markdown形式に変換して返します。Webページの内容を読み取りたい場合に使用してください。

    Args:
        url: 取得するWebページのURL。
        max_length: 返すテキストの最大文字数。デフォルトは50000。
    """
    import requests
    from markitdown import MarkItDown

    try:
        md = MarkItDown()
        result = md.convert_url(url)
    except requests.ConnectionError:
        return f"取得エラー: URL '{url}' に接続できませんでした。URLが正しいか確認してください。"
    except requests.Timeout:
        return f"取得エラー: URL '{url}' への接続がタイムアウトしました。"
    except requests.HTTPError as e:
        return f"取得エラー: HTTPエラーが発生しました (ステータス {e.response.status_code if e.response else '不明'}): {e}"
    except Exception as e:
        return f"取得エラー: 予期しないエラーが発生しました: {type(e).__name__}: {e}"

    text = result.text_content
    if not text or not text.strip():
        return f"取得エラー: URL '{url}' からコンテンツを抽出できませんでした。"
    if len(text) > max_length:
        text = text[:max_length] + "\n\n... (truncated)"
    return text


@langchain_tool
def get_current_time(timezone: str = "Asia/Tokyo") -> str:
    """現在の日時を返します。日時の確認が必要な場合に使用してください。

    Args:
        timezone: タイムゾーン名。デフォルトは"Asia/Tokyo"。例: "UTC", "US/Eastern", "Europe/London"。
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(timezone)
    except KeyError:
        return f"エラー: 不明なタイムゾーン '{timezone}'"
    now = datetime.now(tz)
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")


@functools.cache
def _load_subagents(config_path: Path) -> list:
    """Load subagent definitions from YAML and wire up tools (cached)."""
    available_tools = {
        "get_current_time": get_current_time,
        "web_search": web_search,
        "web_fetch": web_fetch,
    }
    # Tool names that require dynamic injection at init_agent() time
    _dynamic_tool_keys = {"mcp_tools"}

    with open(config_path) as f:
        config = yaml.safe_load(f)

    subagents = []
    for name, spec in config.items():
        subagent = {
            "name": name,
            "description": spec["description"],
            "system_prompt": spec["system_prompt"],
        }
        if "model" in spec:
            subagent["model"] = ChatDatabricks(model=spec["model"])
        if "skills" in spec:
            subagent["skills"] = spec["skills"]
        if "tools" in spec:
            tool_names = spec["tools"]
            resolved = [
                available_tools[t] for t in tool_names if t not in _dynamic_tool_keys
            ]
            if "mcp_tools" in tool_names:
                subagent["_pending_mcp_tools"] = True
            if resolved:
                subagent["tools"] = resolved
        subagents.append(subagent)

    return subagents


@functools.cache
def _load_system_prompt(prompt_path: Path) -> str:
    """Load system prompt from file (cached)."""
    return prompt_path.read_text()


@functools.cache
def _load_preset_files() -> dict[str, Any]:
    """assets/ ディレクトリのファイルデータをキャッシュして返す。"""

    files: dict[str, Any] = {}

    # assets/AGENTS.md -> /AGENTS.md (CompositeBackend が /preset/ を除去して渡すキー)
    agents_md_path = ASSETS_DIR / "AGENTS.md"
    if agents_md_path.exists():
        files["/AGENTS.md"] = create_file_data(agents_md_path.read_text())

    # assets/skills/** -> /skills/**
    skills_dir = ASSETS_DIR / "skills"
    if skills_dir.exists():
        for file_path in skills_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix in _TEXT_SUFFIXES:
                rel = file_path.relative_to(ASSETS_DIR)
                files[f"/{rel}"] = create_file_data(
                    file_path.read_text(encoding="utf-8")
                )

    return files


# def _init_preset_store() -> InMemoryStore:
#     """キャッシュ済みファイルデータから新しい InMemoryStore を構築して返す。"""
#     store = InMemoryStore()
#     for key, value in _load_preset_files().items():
#         store.put(namespace=("filesystem",), key=key, value=value)
#     return store


# --- スタートアップ時プリウォーム ---
_prewarm_logger = logging.getLogger(__name__)


class _AgentPrewarm(LifespanDependency):
    """アプリ起動時にキャッシュを並列プリウォームし、初回リクエストのコールドスタートを排除する。"""

    @staticmethod
    def __call__():
        return None

    @asynccontextmanager
    async def lifespan(self, app):
        t0 = time.monotonic()
        try:
            await asyncio.gather(
                _get_mcp_tools(get_sp_workspace_client()),
                asyncio.to_thread(_load_subagents, _SUBAGENTS_CONFIG_PATH),
                asyncio.to_thread(_load_system_prompt, _SYSTEM_PROMPT_PATH),
                asyncio.to_thread(_load_preset_files),
            )
            _prewarm_logger.info("[prewarm] completed in %.3fs", time.monotonic() - t0)
        except Exception:
            _prewarm_logger.warning("[prewarm] failed (non-fatal)", exc_info=True)
        yield


def _build_subagents(
    mcp_tools: list,
    override_model=None,
) -> list:
    """Load subagent definitions from YAML and inject dynamic tools."""
    subagents = _load_subagents(_SUBAGENTS_CONFIG_PATH)
    for sa in subagents:
        if override_model and "model" in sa:
            sa["model"] = override_model
        if sa.get("_pending_mcp_tools"):
            sa["tools"] = mcp_tools + sa.get("tools", [])
            existing = [
                m for m in sa.get("middleware", []) if m is not strip_content_block_ids
            ]
            sa["middleware"] = existing + [strip_content_block_ids]

    return subagents


# @mlflow.trace(span_type="UNKNOWN")
async def init_agent(
    workspace_client: Optional[WorkspaceClient] = None,
    checkpointer=None,
    volume_path: Optional[str] = None,
    override_model=None,
):
    # 開発モード: USE_FAKE_MODEL=true の場合は FakeListChatModel を使用
    if override_model is None and USE_FAKE_MODEL:
        override_model = _make_fake_model()

    ws_client = workspace_client or get_sp_workspace_client()
    if not volume_path:
        raise ValueError("volume_path is required")

    # MCP ツールは常にサービスプリンシパルで取得（ユーザー認証不要なワークスペース全体のツール）
    mcp_tools = await _get_mcp_tools(get_sp_workspace_client())

    subagents = _build_subagents(
        mcp_tools=mcp_tools,
        override_model=override_model,
    )

    model = override_model or ChatDatabricks(
        endpoint=MODEL,
        workspace_client=ws_client,
        temperature=0,
        use_responses_api=False,
    )

    # preset_store = _init_preset_store()
    backend = lambda rt: CompositeBackend(
        default=UCVolumesBackend(
            volume_path=volume_path,
            workspace_client=ws_client,
        ),
        routes={
            "/preset/": StateBackend(rt),
        },
    )

    return create_deep_agent(
        tools=mcp_tools
        + [
            web_search,
            web_fetch,
            get_current_time,
        ],
        system_prompt=_load_system_prompt(_SYSTEM_PROMPT_PATH),
        memory=["/preset/AGENTS.md"],
        skills=["/preset/skills/"],
        model=model,
        backend=backend,
        subagents=subagents,
        checkpointer=checkpointer,
        middleware=[strip_content_block_ids, flatten_system_message],
    )


@invoke()
async def non_streaming(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    outputs = []
    completed_response: dict | None = None
    async for event in streaming(request):
        if event.type == "response.output_item.done":
            outputs.append(event.item)  # type: ignore[attr-defined]
        elif event.type == "response.completed":
            completed_response = getattr(event, "response", None)

    kwargs: dict[str, Any] = {"output": outputs}

    if completed_response:
        # model
        if completed_response.get("model"):
            kwargs["model"] = completed_response["model"]
        # usage (ResponseUsage 形式)
        u = completed_response.get("usage", {})
        if u:
            kwargs["usage"] = {
                "input_tokens": u.get("input_tokens", 0),
                "output_tokens": u.get("output_tokens", 0),
                "total_tokens": u.get("total_tokens", 0),
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            }

    return ResponsesAgentResponse(**kwargs)


@stream()
async def streaming(
    request: ResponsesAgentRequest,
) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    user_workspace_client = get_user_workspace_client()
    volume_path = _get_volume_path(request)
    thread_id = _get_or_create_thread_id(request)

    checkpointer = UCBundleCheckpointer(
        volume_path=volume_path,
        thread_id=thread_id,
        workspace_client=get_sp_workspace_client(),
    )

    async with checkpointer:
        agent = await init_agent(
            user_workspace_client,
            checkpointer=checkpointer,
            volume_path=volume_path,
        )

        all_messages = to_chat_completions_input(
            [i.model_dump() for i in request.input]
        )
        # checkpointer が会話履歴を保持するため、最後のメッセージのみ渡す
        messages = {
            "messages": [all_messages[-1]] if all_messages else [],
            "files": _load_preset_files(),
        }
        config = {"configurable": {"thread_id": thread_id}}

        max_ctx = 0
        usage_accumulator: dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
        async for event in process_agent_astream_events(
            agent.astream(
                input=messages,
                config=config,  # type: ignore[arg-type]
                stream_mode=["updates", "messages"],
                subgraphs=True,
                version="v2",
            ),
            usage_accumulator=usage_accumulator,
            model=MODEL,
            max_context_tokens=max_ctx,
        ):
            yield event
