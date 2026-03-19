import functools
import logging
import os
from pathlib import Path
from typing import Any, Optional

import yaml
from databricks.sdk import WorkspaceClient
from databricks_langchain.utils import get_async_openai_client, get_openai_client
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.model_profile import ModelProfile
from .clients import get_sp_workspace_client
from .reasoning_model import ChatOpenAIWithReasoning

ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"

USE_FAKE_MODEL = os.getenv("USE_FAKE_MODEL", "false").lower() == "true"
FAKE_MODEL_NAME = "_fake-model-for-testing"
DEFAULT_MODEL_PARAMS: dict[str, Any] = {"temperature": 0.0}
logger = logging.getLogger(__name__)


@functools.cache
def load_models_config() -> dict:
    config_path = ASSETS_DIR / "models.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)["models"]


@functools.cache
def _make_fake_model():
    """FakeListChatModel を構築して返す（開発モード用）."""
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    FAKE_RESPONSE = "こんにちは！私は元気です！"

    class ToolCapableFakeModel(FakeListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    return ToolCapableFakeModel(responses=[FAKE_RESPONSE] * 20)


def init_model(model_name: str, ws: Optional[WorkspaceClient] = None) -> BaseChatModel:
    if model_name == FAKE_MODEL_NAME:
        return _make_fake_model()

    model_config = load_models_config().get(model_name, {})
    model_params = model_config.get("params", {})
    params = {**DEFAULT_MODEL_PARAMS, **model_params}
    logger.info(f"Initializing model {model_name} with params: {params}")

    ws_client = ws or get_sp_workspace_client()
    sync_client = get_openai_client(workspace_client=ws_client)
    async_client = get_async_openai_client(workspace_client=ws_client)

    # root_client と client を両方渡すことで内部の client 再生成をスキップする
    model = ChatOpenAIWithReasoning(
        model=model_name,  # type: ignore[unknown-argument]
        root_client=sync_client,
        root_async_client=async_client,
        client=sync_client.chat.completions,
        async_client=async_client.chat.completions,
        **params,
    )
    if not getattr(model, "profile", None):
        model.profile = ModelProfile(
            **model_config.get(
                "profile",
                {
                    "max_input_tokens": 200000,
                    "max_output_tokens": 10000,
                    "text_inputs": True,
                    "tool_choice": True,
                    "tool_calling": True,
                    "structured_output": True,
                    "text_outputs": True,
                },
            )
        )
    if "max_tokens" not in model_params:
        profile = getattr(model, "profile", None)
        if profile is not None:
            model.max_tokens = profile.get("max_output_tokens")
    return model
