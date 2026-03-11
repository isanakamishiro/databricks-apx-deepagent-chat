import json
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import cache
from typing import Any, AsyncGenerator, AsyncIterator, Iterator, Optional
from uuid import uuid4

from databricks.sdk import WorkspaceClient
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from mlflow.genai.agent_server import get_request_headers
from mlflow.types.responses import (
    ResponsesAgentStreamEvent,
    create_text_delta,
    create_text_output_item,
    output_to_responses_items_stream,
)

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


# ─── テキスト抽出 ──────────────────────────────────────────────────────────────


def _extract_from_list(blocks: list) -> str:
    """content ブロックのリストから text 部分のみを結合して返す."""
    parts = []
    for block in blocks:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)


def _extract_text_content(content) -> str:
    """AIMessage の content からテキスト部分のみを抽出する.

    一部モデル (Gemini, GPT-oss) は content を JSON 配列の文字列で返す:
      '[{"type": "text", "text": "...", "thoughtSignature": "..."}]'
    この場合、"text" タイプのブロックの text フィールドのみを結合して返す。
    通常の文字列や Python list の場合も適切に処理する。
    """
    if isinstance(content, str):
        stripped = content.strip()
        if stripped.startswith("[{"):  # JSON オブジェクト配列の場合のみパース試行
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return _extract_from_list(parsed)
            except (json.JSONDecodeError, ValueError):
                pass
        return content
    if isinstance(content, list):
        return _extract_from_list(content)
    return str(content)


# ─── Databricks クライアント ─────────────────────────────────────────────────


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


# ─── ストリームイベント処理: 共通ユーティリティ ──────────────────────────────


def _log_and_yield(item: ResponsesAgentStreamEvent) -> ResponsesAgentStreamEvent:
    """イベントをデバッグログに記録してそのまま返す."""
    logger.debug("[yield] type=%s data=%s", item.type, item.model_dump())
    return item


def _accumulate_usage(usage_accumulator: dict, msg) -> None:
    """AIMessage/AIMessageChunk の usage_metadata をアキュムレータに加算する."""
    um = getattr(msg, "usage_metadata", None)
    if not um:
        return
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        val = um.get(key, 0) if isinstance(um, dict) else getattr(um, key, 0)
        usage_accumulator[key] = usage_accumulator.get(key, 0) + val


def _normalize_messages(msgs: list, ua: dict) -> None:
    """メッセージリストをインプレースで正規化し、usage を集計する.

    - ToolMessage の content が非文字列なら JSON 文字列化
    - AIMessage/AIMessageChunk の usage_metadata を ua に加算
    """
    for msg in msgs:
        if isinstance(msg, ToolMessage) and not isinstance(msg.content, str):
            msg.content = json.dumps(msg.content)
        if isinstance(msg, (AIMessage, AIMessageChunk)):
            _accumulate_usage(ua, msg)


def _iter_node_messages(data: Any) -> Iterator[tuple[str, list]]:
    """data の各ノードから (node_name, messages) を yield する.

    node_data が dict 以外（Overwrite 等）はスキップする。
    """
    for node_name, node_data in data.items():
        if not isinstance(node_data, dict):
            continue
        msgs = node_data.get("messages")
        if isinstance(msgs, list):
            yield node_name, msgs


def _iter_output_items(
    msgs: list, output_items: list
) -> Iterator[ResponsesAgentStreamEvent]:
    """msgs を output_to_responses_items_stream に通し、done items を集約しながら yield する."""
    for item in output_to_responses_items_stream(msgs):  # type: ignore[arg-type]
        if item.type == "response.output_item.done":
            if (i := getattr(item, "item", None)) is not None:
                output_items.append(i)
        yield _log_and_yield(item)


# ─── ストリームイベント処理: メッセージ変換 ─────────────────────────────────


@dataclass
class _StreamState:
    """process_agent_astream_events のストリーム処理中の状態を保持する."""

    accumulated_text: str = ""
    text_item_id: str | None = None
    output_items: list[dict[str, Any]] = field(default_factory=list)


def _filter_main_agent_messages(msgs: list) -> list:
    """メインエージェントのメッセージをフィルタリングする.

    - ToolMessage: そのまま保持（ツール結果）
    - AIMessage with tool_calls: tool_calls のみ保持（テキストは messages モードで送信済み）
    - それ以外: 除外（テキストの二重出力を防ぐ）
    """
    filtered = []
    for msg in msgs:
        if isinstance(msg, ToolMessage):
            filtered.append(msg)
        elif isinstance(msg, (AIMessage, AIMessageChunk)) and getattr(msg, "tool_calls", None):
            filtered.append(AIMessage(content="", tool_calls=msg.tool_calls, id=msg.id))
    return filtered


def _process_subagent_updates(
    data: Any, ua: dict, output_items: list
) -> Iterator[ResponsesAgentStreamEvent]:
    """サブエージェントの updates を処理して yield する."""
    for _, msgs in _iter_node_messages(data):
        _normalize_messages(msgs, ua)
        yield from _iter_output_items(msgs, output_items)


def _process_main_agent_updates(
    data: Any, ua: dict, output_items: list
) -> Iterator[ResponsesAgentStreamEvent]:
    """メインエージェントの updates を処理して yield する.

    テキストは messages モードでストリーミング済みなので除外し二重表示を防ぐ。
    ToolMessage（ツール結果）と tool_calls 付き AIMessage（ツール呼び出し表示用）のみ yield する。
    """
    for _, msgs in _iter_node_messages(data):
        _normalize_messages(msgs, ua)
        filtered = _filter_main_agent_messages(msgs)
        if filtered:
            yield from _iter_output_items(filtered, output_items)


def _process_main_agent_messages(
    data: Any, state: _StreamState
) -> Iterator[ResponsesAgentStreamEvent]:
    """メインエージェントの messages イベントを処理する.

    AIMessageChunk のテキストトークンを抽出して yield し、
    state.accumulated_text と state.text_item_id を更新する。
    """
    try:
        chunk = data[0]
        if isinstance(chunk, AIMessageChunk) and (content := chunk.content):
            text = _extract_text_content(content)
            if text:
                state.accumulated_text += text
                state.text_item_id = chunk.id
                yield _log_and_yield(
                    ResponsesAgentStreamEvent(
                        **create_text_delta(delta=text, item_id=chunk.id or str(uuid4()))
                    )
                )
    except Exception as e:
        logger.exception(f"Error processing agent stream event: {e}")


def _finalize_stream(
    state: _StreamState,
    ua: dict,
    model: str | None,
    max_context_tokens: int | None,
) -> Iterator[ResponsesAgentStreamEvent]:
    """ストリーム完了後の response.output_item.done と response.completed を emit する."""
    if state.accumulated_text:
        text_output_item = create_text_output_item(
            state.accumulated_text, state.text_item_id or str(uuid4())
        )
        state.output_items.append(text_output_item)
        yield _log_and_yield(
            ResponsesAgentStreamEvent(
                type="response.output_item.done", item=text_output_item  # type: ignore[call-arg]
            )
        )

    total_tokens = ua.get("total_tokens", 0)
    output_tokens = ua.get("output_tokens", 0)
    usage_data: dict[str, Any] = {
        "input_tokens": total_tokens - output_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 0},
    }
    response_data: dict[str, Any] = {
        "id": f"resp-{str(uuid4())[:8]}",
        "status": "completed",
        "output": state.output_items,
        "usage": usage_data,
    }
    if model is not None:
        response_data["model"] = model
    if max_context_tokens is not None:
        response_data["max_context_tokens"] = max_context_tokens

    yield _log_and_yield(
        ResponsesAgentStreamEvent(
            type="response.completed",
            response=response_data,  # type: ignore[call-arg]
        )
    )


# ─── サブエージェントライフサイクル管理 ──────────────────────────────────────


def _handle_subagent_call(msg) -> dict[str, dict]:
    """AIMessage の tool_calls から task ツール呼び出しを抽出して返す.

    Returns:
        tool_call_id -> {type, description, status: "pending"} のマッピング
    """
    return {
        tc["id"]: {
            "type": tc["args"].get("subagent_type"),
            "description": tc["args"].get("description", "")[:80],
            "status": "pending",
        }
        for tc in getattr(msg, "tool_calls", [])
        if tc["name"] == "task"
    }


def _detect_subagent_starts(data: dict, active_subagents: dict[str, dict]) -> None:
    """model node の AIMessage から task tool calls を検出して active_subagents を更新する."""
    model_node = data.get("model")
    if not isinstance(model_node, dict):
        return
    for msg in model_node.get("messages", []):
        active_subagents.update(_handle_subagent_call(msg))


def _detect_subagent_completions(
    data: dict, active_subagents: dict[str, dict]
) -> Iterator[ResponsesAgentStreamEvent]:
    """tools node の ToolMessage からサブエージェント完了を検出して subagent.end を yield する."""
    tools_node = data.get("tools")
    if not isinstance(tools_node, dict):
        return
    for msg in tools_node.get("messages", []):
        if getattr(msg, "type", None) == "tool":
            sub = active_subagents.get(msg.tool_call_id)
            if sub and sub.get("status") == "running":
                sub["status"] = "complete"
                yield _log_and_yield(
                    ResponsesAgentStreamEvent(
                        type="subagent.end",
                        name=sub.get("type") or "unknown",  # type: ignore[call-arg]
                        call_id=msg.tool_call_id,  # type: ignore[call-arg]
                    )
                )


def _resolve_subagent_name(
    ns_key: str, active_subagents: dict[str, dict], data: Any
) -> tuple[str, str]:
    """サブエージェントの名前と tool_call_id を解決し、pending エントリを running に遷移させる.

    LangGraph の ns フォーマット "tools:<tool_call_id>" を使ってまず直接解決を試みる。
    失敗した場合は pending エントリを線形探索し、最終的に data 内の AIMessage.name を参照する。

    Returns:
        (agent_name, tool_call_id) のタプル。tool_call_id は active_subagents のキーと一致する。
    """
    # LangGraph: ns_key = "tools:<tool_call_id>" から直接解決
    parts = ns_key.split(":", 1)
    if len(parts) == 2:
        tc_id = parts[1]
        sub = active_subagents.get(tc_id)
        if sub and sub.get("status") == "pending":
            sub["status"] = "running"
            return sub.get("type") or "unknown", tc_id

    # フォールバック: pending エントリを線形探索（ns_key が UUID7 形式の場合など）
    for tc_id, sub in active_subagents.items():
        if sub.get("status") == "pending":
            sub["status"] = "running"
            return sub.get("type") or "unknown", tc_id

    # フォールバック: data 内の AIMessage.name を参照
    for _, msgs in _iter_node_messages(data):
        for msg in msgs:
            if isinstance(msg, (AIMessage, AIMessageChunk)):
                if name := getattr(msg, "name", None):
                    return name, ""

    return "unknown", ""


# ─── メインのストリーム処理関数 ──────────────────────────────────────────────


async def process_agent_astream_events(
    async_stream: AsyncIterator[Any],
    usage_accumulator: dict[str, int] | None = None,
    model: str | None = None,
    max_context_tokens: int | None = None,
) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    """agent.astream() のストリームを受け取り ResponsesAgentStreamEvent を yield する.

    v2 streaming format（chunk["type"], chunk["ns"], chunk["data"]）に対応。
    ns == () → メインエージェント、ns != () → サブエージェントを区別。

    メインエージェント (ns == ()):
      - updates: ツール呼び出し・結果を処理し、サブエージェントのライフサイクルを検出
      - messages: LLM トークンをストリーミング

    サブエージェント (ns != ()):
      - updates のみ処理（messages はスキップ）
      - 初回イベントで subagent.start を emit

    ストリーム完了後:
      - 集約テキストの response.output_item.done を emit
      - 全 output items + usage を含む response.completed を emit

    Args:
        async_stream: agent.astream() の非同期イテレータ
        usage_accumulator: トークン使用量を蓄積する辞書（破壊的変更）
        model: response.completed に含めるモデル名
        max_context_tokens: response.completed に含めるコンテキスト長
    """
    state = _StreamState()
    _ua = usage_accumulator if usage_accumulator is not None else {}
    active_subagents: dict[str, dict] = {}  # tool_call_id -> subagent info
    seen_ns: set[str] = set()  # 既に subagent.start を発行した namespace

    async for chunk in async_stream:
        chunk_type = chunk["type"]
        ns = chunk["ns"]
        data = chunk["data"]

        if not ns:  # メインエージェント (ns == ())
            if chunk_type == "updates":
                _detect_subagent_starts(data, active_subagents)
                for item in _process_main_agent_updates(data, _ua, state.output_items):
                    yield item
                for item in _detect_subagent_completions(data, active_subagents):
                    yield item
            elif chunk_type == "messages":
                for item in _process_main_agent_messages(data, state):
                    yield item

        else:  # サブエージェント (ns != ()): updates のみ処理
            if chunk_type == "updates":
                ns_key = ns[0]
                if ns_key not in seen_ns:
                    seen_ns.add(ns_key)
                    agent_name, subagent_call_id = _resolve_subagent_name(
                        ns_key, active_subagents, data
                    )
                    yield _log_and_yield(
                        ResponsesAgentStreamEvent(
                            type="subagent.start",
                            name=agent_name,  # type: ignore[call-arg]
                            call_id=subagent_call_id,  # type: ignore[call-arg]
                        )
                    )
                for item in _process_subagent_updates(data, _ua, state.output_items):
                    yield item

    logger.debug(
        "[stream] completed. accumulated_text_len=%d output_items=%d",
        len(state.accumulated_text),
        len(state.output_items),
    )
    for item in _finalize_stream(state, _ua, model, max_context_tokens):
        yield item


# ─── Unity Catalog Volumes パス変換 ─────────────────────────────────────────


def to_real_path(volume_path: str, virtual_path: str) -> str:
    """仮想パスを Unity Catalog Volumes 上の実パスに変換する.

    Args:
        volume_path: Volume のルートパス (例: "/Volumes/catalog/schema/volume").
        virtual_path: 仮想絶対パス (例: "/workspace/plan.md").

    Returns:
        Volumes 上の実パス (例: "/Volumes/catalog/schema/volume/workspace/plan.md").
    """
    vp = virtual_path if virtual_path.startswith("/") else "/" + virtual_path
    result = volume_path.rstrip("/") + vp
    # "/Volumes/.../vol/" のように末尾スラッシュが残る場合は除去 (ルート "/" の場合)
    if result.endswith("/") and len(result) > 1:
        result = result.rstrip("/")
    return result


def to_virtual_path(volume_path: str, real_path: str) -> str:
    """Unity Catalog Volumes 上の実パスを仮想パスに変換する.

    Args:
        volume_path: Volume のルートパス (例: "/Volumes/catalog/schema/volume").
        real_path: Volumes 上の実パス (例: "/Volumes/catalog/schema/volume/workspace/plan.md").
            read_files の _metadata.file_path は "dbfs:" プレフィクス付きの場合がある.

    Returns:
        仮想絶対パス (例: "/workspace/plan.md").
    """
    prefix = volume_path.rstrip("/")
    # read_files の _metadata.file_path は "dbfs:" プレフィクスが付く場合がある
    path = real_path.removeprefix("dbfs:")
    if path.startswith(prefix):
        rest = path[len(prefix) :]
        return rest if rest.startswith("/") else "/" + rest
    return real_path
