import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, AsyncIterator, Iterator
from uuid import uuid4

from langchain_core.language_models.model_profile import ModelProfile
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from mlflow.types.responses import (
    ResponsesAgentStreamEvent,
    create_reasoning_item,
    create_text_delta,
    create_text_output_item,
    output_to_responses_items_stream,
)

logger = logging.getLogger(__name__)

# モジュールレベルでコンパイル済みXMLパターン（関数呼び出しごとの再コンパイルを回避）
_XML_REASONING_PATTERNS = [
    re.compile(r'<thinking>(.*?)</thinking>', re.DOTALL),  # LLaMA
    re.compile(r'<think>(.*?)</think>', re.DOTALL),        # その他
]


# ─── テキスト・Reasoning 抽出 ──────────────────────────────────────────────────


def _process_blocks(blocks: list) -> tuple[list[str], list[str]]:
    """dict ブロックのリストからテキストと reasoning を抽出する.

    str 形式（JSONパース後）・list 形式の両方に対応する共通処理。
    """
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    for block in blocks:
        if isinstance(block, str):
            text_parts.append(block)
        elif isinstance(block, dict):
            block_type = block.get("type")
            # GPT-OSS-120B: type="reasoning"
            if block_type == "reasoning":
                summary = block.get("summary", [])
                if isinstance(summary, list):
                    for item in summary:
                        if isinstance(item, dict) and item.get("type") == "summary_text":
                            reasoning_parts.append(item.get("text", ""))
            elif block_type == "thought":
                reasoning_parts.append(block.get("content", ""))
            elif block_type == "text":
                text_parts.append(block.get("text", ""))
                if "thoughtSignature" in block:
                    reasoning_parts.append(block.get("thoughtSignature", ""))
    return text_parts, reasoning_parts


def _extract_text_and_reasoning(content: str | list | Any) -> tuple[str, str]:
    """AIMessage の content からテキストとreasoningを分離して返す.

    - str 形式: JSON配列文字列 → _process_blocks、次に XMLタグ → regex 抽出を試みる
    - list 形式: 構造化ブロックのみ処理（XML抽出は行わない）
    - その他: str() に変換して返す

    Returns:
        (text, reasoning) のタプル
    """
    # JSON配列文字列形式
    if isinstance(content, str):
        stripped = content.strip()
        if stripped.startswith("[{"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    text_parts, reasoning_parts = _process_blocks(parsed)
                    return "".join(text_parts), " ".join(reasoning_parts)
            except (json.JSONDecodeError, ValueError):
                pass

        # XMLタグ形式
        for pattern in _XML_REASONING_PATTERNS:
            matches = list(pattern.finditer(content))
            if matches:
                reasoning = "".join(m.group(1) for m in matches)
                text_only = pattern.sub('', content)
                return text_only, reasoning

        return content, ""

    # Pythonリスト形式（構造化ブロックのみ、XML処理なし）
    if isinstance(content, list):
        text_parts, reasoning_parts = _process_blocks(content)
        return "".join(text_parts), " ".join(reasoning_parts)

    return str(content), ""


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
    accumulated_reasoning: str = ""
    reasoning_item_id: str | None = None
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
        elif isinstance(msg, (AIMessage, AIMessageChunk)) and getattr(
            msg, "tool_calls", None
        ):
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

    AIMessageChunk のテキストトークンと reasoning を分離して yield し、
    state を更新する。
    """
    try:
        chunk = data[0]
        if isinstance(chunk, AIMessageChunk) and (content := chunk.content):
            text, reasoning = _extract_text_and_reasoning(content)
            item_id = chunk.id or str(uuid4())

            # テキストデルタ
            if text:
                state.accumulated_text += text
                state.text_item_id = item_id
                yield _log_and_yield(
                    ResponsesAgentStreamEvent(
                        **create_text_delta(delta=text, item_id=item_id)
                    )
                )

            # Reasoningデルタ
            if reasoning:
                state.accumulated_reasoning += reasoning
                state.reasoning_item_id = item_id
                yield _log_and_yield(
                    ResponsesAgentStreamEvent.model_validate(
                        {
                            "type": "response.output_text.reasoning.delta",
                            "delta": reasoning,
                            "item_id": item_id,
                        }
                    )
                )
    except Exception as e:
        logger.exception(f"Error processing agent stream event: {e}")


def _finalize_stream(
    state: _StreamState,
    ua: dict,
    model: str | None,
    max_input_tokens: int | None,
) -> Iterator[ResponsesAgentStreamEvent]:
    """ストリーム完了後の response.output_item.done と response.completed を emit する."""
    if state.accumulated_text:
        text_output_item = create_text_output_item(
            state.accumulated_text, state.text_item_id or str(uuid4())
        )
        state.output_items.append(text_output_item)
        yield _log_and_yield(
            ResponsesAgentStreamEvent(
                type="response.output_item.done",
                item=text_output_item,  # type: ignore[call-arg]
            )
        )

    # Reasoning item done
    if state.accumulated_reasoning:
        reasoning_output_item = create_reasoning_item(
            id=state.reasoning_item_id or str(uuid4()),
            reasoning_text=state.accumulated_reasoning,
        )
        state.output_items.append(reasoning_output_item)
        yield _log_and_yield(
            ResponsesAgentStreamEvent(
                type="response.output_item.done",
                item=reasoning_output_item,  # type: ignore[call-arg]
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

    response_data["metadata"] = {}
    if max_input_tokens is not None:
        response_data["metadata"]["max_input_tokens"] = str(max_input_tokens)

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
    model_profile: ModelProfile | None = None,
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
        model_profile: モデルプロファイル（max_input_tokens 等）
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
        "[stream] completed. accumulated_text_len=%d reasoning_len=%d output_items=%d",
        len(state.accumulated_text),
        len(state.accumulated_reasoning),
        len(state.output_items),
    )

    max_input_tokens = model_profile.get("max_input_tokens") if model_profile else None
    for item in _finalize_stream(state, _ua, model, max_input_tokens):
        yield item
