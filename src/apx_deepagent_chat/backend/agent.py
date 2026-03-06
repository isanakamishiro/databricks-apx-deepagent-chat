import asyncio
import functools
import json
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

import mlflow
import uuid_utils
import yaml
from databricks.sdk import WorkspaceClient
from databricks_langchain import (
    ChatDatabricks,
    DatabricksMCPServer,
    DatabricksMultiServerMCPClient,
)
from deepagents import create_deep_agent
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

from .docx_tools import create_docx_tools
from .pdf_tools import create_pdf_tools
from .pptx_tools import create_pptx_tools
from .uc_backend import UCVolumesBackend
from .uc_checkpointer import UCVolumesCheckpointer
from .agent_utils import (
    get_databricks_host_from_env,
    get_user_workspace_client,
    process_agent_astream_events,
)

mlflow.langchain.autolog()
sp_workspace_client = WorkspaceClient()

# src/myapp/backend/agent.py -> apx-sample/
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
_MODELS_CONFIG_PATH = _PROJECT_ROOT / "config" / "models.json"


def _load_models_config() -> dict:
    with open(_MODELS_CONFIG_PATH) as f:
        return json.load(f)


_models_config = _load_models_config()
AVAILABLE_MODELS: list[str] = list(_models_config["models"].keys())
DEFAULT_MODEL: str = _models_config["default_model"]

ASSETS_DIR = _PROJECT_ROOT / "assets"

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
            DatabricksMCPServer(
                name="dbsql",
                url=f"{host_name}/api/2.0/mcp/sql",
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
        tools = [t for t in tools if t.name != "execute_sql"]
        _mcp_tools_cache = tools
        _mcp_tools_cached_at = time.monotonic()
        return tools


def _get_model_option(model_name: str, key: str, default=None):
    """Get a model-specific option from the config."""
    model_opts = _models_config["models"].get(model_name, {})
    return model_opts.get(key, default)


def _get_llm_model(request: ResponsesAgentRequest) -> str:
    """Extract llm_model from custom_inputs, falling back to DEFAULT_MODEL."""
    ci = dict(request.custom_inputs or {})
    model = ci.get("llm_model", "")
    return model if model in AVAILABLE_MODELS else DEFAULT_MODEL


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
    _dynamic_tool_keys = {"mcp_tools", "pptx_tools", "pdf_tools", "docx_tools"}

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
            if "pptx_tools" in tool_names:
                subagent["_pending_pptx_tools"] = True
            if "pdf_tools" in tool_names:
                subagent["_pending_pdf_tools"] = True
            if "docx_tools" in tool_names:
                subagent["_pending_docx_tools"] = True
            if resolved:
                subagent["tools"] = resolved
        subagents.append(subagent)

    return subagents


@functools.cache
def _load_system_prompt(prompt_path: Path) -> str:
    """Load system prompt from file (cached)."""
    return prompt_path.read_text()


def _build_subagents(
    mcp_tools: list,
    volume_path: str,
    workspace_client: Optional[WorkspaceClient] = None,
) -> list:
    """Load subagent definitions from YAML and inject dynamic tools."""
    ws_client = workspace_client or sp_workspace_client
    pptx_tools = create_pptx_tools(ws_client, volume_path)
    pdf_tools = create_pdf_tools(ws_client, volume_path)
    docx_tools = create_docx_tools(ws_client, volume_path)

    subagents = _load_subagents(ASSETS_DIR / "subagents.yaml")
    for sa in subagents:
        if sa.get("_pending_mcp_tools"):
            sa["tools"] = mcp_tools + sa.get("tools", [])
            existing = [
                m for m in sa.get("middleware", []) if m is not strip_content_block_ids
            ]
            sa["middleware"] = existing + [strip_content_block_ids]
        if sa.get("_pending_pptx_tools"):
            sa["tools"] = pptx_tools + sa.get("tools", [])
            del sa["_pending_pptx_tools"]
        if sa.get("_pending_pdf_tools"):
            sa["tools"] = pdf_tools + sa.get("tools", [])
            del sa["_pending_pdf_tools"]
        if sa.get("_pending_docx_tools"):
            sa["tools"] = docx_tools + sa.get("tools", [])
            del sa["_pending_docx_tools"]

    return subagents


async def init_agent(
    workspace_client: Optional[WorkspaceClient] = None,
    checkpointer=None,
    volume_path: Optional[str] = None,
    llm_model: Optional[str] = None,
):
    ws_client = workspace_client or sp_workspace_client
    if not volume_path:
        raise ValueError("volume_path is required")

    mcp_tools = await _get_mcp_tools(ws_client)

    # クロージャが必要なツール（volume_path / ws_client を参照）
    @langchain_tool
    def reset_skills() -> str:
        """ボリュームの skills/ フォルダをデフォルトに復元します。ユーザから「リセット」と指示された場合に使用してください。"""
        import io
        from pathlib import PurePosixPath

        assets_skills = _PROJECT_ROOT / "assets" / "skills"
        if not assets_skills.is_dir():
            return "エラー: デフォルトのスキルフォルダが見つかりません。"

        count = 0
        for local_path in assets_skills.rglob("*"):
            if not local_path.is_file():
                continue
            rel = local_path.relative_to(assets_skills)
            dest = f"{volume_path}/skills/{rel}"
            parent = str(PurePosixPath(dest).parent)
            try:
                sp_workspace_client.files.create_directory(parent)
            except Exception:
                pass
            sp_workspace_client.files.upload(
                dest, io.BytesIO(local_path.read_bytes()), overwrite=True
            )
            count += 1

        return f"skills/ をデフォルトに復元しました ({count} ファイル)。"

    @langchain_tool
    def reset_agent_config() -> str:
        """ボリュームの AGENTS.md をデフォルトに復元します。ユーザからエージェント設定のリセットを指示された場合に使用してください。"""
        import io

        agents_md = _PROJECT_ROOT / "assets" / "AGENTS.md"
        if not agents_md.is_file():
            return "エラー: デフォルトの AGENTS.md が見つかりません。"

        sp_workspace_client.files.upload(
            f"{volume_path}/AGENTS.md",
            io.BytesIO(agents_md.read_bytes()),
            overwrite=True,
        )
        return "AGENTS.md をデフォルトに復元しました。"

    @langchain_tool
    def get_volume_browser_url(file_path: str) -> str:
        """UC Volume上のファイルが格納されているディレクトリのブラウザURLを生成します。ファイルの場所をユーザに案内したい場合に使用してください。

        Args:
            file_path: 対象ファイルの仮想パス (例: "/report.csv")。
        """
        from pathlib import PurePosixPath
        from urllib.parse import quote

        from .agent_utils import to_real_path

        real_path = to_real_path(volume_path, file_path)
        parent_dir = str(PurePosixPath(real_path).parent)
        if not parent_dir.endswith("/"):
            parent_dir += "/"
        parts = volume_path.strip("/").split(
            "/"
        )  # ["Volumes", catalog, schema, volume]
        catalog, schema, volume_name = parts[1], parts[2], parts[3]
        host = ws_client.config.host.rstrip("/")
        volume_path_param = quote(parent_dir, safe="")
        return (
            f"{host}/explore/data/volumes/{catalog}/{schema}/{volume_name}"
            f"?volumePath={volume_path_param}"
        )

    subagents = _build_subagents(
        mcp_tools=mcp_tools,
        volume_path=volume_path,
        workspace_client=ws_client,
    )

    return create_deep_agent(
        tools=mcp_tools
        + [
            web_search,
            web_fetch,
            get_volume_browser_url,
            reset_skills,
            reset_agent_config,
            get_current_time,
        ],
        system_prompt=_load_system_prompt(ASSETS_DIR / "system_prompt.md"),
        memory=["AGENTS.md", "memories/instructions.md"],
        skills=["skills/"],
        model=ChatDatabricks(
            endpoint=llm_model or DEFAULT_MODEL,
            workspace_client=ws_client,
            temperature=0,
            use_responses_api=_get_model_option(
                llm_model or DEFAULT_MODEL, "use_responses_api", False
            ),
        ),
        backend=UCVolumesBackend(
            volume_path=volume_path,
            workspace_client=ws_client,
        ),
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
    llm_model = _get_llm_model(request)

    checkpointer = UCVolumesCheckpointer(
        volume_path=volume_path,
        workspace_client=sp_workspace_client,
    )
    agent = await init_agent(
        user_workspace_client,
        checkpointer=checkpointer,
        volume_path=volume_path,
        llm_model=llm_model,
    )

    all_messages = to_chat_completions_input([i.model_dump() for i in request.input])
    # checkpointer が会話履歴を保持するため、最後のメッセージのみ渡す
    messages = {"messages": [all_messages[-1]] if all_messages else []}
    thread_id = _get_or_create_thread_id(request)
    config = {"configurable": {"thread_id": thread_id}}

    max_ctx = _get_model_option(llm_model, "max_context_tokens", 0)
    usage_accumulator: dict[str, int] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    async for event in process_agent_astream_events(
        agent.astream(
            input=messages,
            config=config,
            stream_mode=["updates", "messages"],
            subgraphs=True,
        ),
        usage_accumulator=usage_accumulator,
        model=llm_model,
        max_context_tokens=max_ctx,
    ):
        yield event
