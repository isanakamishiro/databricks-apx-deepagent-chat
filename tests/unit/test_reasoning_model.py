"""reasoning_model.py の _translate_openai_with_reasoning ユニットテスト."""
from langchain_core.messages import AIMessage, AIMessageChunk

# トランスレータを登録するために import する（副作用として register_translator が実行される）
from apx_deepagent_chat.backend.agent.reasoning_model import (
    _strip_index,
    _translate_openai_with_reasoning,
)


# ─── _strip_index ────────────────────────────────────────────────────────────


def test_strip_index_removes_index_field():
    block = {"type": "text", "text": "hello", "index": 0}
    result = _strip_index(block)
    assert result == {"type": "text", "text": "hello"}
    assert "index" not in result


def test_strip_index_no_index_unchanged():
    block = {"type": "text", "text": "hello"}
    result = _strip_index(block)
    assert result == {"type": "text", "text": "hello"}


# ─── _translate_openai_with_reasoning ────────────────────────────────────────


def _make_message(**kwargs) -> AIMessage:
    """テスト用 AIMessage を生成するヘルパー."""
    return AIMessage(**kwargs)


def test_translate_includes_tool_calls_when_present():
    """tool_calls が content_blocks に tool_call ブロックとして含まれること."""
    msg = _make_message(
        content="",
        tool_calls=[{"id": "call_1", "name": "my_tool", "args": {"key": "val"}, "type": "tool_call"}],
        additional_kwargs={"reasoning": "let me think"},
        response_metadata={"model_provider": "openai_with_reasoning"},
    )
    blocks = msg.content_blocks

    tool_blocks = [b for b in blocks if b.get("type") == "tool_call"]
    assert len(tool_blocks) == 1
    assert tool_blocks[0].get("id") == "call_1"
    assert tool_blocks[0].get("name") == "my_tool"
    assert tool_blocks[0].get("args") == {"key": "val"}


def test_translate_tool_calls_fields_mapped_correctly():
    """id / name / args が正しくマッピングされること."""
    msg = _make_message(
        content="",
        tool_calls=[{"id": "tc-abc", "name": "search", "args": {"query": "hello"}, "type": "tool_call"}],
        additional_kwargs={},
        response_metadata={"model_provider": "openai_with_reasoning"},
    )
    blocks = _translate_openai_with_reasoning(msg)
    tool_blocks = [b for b in blocks if b.get("type") == "tool_call"]
    assert len(tool_blocks) == 1
    assert tool_blocks[0] == {"type": "tool_call", "id": "tc-abc", "name": "search", "args": {"query": "hello"}}


def test_translate_no_tool_calls_unchanged():
    """tool_calls がない場合に既存動作が変わらないこと."""
    msg = _make_message(
        content="Hello",
        tool_calls=[],
        additional_kwargs={"reasoning": "thinking"},
        response_metadata={"model_provider": "openai_with_reasoning"},
    )
    blocks = _translate_openai_with_reasoning(msg)
    types = [b.get("type") for b in blocks]
    assert "tool_call" not in types
    assert "reasoning" in types
    assert "text" in types


def test_translate_reasoning_before_tool_call():
    """ブロック順序: reasoning → text → tool_call であること."""
    msg = _make_message(
        content="some text",
        tool_calls=[{"id": "c1", "name": "tool", "args": {}, "type": "tool_call"}],
        additional_kwargs={"reasoning": "thinking..."},
        response_metadata={"model_provider": "openai_with_reasoning"},
    )
    blocks = _translate_openai_with_reasoning(msg)
    types = [b.get("type") for b in blocks]
    assert types.index("reasoning") < types.index("text")
    assert types.index("text") < types.index("tool_call")


def test_translate_tool_calls_only_no_reasoning():
    """reasoning なし・tool_calls ありのケースで tool_call ブロックが生成されること."""
    msg = _make_message(
        content="",
        tool_calls=[{"id": "c2", "name": "calc", "args": {"x": 1}, "type": "tool_call"}],
        additional_kwargs={},
        response_metadata={"model_provider": "openai_with_reasoning"},
    )
    blocks = _translate_openai_with_reasoning(msg)
    assert len(blocks) == 1
    assert blocks[0] == {"type": "tool_call", "id": "c2", "name": "calc", "args": {"x": 1}}


def test_translate_chunk_tool_call_partial_args_safe():
    """AIMessageChunk + 部分的な tool_call_chunks でも安全に処理されること."""
    chunk = AIMessageChunk(
        content="",
        tool_call_chunks=[{"id": "c3", "name": "fetch", "args": '{"url":', "index": 0, "type": "tool_call_chunk"}],
        additional_kwargs={"reasoning": "partial"},
        response_metadata={"model_provider": "openai_with_reasoning"},
    )
    # content_blocks アクセス時にエラーにならないこと
    blocks = chunk.content_blocks
    tool_blocks = [b for b in blocks if b.get("type") == "tool_call"]
    # 部分的な args は {} にパースされるが例外は発生しない
    assert len(tool_blocks) == 1
    assert tool_blocks[0].get("name") == "fetch"
