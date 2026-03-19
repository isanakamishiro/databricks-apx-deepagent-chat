import functools
import os
from pathlib import Path
from typing import Any, Optional, Union

import yaml
from databricks.sdk import WorkspaceClient
from databricks_langchain import ChatDatabricks
from langchain_core.language_models.model_profile import ModelProfile

from .clients import get_sp_workspace_client

ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"

USE_FAKE_MODEL = os.getenv("USE_FAKE_MODEL", "false").lower() == "true"
FAKE_MODEL_NAME = "_fake-model-for-testing"
DEFAULT_MODEL_PARAMS = {"temperature": 0}


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


def init_model(
    model_name: str, ws: Optional[WorkspaceClient] = None
) -> Union[ChatDatabricks, Any]:
    if model_name == FAKE_MODEL_NAME:
        return _make_fake_model()

    model_config = load_models_config().get(model_name, {})
    model_params = model_config.get("params", {})
    params = {**DEFAULT_MODEL_PARAMS, **model_params}

    ws_client = ws or get_sp_workspace_client()
    model = ChatDatabricks(
        model=model_name,
        workspace_client=ws_client,
        use_responses_api=False,
        **params,
    )
    if not model.profile:
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
        model.max_tokens = model.profile.get("max_output_tokens")
    return model
