"""agent_utils.py の純粋関数ユニットテスト."""
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from apx_deepagent_chat.backend.agent_utils import (
    _accumulate_usage,
    _detect_subagent_completions,
    _detect_subagent_starts,
    _extract_from_list,
    _extract_text_content,
    _filter_main_agent_messages,
    _handle_subagent_call,
    _iter_node_messages,
    _log_and_yield,
    _normalize_messages,
    _resolve_subagent_name,
    to_real_path,
    to_virtual_path,
)


# ─── to_real_path ────────────────────────────────────────────────────────────


def test_to_real_path_simple():
    result = to_real_path("/Volumes/cat/schema/vol", "/workspace/plan.md")
    assert result == "/Volumes/cat/schema/vol/workspace/plan.md"


def test_to_real_path_root():
    result = to_real_path("/Volumes/cat/schema/vol", "/")
    assert result == "/Volumes/cat/schema/vol"


def test_to_real_path_no_leading_slash():
    result = to_real_path("/Volumes/cat/schema/vol", "file.txt")
    assert result == "/Volumes/cat/schema/vol/file.txt"


def test_to_real_path_trailing_slash_volume():
    result = to_real_path("/Volumes/cat/schema/vol/", "/data/file.csv")
    assert result == "/Volumes/cat/schema/vol/data/file.csv"


def test_to_real_path_nested():
    result = to_real_path("/Volumes/cat/schema/vol", "/a/b/c/d.txt")
    assert result == "/Volumes/cat/schema/vol/a/b/c/d.txt"


# ─── to_virtual_path ─────────────────────────────────────────────────────────


def test_to_virtual_path_simple():
    result = to_virtual_path(
        "/Volumes/cat/schema/vol",
        "/Volumes/cat/schema/vol/workspace/plan.md",
    )
    assert result == "/workspace/plan.md"


def test_to_virtual_path_no_match():
    result = to_virtual_path("/Volumes/cat/schema/vol", "/other/path/file.txt")
    assert result == "/other/path/file.txt"


def test_to_virtual_path_with_dbfs_prefix():
    result = to_virtual_path(
        "/Volumes/cat/schema/vol",
        "dbfs:/Volumes/cat/schema/vol/file.txt",
    )
    assert result == "/file.txt"


def test_to_virtual_path_root_file():
    result = to_virtual_path("/Volumes/cat/schema/vol", "/Volumes/cat/schema/vol/top.md")
    assert result == "/top.md"


# ─── _extract_text_content ────────────────────────────────────────────────────


def test_extract_text_plain_string():
    result = _extract_text_content("hello world")
    assert result == "hello world"


def test_extract_text_list_with_text_block():
    result = _extract_text_content('[{"type": "text", "text": "hello"}]')
    assert result == "hello"


def test_extract_text_list_multiple_blocks():
    payload = '[{"type": "text", "text": "hello"}, {"type": "thought", "text": "ignored"}, {"type": "text", "text": " world"}]'
    result = _extract_text_content(payload)
    assert result == "hello world"


def test_extract_text_invalid_json():
    # starts with "[{" but is invalid JSON → returns original string
    raw = '[{ invalid json'
    result = _extract_text_content(raw)
    assert result == raw


def test_extract_text_python_list():
    result = _extract_text_content([{"type": "text", "text": "from list"}])
    assert result == "from list"


def test_extract_text_python_list_mixed():
    result = _extract_text_content(["plain string", {"type": "text", "text": " appended"}])
    assert result == "plain string appended"


def test_extract_text_non_string_non_list():
    result = _extract_text_content(42)
    assert result == "42"


# ─── _extract_from_list ───────────────────────────────────────────────────────


def test_extract_from_list_empty():
    assert _extract_from_list([]) == ""


def test_extract_from_list_plain_strings():
    assert _extract_from_list(["a", "b"]) == "ab"


def test_extract_from_list_text_blocks():
    blocks = [
        {"type": "text", "text": "hello"},
        {"type": "thought", "text": "ignored"},
        {"type": "text", "text": " world"},
    ]
    assert _extract_from_list(blocks) == "hello world"


def test_extract_from_list_mixed():
    blocks = ["prefix ", {"type": "text", "text": "suffix"}]
    assert _extract_from_list(blocks) == "prefix suffix"


def test_extract_from_list_non_text_dict_skipped():
    blocks = [{"type": "image_url", "url": "http://example.com"}]
    assert _extract_from_list(blocks) == ""


# ─── _log_and_yield ───────────────────────────────────────────────────────────


def test_log_and_yield_returns_same_item():
    item = MagicMock()
    item.type = "test.event"
    item.model_dump.return_value = {"type": "test.event"}
    result = _log_and_yield(item)
    assert result is item


def test_log_and_yield_calls_debug(mocker):
    mock_logger = mocker.patch("apx_deepagent_chat.backend.agent_utils.logger")
    item = MagicMock()
    item.type = "some.event"
    item.model_dump.return_value = {}
    _log_and_yield(item)
    mock_logger.debug.assert_called_once()


# ─── _accumulate_usage ───────────────────────────────────────────────────────


def test_accumulate_usage_adds_tokens():
    ua: dict = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    msg = AIMessage(
        content="hi",
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )
    _accumulate_usage(ua, msg)
    assert ua["input_tokens"] == 10
    assert ua["output_tokens"] == 5
    assert ua["total_tokens"] == 15


def test_accumulate_usage_empty_accumulator():
    ua: dict = {}
    msg = AIMessage(
        content="hi",
        usage_metadata={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
    )
    _accumulate_usage(ua, msg)
    assert ua["input_tokens"] == 3


def test_accumulate_usage_no_metadata():
    ua: dict = {"input_tokens": 5, "output_tokens": 0, "total_tokens": 5}
    msg = AIMessage(content="no usage")
    _accumulate_usage(ua, msg)
    assert ua["input_tokens"] == 5  # unchanged


def test_accumulate_usage_chunk():
    ua: dict = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    chunk = AIMessageChunk(
        content="chunk",
        usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
    )
    _accumulate_usage(ua, chunk)
    assert ua["total_tokens"] == 2


# ─── _normalize_messages ─────────────────────────────────────────────────────


def test_normalize_messages_tool_message_dict():
    msg = ToolMessage(content="placeholder", tool_call_id="tc-1")
    object.__setattr__(msg, "content", {"key": "value"})
    _normalize_messages([msg], {})
    assert isinstance(msg.content, str)
    assert '"key"' in msg.content


def test_normalize_messages_tool_message_list():
    msg = ToolMessage(content=[{"item": 1}], tool_call_id="tc-1")
    ua: dict = {}
    _normalize_messages([msg], ua)
    assert isinstance(msg.content, str)


def test_normalize_messages_string_unchanged():
    msg = ToolMessage(content="already a string", tool_call_id="tc-1")
    _normalize_messages([msg], {})
    assert msg.content == "already a string"


def test_normalize_messages_accumulates_usage():
    ua: dict = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    msg = AIMessage(
        content="hi",
        usage_metadata={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
    )
    _normalize_messages([msg], ua)
    assert ua["total_tokens"] == 10


# ─── _iter_node_messages ─────────────────────────────────────────────────────


def test_iter_node_messages_basic():
    msgs_a = [AIMessage(content="a")]
    msgs_b = [AIMessage(content="b")]
    data = {"node_a": {"messages": msgs_a}, "node_b": {"messages": msgs_b}}
    result = list(_iter_node_messages(data))
    assert len(result) == 2
    names = [r[0] for r in result]
    assert "node_a" in names
    assert "node_b" in names


def test_iter_node_messages_skips_non_dict():
    data = {"node_a": "not-a-dict", "node_b": {"messages": [AIMessage(content="x")]}}
    result = list(_iter_node_messages(data))
    assert len(result) == 1
    assert result[0][0] == "node_b"


def test_iter_node_messages_no_messages_key():
    data = {"node_a": {"other": "data"}}
    result = list(_iter_node_messages(data))
    assert result == []


def test_iter_node_messages_empty_data():
    result = list(_iter_node_messages({}))
    assert result == []


# ─── _filter_main_agent_messages ─────────────────────────────────────────────


def test_filter_tool_message_kept():
    msg = ToolMessage(content="result", tool_call_id="tc-1")
    result = _filter_main_agent_messages([msg])
    assert len(result) == 1
    assert result[0] is msg


def test_filter_ai_with_tool_calls_content_cleared():
    msg = AIMessage(
        content="some text",
        tool_calls=[
            {"id": "tc-1", "name": "task", "args": {}, "type": "tool_call"}
        ],
    )
    result = _filter_main_agent_messages([msg])
    assert len(result) == 1
    assert result[0].content == ""
    assert result[0].tool_calls == msg.tool_calls


def test_filter_ai_without_tool_calls_excluded():
    msg = AIMessage(content="just text")
    result = _filter_main_agent_messages([msg])
    assert result == []


def test_filter_mixed():
    tm = ToolMessage(content="res", tool_call_id="tc-1")
    ai_with_tools = AIMessage(
        content="calling",
        tool_calls=[{"id": "tc-2", "name": "task", "args": {}, "type": "tool_call"}],
    )
    ai_plain = AIMessage(content="plain")
    result = _filter_main_agent_messages([tm, ai_with_tools, ai_plain])
    assert len(result) == 2


# ─── _handle_subagent_call ───────────────────────────────────────────────────


def test_handle_subagent_call_task_tool():
    msg = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "tc-1",
                "name": "task",
                "args": {"subagent_type": "research", "description": "find info"},
                "type": "tool_call",
            }
        ],
    )
    result = _handle_subagent_call(msg)
    assert "tc-1" in result
    assert result["tc-1"]["type"] == "research"
    assert result["tc-1"]["status"] == "pending"


def test_handle_subagent_call_ignores_non_task():
    msg = AIMessage(
        content="",
        tool_calls=[
            {"id": "tc-1", "name": "web_search", "args": {"query": "test"}, "type": "tool_call"}
        ],
    )
    result = _handle_subagent_call(msg)
    assert result == {}


def test_handle_subagent_call_description_truncated():
    long_desc = "a" * 81
    msg = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "tc-1",
                "name": "task",
                "args": {"subagent_type": "coder", "description": long_desc},
                "type": "tool_call",
            }
        ],
    )
    result = _handle_subagent_call(msg)
    assert len(result["tc-1"]["description"]) == 80


def test_handle_subagent_call_mixed_tools():
    msg = AIMessage(
        content="",
        tool_calls=[
            {"id": "tc-1", "name": "task", "args": {"subagent_type": "writer", "description": ""}, "type": "tool_call"},
            {"id": "tc-2", "name": "web_fetch", "args": {"url": "http://example.com"}, "type": "tool_call"},
        ],
    )
    result = _handle_subagent_call(msg)
    assert len(result) == 1
    assert "tc-1" in result


# ─── _detect_subagent_starts ─────────────────────────────────────────────────


def test_detect_subagent_starts_basic():
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "tc-1",
                "name": "task",
                "args": {"subagent_type": "research", "description": "do research"},
                "type": "tool_call",
            }
        ],
    )
    data = {"model": {"messages": [ai_msg]}}
    active_subagents: dict = {}
    _detect_subagent_starts(data, active_subagents)
    assert "tc-1" in active_subagents
    assert active_subagents["tc-1"]["status"] == "pending"
    assert active_subagents["tc-1"]["type"] == "research"


def test_detect_subagent_starts_no_model_node():
    data = {"other": {"messages": []}}
    active_subagents: dict = {}
    _detect_subagent_starts(data, active_subagents)
    assert active_subagents == {}


def test_detect_subagent_starts_model_not_dict():
    data = {"model": "not-a-dict"}
    active_subagents: dict = {}
    _detect_subagent_starts(data, active_subagents)
    assert active_subagents == {}


# ─── _detect_subagent_completions ────────────────────────────────────────────


def test_detect_subagent_completions_running():
    active_subagents = {"tc-1": {"type": "research", "status": "running"}}
    msg = ToolMessage(content="result", tool_call_id="tc-1")
    data = {"tools": {"messages": [msg]}}
    result = list(_detect_subagent_completions(data, active_subagents))
    assert len(result) == 1
    assert result[0].type == "subagent.end"
    assert active_subagents["tc-1"]["status"] == "complete"


def test_detect_subagent_completions_pending_not_completed():
    active_subagents = {"tc-1": {"type": "research", "status": "pending"}}
    msg = ToolMessage(content="result", tool_call_id="tc-1")
    data = {"tools": {"messages": [msg]}}
    result = list(_detect_subagent_completions(data, active_subagents))
    assert result == []


def test_detect_subagent_completions_no_tools_node():
    active_subagents = {"tc-1": {"type": "research", "status": "running"}}
    data = {"model": {"messages": []}}
    result = list(_detect_subagent_completions(data, active_subagents))
    assert result == []


def test_detect_subagent_completions_unknown_id():
    active_subagents = {"tc-1": {"type": "research", "status": "running"}}
    msg = ToolMessage(content="result", tool_call_id="tc-unknown")
    data = {"tools": {"messages": [msg]}}
    result = list(_detect_subagent_completions(data, active_subagents))
    assert result == []


# ─── _resolve_subagent_name ──────────────────────────────────────────────────


def test_resolve_direct_from_ns_key():
    active_subagents = {"tc-1": {"type": "research", "status": "pending"}}
    name, call_id = _resolve_subagent_name("tools:tc-1", active_subagents, {})
    assert name == "research"
    assert call_id == "tc-1"
    assert active_subagents["tc-1"]["status"] == "running"


def test_resolve_fallback_to_pending():
    """直接解決失敗 → pending エントリを線形探索."""
    active_subagents = {"tc-1": {"type": "coder", "status": "pending"}}
    # tc-2 は存在しないため直接解決に失敗し、tc-1 が線形探索で見つかる
    name, call_id = _resolve_subagent_name("tools:tc-2", active_subagents, {})
    assert name == "coder"
    assert call_id == "tc-1"
    assert active_subagents["tc-1"]["status"] == "running"


def test_resolve_fallback_to_ai_message_name():
    """pending なし → data内AIMessage.name を使う."""
    active_subagents = {"tc-1": {"type": "unknown", "status": "running"}}
    ai_msg = AIMessage(content="hi", name="researcher")
    data = {"node1": {"messages": [ai_msg]}}
    name, call_id = _resolve_subagent_name("tools:tc-2", active_subagents, data)
    assert name == "researcher"
    assert call_id == ""


def test_resolve_completely_unknown():
    """全フォールバック失敗 → ("unknown", "")."""
    name, call_id = _resolve_subagent_name("tools:tc-x", {}, {})
    assert name == "unknown"
    assert call_id == ""
