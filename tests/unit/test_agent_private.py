"""agent.py private関数のユニットテスト.

対象:
  - _get_model_name
  - _get_volume_path
  - _get_or_create_thread_id
"""
import pytest
from unittest.mock import MagicMock

from apx_deepagent_chat.backend.agent import (
    _get_model_name,
    _get_volume_path,
    _get_or_create_thread_id,
)


def _make_request(custom_inputs=None, context=None):
    """テスト用リクエストオブジェクト（MagicMock）."""
    req = MagicMock()
    req.custom_inputs = custom_inputs
    req.context = context
    return req


# ─── _get_model_name ─────────────────────────────────────────────────────────


def test_get_model_name_from_custom_inputs():
    """custom_inputs["llm_model"] が指定された場合はそれを返す（load_models_config を呼ばない）."""
    req = _make_request(custom_inputs={"llm_model": "claude-3"})
    result = _get_model_name(req)
    assert result == "claude-3"


def test_get_model_name_falls_back_to_default(mocker):
    """custom_inputs が空の場合は default=True のモデルを返す."""
    mocker.patch(
        "apx_deepagent_chat.backend.agent.load_models_config",
        return_value={"model-a": {}, "model-b": {"default": True}},
    )
    req = _make_request(custom_inputs={})
    result = _get_model_name(req)
    assert result == "model-b"


def test_get_model_name_empty_llm_model_falls_back(mocker):
    """custom_inputs["llm_model"] が空文字（falsy）の場合はデフォルトモデルにフォールバックする."""
    mocker.patch(
        "apx_deepagent_chat.backend.agent.load_models_config",
        return_value={"model-x": {"default": True}},
    )
    req = _make_request(custom_inputs={"llm_model": ""})
    result = _get_model_name(req)
    assert result == "model-x"


def test_get_model_name_none_custom_inputs(mocker):
    """custom_inputs が None の場合はデフォルトモデルにフォールバックする."""
    mocker.patch(
        "apx_deepagent_chat.backend.agent.load_models_config",
        return_value={"default-model": {"default": True}},
    )
    req = _make_request(custom_inputs=None)
    result = _get_model_name(req)
    assert result == "default-model"


# ─── _get_volume_path ─────────────────────────────────────────────────────────


def test_get_volume_path_returns_value():
    """custom_inputs["volume_path"] が設定されている場合はその値を返す."""
    req = _make_request(custom_inputs={"volume_path": "/Volumes/cat/schema/vol"})
    result = _get_volume_path(req)
    assert result == "/Volumes/cat/schema/vol"


def test_get_volume_path_missing_raises():
    """custom_inputs に volume_path が存在しない場合は ValueError を送出する."""
    req = _make_request(custom_inputs={})
    with pytest.raises(ValueError):
        _get_volume_path(req)


def test_get_volume_path_empty_string_raises():
    """volume_path が空文字の場合は ValueError を送出する."""
    req = _make_request(custom_inputs={"volume_path": ""})
    with pytest.raises(ValueError):
        _get_volume_path(req)


def test_get_volume_path_none_custom_inputs_raises():
    """custom_inputs が None の場合は ValueError を送出する."""
    req = _make_request(custom_inputs=None)
    with pytest.raises(ValueError):
        _get_volume_path(req)


# ─── _get_or_create_thread_id ─────────────────────────────────────────────────


def test_get_or_create_thread_id_from_custom_inputs():
    """custom_inputs["thread_id"] が最優先で使われる."""
    req = _make_request(custom_inputs={"thread_id": "my-thread"})
    result = _get_or_create_thread_id(req)
    assert result == "my-thread"


def test_get_or_create_thread_id_from_context():
    """custom_inputs に thread_id がない場合は context.conversation_id を使う."""
    context = MagicMock()
    context.conversation_id = "conv-abc"
    req = _make_request(custom_inputs={}, context=context)
    result = _get_or_create_thread_id(req)
    assert result == "conv-abc"


def test_get_or_create_thread_id_auto_generates():
    """custom_inputs も context もない場合は UUID 形式の文字列を自動生成する."""
    req = _make_request(custom_inputs=None, context=None)
    result = _get_or_create_thread_id(req)
    assert isinstance(result, str)
    assert len(result) > 0


def test_get_or_create_thread_id_custom_inputs_over_context():
    """custom_inputs["thread_id"] が context.conversation_id より優先される."""
    context = MagicMock()
    context.conversation_id = "ctx"
    req = _make_request(custom_inputs={"thread_id": "ci"}, context=context)
    result = _get_or_create_thread_id(req)
    assert result == "ci"
