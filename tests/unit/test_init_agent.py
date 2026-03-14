"""agent/core.py の init_agent ユニットテスト."""
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apx_deepagent_chat.backend.agent.core import init_agent
from apx_deepagent_chat.backend.agent.lc_tools import (
    get_current_time,
    web_fetch,
    web_search,
)

MODULE = "apx_deepagent_chat.backend.agent.core"


@pytest.fixture()
def mock_model():
    return MagicMock()


@pytest.fixture()
def mock_ws():
    return MagicMock()


@pytest.fixture()
def mock_mcp_tools():
    return [MagicMock(name="mcp_tool_1"), MagicMock(name="mcp_tool_2")]


@pytest.fixture()
def mock_agent():
    return MagicMock()


@pytest.fixture()
def patches(mock_ws, mock_mcp_tools, mock_agent):
    """全テスト共通の外部依存モック。個々のテストで上書き可能。"""
    with ExitStack() as stack:
        mocks = {
            "get_sp_ws": stack.enter_context(
                patch(f"{MODULE}.get_sp_workspace_client", return_value=mock_ws)
            ),
            "get_mcp": stack.enter_context(
                patch(f"{MODULE}.get_mcp_tools", new=AsyncMock(return_value=mock_mcp_tools))
            ),
            "build_subagents": stack.enter_context(
                patch(f"{MODULE}._build_subagents", return_value=[MagicMock()])
            ),
            "load_system_prompt": stack.enter_context(
                patch(f"{MODULE}._load_system_prompt", return_value="system_prompt_text")
            ),
            "summarization_mw": stack.enter_context(
                patch(f"{MODULE}.create_summarization_tool_middleware", return_value=MagicMock())
            ),
            "create_deep_agent": stack.enter_context(
                patch(f"{MODULE}.create_deep_agent", return_value=mock_agent)
            ),
            "CompositeBackend": stack.enter_context(
                patch(f"{MODULE}.CompositeBackend", return_value=MagicMock())
            ),
            "UCVolumesBackend": stack.enter_context(
                patch(f"{MODULE}.UCVolumesBackend", return_value=MagicMock())
            ),
            "StateBackend": stack.enter_context(
                patch(f"{MODULE}.StateBackend", return_value=MagicMock())
            ),
        }
        yield mocks


# ─── volume_path バリデーション ───────────────────────────────────────────────


async def test_init_agent_raises_when_volume_path_is_none(mock_model, patches):
    """volume_path=None は ValueError を上げる."""
    with pytest.raises(ValueError, match="volume_path"):
        await init_agent(model=mock_model, volume_path=None)


async def test_init_agent_raises_when_volume_path_is_empty(mock_model, patches):
    """volume_path="" は ValueError を上げる（空文字も falsy）."""
    with pytest.raises(ValueError, match="volume_path"):
        await init_agent(model=mock_model, volume_path="")


# ─── workspace_client フォールバック ──────────────────────────────────────────


async def test_init_agent_uses_sp_client_when_workspace_client_is_none(
    mock_model, patches
):
    """workspace_client=None のとき get_sp_workspace_client() にフォールバックする."""
    await init_agent(model=mock_model, volume_path="/Volumes/a/b/c")

    patches["get_sp_ws"].assert_called_once()


async def test_init_agent_uses_provided_workspace_client(mock_model, patches):
    """workspace_client が指定されたとき get_sp_workspace_client() は呼ばれない."""
    custom_ws = MagicMock()
    await init_agent(model=mock_model, workspace_client=custom_ws, volume_path="/Volumes/a/b/c")

    patches["get_sp_ws"].assert_not_called()


async def test_init_agent_passes_correct_ws_to_get_mcp_tools(mock_model, patches):
    """get_mcp_tools に使われる ws_client は workspace_client 引数から来る."""
    custom_ws = MagicMock()
    await init_agent(model=mock_model, workspace_client=custom_ws, volume_path="/Volumes/a/b/c")

    patches["get_mcp"].assert_awaited_once_with(custom_ws)


# ─── create_deep_agent への引数 ───────────────────────────────────────────────


async def test_init_agent_includes_mcp_tools_in_tools(
    mock_model, mock_mcp_tools, patches
):
    """create_deep_agent の tools に mcp_tools が含まれる."""
    await init_agent(model=mock_model, volume_path="/Volumes/a/b/c")

    call_kwargs = patches["create_deep_agent"].call_args.kwargs
    for mcp_tool in mock_mcp_tools:
        assert mcp_tool in call_kwargs["tools"]


async def test_init_agent_includes_lc_tools_in_tools(mock_model, patches):
    """create_deep_agent の tools に web_search / web_fetch / get_current_time が含まれる."""
    await init_agent(model=mock_model, volume_path="/Volumes/a/b/c")

    call_kwargs = patches["create_deep_agent"].call_args.kwargs
    tools = call_kwargs["tools"]
    assert web_search in tools
    assert web_fetch in tools
    assert get_current_time in tools


async def test_init_agent_passes_model_to_create_deep_agent(mock_model, patches):
    """create_deep_agent に model が渡される."""
    await init_agent(model=mock_model, volume_path="/Volumes/a/b/c")

    call_kwargs = patches["create_deep_agent"].call_args.kwargs
    assert call_kwargs["model"] is mock_model


async def test_init_agent_passes_system_prompt_to_create_deep_agent(mock_model, patches):
    """create_deep_agent に _load_system_prompt の戻り値が渡される."""
    await init_agent(model=mock_model, volume_path="/Volumes/a/b/c")

    call_kwargs = patches["create_deep_agent"].call_args.kwargs
    assert call_kwargs["system_prompt"] == "system_prompt_text"


async def test_init_agent_passes_checkpointer_to_create_deep_agent(mock_model, patches):
    """create_deep_agent に checkpointer が渡される."""
    mock_checkpointer = MagicMock()
    await init_agent(
        model=mock_model,
        volume_path="/Volumes/a/b/c",
        checkpointer=mock_checkpointer,
    )

    call_kwargs = patches["create_deep_agent"].call_args.kwargs
    assert call_kwargs["checkpointer"] is mock_checkpointer


async def test_init_agent_passes_none_checkpointer_by_default(mock_model, patches):
    """checkpointer 未指定のとき None が渡される."""
    await init_agent(model=mock_model, volume_path="/Volumes/a/b/c")

    call_kwargs = patches["create_deep_agent"].call_args.kwargs
    assert call_kwargs["checkpointer"] is None


async def test_init_agent_returns_create_deep_agent_result(mock_model, patches):
    """init_agent は create_deep_agent の戻り値をそのまま返す."""
    result = await init_agent(model=mock_model, volume_path="/Volumes/a/b/c")

    assert result is patches["create_deep_agent"].return_value


# ─── _build_subagents への引数 ───────────────────────────────────────────────


async def test_init_agent_passes_mcp_tools_to_build_subagents(
    mock_model, mock_mcp_tools, patches
):
    """_build_subagents に mcp_tools が渡される."""
    await init_agent(model=mock_model, volume_path="/Volumes/a/b/c")

    patches["build_subagents"].assert_called_once()
    call_kwargs = patches["build_subagents"].call_args.kwargs
    assert call_kwargs["mcp_tools"] == mock_mcp_tools


async def test_init_agent_passes_override_subagent_model_to_build_subagents(
    mock_model, patches
):
    """override_subagent_model が _build_subagents の override_model に渡される."""
    override_model = MagicMock()
    await init_agent(
        model=mock_model,
        volume_path="/Volumes/a/b/c",
        override_subagent_model=override_model,
    )

    call_kwargs = patches["build_subagents"].call_args.kwargs
    assert call_kwargs["override_model"] is override_model


async def test_init_agent_passes_subagents_to_create_deep_agent(mock_model, patches):
    """_build_subagents の結果が create_deep_agent の subagents に渡される."""
    fake_subagents = [MagicMock(), MagicMock()]
    patches["build_subagents"].return_value = fake_subagents

    await init_agent(model=mock_model, volume_path="/Volumes/a/b/c")

    call_kwargs = patches["create_deep_agent"].call_args.kwargs
    assert call_kwargs["subagents"] == fake_subagents
