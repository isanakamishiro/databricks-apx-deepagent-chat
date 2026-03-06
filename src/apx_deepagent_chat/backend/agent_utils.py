import logging
from typing import Any, AsyncGenerator, AsyncIterator, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

from databricks.sdk import WorkspaceClient
import json
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from mlflow.genai.agent_server import get_request_headers
from mlflow.types.responses import (
    ResponsesAgentStreamEvent,
    create_text_delta,
    create_text_output_item,
    output_to_responses_items_stream,
)


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
        if stripped.startswith("["):
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


def get_user_workspace_client() -> WorkspaceClient:
    token = get_request_headers().get("x-forwarded-access-token")
    if not token:
        return WorkspaceClient()

    return WorkspaceClient(token=token, auth_type="pat")


def get_databricks_host_from_env() -> Optional[str]:
    try:
        w = WorkspaceClient()
        return w.config.host
    except Exception as e:
        logging.exception(f"Error getting databricks host from env: {e}")
        return None


async def process_agent_astream_events(
    async_stream: AsyncIterator[Any],
    usage_accumulator: dict[str, int] | None = None,
    model: str | None = None,
    max_context_tokens: int | None = None,
) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    """
    Generic helper to process agent stream events and yield ResponsesAgentStreamEvent objects.

    サブエージェント (namespace != ()) の場合:
      - messages モード: lc_agent_name から名前を検出し <name> マーカーを emit、トークンはスキップ
      - updates モード: ツール呼び出し・完了メッセージを yield
    メインエージェント (namespace == ()) の場合:
      - messages / updates とも通常通り yield

    ストリーム完了後:
      - 集約テキストの response.output_item.done を emit
      - 全 output items + usage を含む response.completed を emit
        （BFF の @databricks/ai-sdk-provider が usage を取得するために必要）

    Args:
        async_stream: The async iterator from agent.astream()
        usage_accumulator: Optional dict to accumulate token usage
            (keys: "input_tokens", "output_tokens"). Mutated in place.
        model: Optional model name to include in the response.completed event.
        max_context_tokens: Optional max context window size to include in
            the response.completed event.
    """
    _current_agent_name: str | None = None
    _accumulated_text: str = ""
    _text_item_id: str | None = None
    _all_output_items: list[dict[str, Any]] = []

    def _log_and_yield(item: ResponsesAgentStreamEvent) -> ResponsesAgentStreamEvent:
        logger.debug("[yield] type=%s data=%s", item.type, item.model_dump())
        return item

    def _accumulate_usage(msg):
        """AIMessage/AIMessageChunk の usage_metadata をアキュムレータに加算する."""
        if usage_accumulator is None:
            return
        um = getattr(msg, "usage_metadata", None)
        if not um:
            return
        if isinstance(um, dict):
            usage_accumulator["input_tokens"] = usage_accumulator.get(
                "input_tokens", 0
            ) + um.get("input_tokens", 0)
            usage_accumulator["output_tokens"] = usage_accumulator.get(
                "output_tokens", 0
            ) + um.get("output_tokens", 0)
            usage_accumulator["total_tokens"] = usage_accumulator.get(
                "total_tokens", 0
            ) + um.get("total_tokens", 0)
        else:
            usage_accumulator["input_tokens"] = usage_accumulator.get(
                "input_tokens", 0
            ) + getattr(um, "input_tokens", 0)
            usage_accumulator["output_tokens"] = usage_accumulator.get(
                "output_tokens", 0
            ) + getattr(um, "output_tokens", 0)
            usage_accumulator["total_tokens"] = usage_accumulator.get(
                "total_tokens", 0
            ) + getattr(um, "total_tokens", 0)

    def _collect_output_items(stream_event: ResponsesAgentStreamEvent):
        """response.output_item.done イベントの item を集約リストに追加する."""
        if stream_event.type == "response.output_item.done":
            item = getattr(stream_event, "item", None)
            if item is not None:
                _all_output_items.append(item)

    async for event in async_stream:
        # subgraphs=True: event is a 3-tuple (namespace, mode, data)
        _ns, mode, data = event
        logger.debug("[stream] ns=%s mode=%s data_type=%s", _ns, mode, type(data).__name__)

        if _ns != ():
            # --- サブエージェントのイベント ---
            if mode == "messages":
                # トークンストリーミングはスキップ、名前検出のみ
                try:
                    _unused_token, metadata = data
                    agent_name = metadata.get("lc_agent_name")
                    if agent_name and agent_name != _current_agent_name:
                        _current_agent_name = agent_name
                        yield _log_and_yield(ResponsesAgentStreamEvent(
                            type="subagent.start",
                            name=agent_name,  # type: ignore[call-arg]
                        ))
                except Exception as e:
                    logging.exception(f"Error extracting subagent name: {e}")
                continue

            if mode == "updates":
                # サブエージェントの updates は yield（ツール呼び出し・結果）
                for node_data in data.values():
                    if not node_data:
                        continue
                    if node_data.get("messages") and isinstance(
                        node_data.get("messages"), list
                    ):
                        for msg in node_data["messages"]:
                            if isinstance(msg, ToolMessage) and not isinstance(
                                msg.content, str
                            ):
                                msg.content = json.dumps(msg.content)
                            if isinstance(msg, (AIMessage, AIMessageChunk)):
                                _accumulate_usage(msg)
                        for item in output_to_responses_items_stream(
                            node_data["messages"]
                        ):
                            _collect_output_items(item)
                            yield _log_and_yield(item)
                continue

        # --- メインエージェントのイベント ---
        if _current_agent_name is not None:
            yield _log_and_yield(ResponsesAgentStreamEvent(
                type="subagent.end",
                name=_current_agent_name,  # type: ignore[call-arg]
            ))
            _current_agent_name = None

        if mode == "updates":
            for node_data in data.values():
                if not node_data:
                    continue
                if node_data.get("messages") and isinstance(
                    node_data.get("messages"), list
                ):
                    # メインエージェントの updates では、テキストは "messages"
                    # モードでストリーミング済みなので除外し二重表示を防ぐ。
                    # ToolMessage（ツール結果）と tool_calls 付き AIMessage
                    # （ツール呼び出し表示用）のみ yield する。
                    filtered_msgs = []
                    for msg in node_data["messages"]:
                        if isinstance(msg, (AIMessage, AIMessageChunk)):
                            _accumulate_usage(msg)
                        if isinstance(msg, ToolMessage):
                            if not isinstance(msg.content, str):
                                msg.content = json.dumps(msg.content)
                            filtered_msgs.append(msg)
                        elif isinstance(msg, (AIMessage, AIMessageChunk)):
                            if getattr(msg, "tool_calls", None):
                                # テキストを除去し tool_calls のみ保持
                                stripped = AIMessage(
                                    content="",
                                    tool_calls=msg.tool_calls,
                                    id=msg.id,
                                )
                                filtered_msgs.append(stripped)
                    if filtered_msgs:
                        for item in output_to_responses_items_stream(filtered_msgs):  # type: ignore[arg-type]
                            _collect_output_items(item)
                            yield _log_and_yield(item)
        elif mode == "messages":
            try:
                chunk = data[0]
                if isinstance(chunk, AIMessageChunk) and (content := chunk.content):
                    text = _extract_text_content(content)
                    if text:
                        _accumulated_text += text
                        _text_item_id = chunk.id
                        yield _log_and_yield(ResponsesAgentStreamEvent(
                            **create_text_delta(delta=text, item_id=chunk.id)
                        ))
            except Exception as e:
                logging.exception(f"Error processing agent stream event: {e}")

    # --- ストリーム完了後 ---
    logger.debug("[stream] completed. accumulated_text_len=%d output_items=%d", len(_accumulated_text), len(_all_output_items))

    # 集約テキストの response.output_item.done を emit
    if _accumulated_text:
        text_output_item = create_text_output_item(
            _accumulated_text, _text_item_id or str(uuid4())
        )
        _all_output_items.append(text_output_item)
        yield _log_and_yield(ResponsesAgentStreamEvent(
            type="response.output_item.done", item=text_output_item  # type: ignore[call-arg]
        ))

    # response.completed を emit（mlflow 準拠の type）
    _ua = usage_accumulator or {}
    _total = _ua.get("total_tokens", 0)
    _output = _ua.get("output_tokens", 0)
    usage_data: dict[str, Any] = {
        "input_tokens": _total - _output,
        "output_tokens": _output,
        "total_tokens": _total,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 0},
    }
    response_data: dict[str, Any] = {
        "id": f"resp-{str(uuid4())[:8]}",
        "status": "completed",
        "output": _all_output_items,
        "usage": usage_data,
    }
    if model is not None:
        response_data["model"] = model
    if max_context_tokens is not None:
        response_data["max_context_tokens"] = max_context_tokens

    yield _log_and_yield(ResponsesAgentStreamEvent(
        type="response.completed",
        response=response_data,  # type: ignore[call-arg]
    ))

    # responses.completed を emit（BFF の @databricks/ai-sdk-provider 用）
    # プロバイダーは "responses.completed" から usage を取得し streamText の
    # onFinish → data-usage としてフロントエンドに伝播する。
    yield _log_and_yield(ResponsesAgentStreamEvent(
        type="responses.completed",
        response=response_data,  # type: ignore[call-arg]
    ))


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
