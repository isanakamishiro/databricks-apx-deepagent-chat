import asyncio
import functools
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

import mlflow
import mlflow.config
import uuid_utils
import yaml
from databricks.sdk import WorkspaceClient
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend
from deepagents.backends.utils import create_file_data
from deepagents.middleware.summarization import (
    create_summarization_tool_middleware,
)
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain_core.language_models import BaseChatModel
from mlflow.genai.agent_server import invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
    to_chat_completions_input,
)
from mlflow.types.responses_helpers import ResponseError

from ..core._base import LifespanDependency
from .clients import get_sp_workspace_client, get_user_workspace_client
from .lc_tools import get_current_time, web_fetch, web_search
from .mcp_tools import get_mcp_tools
from .middleware import flatten_system_message, strip_content_block_ids
from .model import (
    ASSETS_DIR,
    FAKE_MODEL_NAME,
    USE_FAKE_MODEL,
    init_model,
    load_models_config,
)
from .stream import process_agent_astream_events
from .uc_backend import UCVolumesBackend
from .uc_checkpointer import UCBundleCheckpointer

mlflow.langchain.autolog()
# Enable async logging
mlflow.config.enable_async_logging()

_SYSTEM_PROMPT_PATH = ASSETS_DIR / "system_prompt.md"
_SUBAGENTS_CONFIG_PATH = ASSETS_DIR / "subagents.yaml"
_TEXT_SUFFIXES = {".md", ".py", ".txt"}

logger = logging.getLogger(__name__)


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
                get_mcp_tools(get_user_workspace_client()),
                asyncio.to_thread(_load_subagents, _SUBAGENTS_CONFIG_PATH),
                asyncio.to_thread(_load_system_prompt, _SYSTEM_PROMPT_PATH),
                asyncio.to_thread(_load_preset_files),
            )
            logger.info("[prewarm] completed in %.3fs", time.monotonic() - t0)
        except Exception:
            logger.warning("[prewarm] failed (non-fatal)", exc_info=True)
        yield


def _get_model_name(request: ResponsesAgentRequest) -> str:
    """Extract llm_model from custom_inputs, falling back to the default model."""
    ci = dict(request.custom_inputs or {})
    if "llm_model" in ci and ci["llm_model"]:
        return str(ci["llm_model"])
    return next(k for k, v in load_models_config().items() if v.get("default"))


def _get_volume_path(request: ResponsesAgentRequest) -> str:
    """Extract volume_path from custom_inputs."""
    ci = dict(request.custom_inputs or {})
    if "volume_path" in ci and ci["volume_path"]:
        return str(ci["volume_path"])
    raise ValueError("UC Volume Path が設定されていません。")


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


@functools.cache
def _load_subagents(config_path) -> list:
    """Load subagent definitions from YAML and wire up tools (cached).

    Note: callers must shallow-copy returned dicts before mutating (e.g. ``sa = {**sa}``).
    """
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
            subagent["model"] = spec["model"]
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
def _load_system_prompt(prompt_path) -> str:
    """Load system prompt from file (cached)."""
    return prompt_path.read_text()


@functools.cache
def _load_preset_files() -> dict[str, Any]:
    """assets/ ディレクトリのファイルデータをキャッシュして返す。"""

    files: dict[str, Any] = {}

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


def _build_subagents(
    mcp_tools: list,
    ws_client: Optional[WorkspaceClient] = None,
    override_model=None,
) -> list:
    """Load subagent definitions from YAML and inject dynamic tools."""
    subagents = _load_subagents(_SUBAGENTS_CONFIG_PATH)

    result = []
    for sa in subagents:
        sa = {**sa}  # shallow copy to avoid mutating the cached list's dicts
        if override_model and "model" in sa:
            sa["model"] = override_model
        elif "model" in sa:
            sa["model"] = init_model(model_name=sa["model"], ws=ws_client)

        if sa.get("_pending_mcp_tools"):
            sa["tools"] = mcp_tools + sa.get("tools", [])

        sa["middleware"] = [
            strip_content_block_ids,
            flatten_system_message,
            # サブエージェントの過剰な検索呼び出しを抑制する
            # thread_limit: 1スレッド（1サブエージェント実行）内での最大呼び出し回数
            # run_limit: 会話全体での最大実行回数（サブエージェントのYAML定義のbudgetと合わせること）
            ToolCallLimitMiddleware(
                tool_name="web_search",
                thread_limit=12,
                run_limit=3,
            ),
            ToolCallLimitMiddleware(
                tool_name="web_fetch",
                thread_limit=20,
                run_limit=5,
            ),
        ]

        result.append(sa)
    return result


@mlflow.trace(span_type="UNKNOWN")
async def init_agent(
    model: BaseChatModel,
    workspace_client: Optional[WorkspaceClient] = None,
    checkpointer=None,
    volume_path: Optional[str] = None,
    override_subagent_model: Optional[BaseChatModel] = None,
):

    ws_client = workspace_client or get_sp_workspace_client()
    if not volume_path:
        raise ValueError("volume_path is required")

    mcp_tools = await get_mcp_tools(ws_client)

    def backend(rt):
        return CompositeBackend(
            default=UCVolumesBackend(
                volume_path=volume_path,
                workspace_client=ws_client,
            ),
            routes={
                "/preset/": StateBackend(rt),
            },
        )

    middleware = [
        strip_content_block_ids,
        flatten_system_message,
        create_summarization_tool_middleware(model, backend),
    ]

    subagents = _build_subagents(
        mcp_tools=mcp_tools,
        ws_client=ws_client,
        override_model=override_subagent_model,
    )

    return create_deep_agent(
        tools=mcp_tools
        + [
            web_search,
            web_fetch,
            get_current_time,
        ],
        system_prompt=_load_system_prompt(_SYSTEM_PROMPT_PATH),
        memory=["AGENTS.md"],
        skills=["/preset/skills/", "skills/"],
        model=model,
        backend=backend,
        subagents=subagents,
        checkpointer=checkpointer,
        middleware=middleware,
    )


@invoke()
async def non_streaming(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    outputs = []
    completed_response: dict | None = None
    error_msg: str | None = None
    async for event in streaming(request):
        if event.type == "response.output_item.done":
            outputs.append(event.item)  # type: ignore[attr-defined]
        elif event.type == "response.completed":
            completed_response = getattr(event, "response", None)
        elif event.type == "error":
            error_msg = getattr(event, "message", "Unknown error")
            break

    kwargs: dict[str, Any] = {"output": outputs}

    if completed_response:
        # model
        if completed_response.get("model"):
            kwargs["model"] = completed_response["model"]
        # metadata
        if metadata := completed_response.get("metadata", {}):
            kwargs["metadata"] = metadata
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

    if error_msg is not None:
        kwargs["error"] = ResponseError(message=error_msg)

    return ResponsesAgentResponse(**kwargs)


@stream()
async def streaming(
    request: ResponsesAgentRequest,
) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    try:
        user_workspace_client = get_user_workspace_client()
        volume_path = _get_volume_path(request)
        thread_id = _get_or_create_thread_id(request)

        checkpointer = UCBundleCheckpointer(
            volume_path=volume_path,
            thread_id=thread_id,
            workspace_client=user_workspace_client,
        )

        async with checkpointer:
            model_name = (
                _get_model_name(request) if not USE_FAKE_MODEL else FAKE_MODEL_NAME
            )
            model = init_model(
                model_name=model_name,
                ws=user_workspace_client,
            )
            override_model = None if not USE_FAKE_MODEL else model
            agent = await init_agent(
                model=model,
                workspace_client=user_workspace_client,
                checkpointer=checkpointer,
                volume_path=volume_path,
                override_subagent_model=override_model,
            )

            all_messages = to_chat_completions_input(
                [i.model_dump() for i in request.input]
            )
            # checkpointer が会話履歴を保持するため、最後のメッセージのみ渡す
            messages = {
                "messages": [all_messages[-1]] if all_messages else [],
                "files": _load_preset_files(),
            }
            config = {
                "configurable": {"thread_id": thread_id, "model_name": model_name}
            }

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
                    version="v2",
                ),
                usage_accumulator=usage_accumulator,
                model=model_name,
                model_profile=model.profile if hasattr(model, "profile") else None,
            ):
                yield event
    except Exception as e:
        logger.exception("Streaming error: %s", e)
        yield ResponsesAgentStreamEvent(
            type="error",
            message=str(e),  # type: ignore
        )
