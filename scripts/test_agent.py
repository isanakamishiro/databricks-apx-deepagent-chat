"""
エージェント統合テストスクリプト

使用方法:
    # 実LLMで実行
    uv run python scripts/test_agent.py

    # FakeModel（コストゼロ・高速）で実行
    USE_FAKE_MODEL=true uv run python scripts/test_agent.py

環境変数:
    USE_FAKE_MODEL    - "true" の場合 FakeListChatModel を使用
    TEST_VOLUME_PATH  - テスト用 UC Volume パス (例: /Volumes/catalog/schema/volume)
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from pydantic import SecretStr

from apx_deepagent_chat.backend.agent import init_agent, init_model
from apx_deepagent_chat.backend.agent.clients import get_user_workspace_client
from apx_deepagent_chat.backend.agent.core import _load_preset_files
from apx_deepagent_chat.backend.agent.model_loader import load_models_config
from apx_deepagent_chat.backend.agent.reasoning_model import ChatOpenAIWithReasoning
from apx_deepagent_chat.backend.agent.stream import process_agent_astream_events

# プロジェクトの src ディレクトリを Python パスに追加
# sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
load_dotenv(Path(__file__).parent.parent / ".env")

# opentelemetry.attributes の警告（WARNING）を抑制
# logging.getLogger("opentelemetry.attributes").setLevel(logging.ERROR)
logging.getLogger("mlflow.utils.autologging_utils").setLevel(logging.ERROR)
# logging.getLogger("mlflow.tracing.export.async_export_queue").setLevel(logging.ERROR)

# --- 設定 ---

USE_FAKE_MODEL = os.getenv("USE_FAKE_MODEL", "false").lower() == "true"
VOLUME_PATH = os.getenv("TEST_VOLUME_PATH", "")

TEST_CASES = [
    {
        "name": "Skill実行",
        "message": "Databricksについて調査して",
        "thread_id": "test-000",
    },
    # {
    #     "name": "基本的な質問",
    #     "message": "今日の日付を必ずサブエージェントを使って確認してください",
    #     "thread_id": "test-001",
    # },
    # {
    #     "name": "ツールを使うタスク",
    #     "message": "現在の東京の時刻を教えてください",
    #     "thread_id": "test-002",
    # },
    # {
]


async def run_test_chatmodel():

    from langchain.agents import create_agent

    model_name = os.environ.get("REASONING_MODEL", "ext-endpoint-middle")
    api_base = os.environ.get("OPENAI_API_BASE", "")
    api_key = os.environ.get("OPENAI_API_KEY", "")

    if not api_base or not api_key:
        print("環境変数 OPENAI_API_BASE / OPENAI_API_KEY を設定してください")
        sys.exit(1)

    model = ChatOpenAIWithReasoning(
        model=model_name,  # type: ignore[unknown-argument]
        base_url=api_base,  # type: ignore[unknown-argument]
        api_key=SecretStr(api_key),  # type: ignore[unknown-argument]
        streaming=True,
        max_tokens=2048,
        temperature=1.0,
        top_p=0.9,
    )

    agent = create_agent(
        model=model,
        tools=[],
    )

    resp = agent.invoke(
        {"messages": [HumanMessage(content="9.11 or 9.8、どちらが大きい?")]},
    )

    from pprint import pprint

    messages = resp.get("messages", [])
    for msg in messages:
        pprint(msg.content_blocks)


def _make_fake_model():
    """FakeListChatModel を構築して返す.

    bind_tools() をオーバーライドして self を返すことで、
    エージェントフレームワークのツールバインド要求に対応する。
    """
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    responses = [
        "今日は2026年3月6日です。",
        "現在の東京の時刻は取得できませんでしたが、テストレスポンスです。",
        "テストレスポンス3",
        "テストレスポンス4",
        "テストレスポンス5",
    ]

    class ToolCapableFakeModel(FakeListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    return ToolCapableFakeModel(responses=responses)


async def run_test_case(
    name: str,
    message: str,
    volume_path: str,
    thread_id: str,
    override_model=None,
    case_index: int = 0,
    total: int = 0,
) -> None:
    """単一テストケースを実行して結果を表示する."""
    print(f"\n{'=' * 50}")
    print(f"=== [{case_index}/{total}] {name} ===")
    print(f"メッセージ: {message}")
    print("-" * 50)

    user_workspace_client = get_user_workspace_client()
    default_model = next(k for k, v in load_models_config().items() if v.get("default"))
    # default_model = "databricks-qwen3-next-80b-a3b-instruct"
    model = init_model(default_model, user_workspace_client)
    if override_model:
        print(
            f"*** モデルを {override_model.__class__.__name__} にオーバーライドして実行 ***"
        )
        model = override_model

    agent = await init_agent(
        model=model,
        workspace_client=user_workspace_client,
        checkpointer=None,
        volume_path=volume_path,
        override_subagent_model=override_model,
    )

    messages = {
        "messages": [HumanMessage(content=message)],
        "files": _load_preset_files(),
    }
    config = {"configurable": {"thread_id": thread_id}}

    usage_accumulator: dict[str, int] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }

    text_parts: list[str] = []
    tool_calls: list[str] = []

    async for event in process_agent_astream_events(
        agent.astream(
            input=messages,
            config=config,
            stream_mode=["updates", "messages"],
            # stream_mode=["updates"],
            subgraphs=True,
            version="v2",
        ),
        usage_accumulator=usage_accumulator,
    ):
        etype = event.type
        # print(f"[イベント] {etype}")
        # print(f"イベント内容: {event}")

        # テキストデルタを収集
        if etype == "response.output_text.delta":
            delta = getattr(event, "delta", "")
            if delta:
                text_parts.append(delta)

        # ツール呼び出しを収集
        elif etype == "response.output_item.done":
            item = getattr(event, "item", None)
            if item and isinstance(item, dict) and item.get("type") == "function_call":
                name_tc = item.get("name", "?")
                args = item.get("arguments", "")
                tool_calls.append(f"- {name_tc}({args})")

        # usage を取得
        elif etype == "response.completed":
            response = getattr(event, "response", None)
            if response and isinstance(response, dict):
                u = response.get("usage", {})
                if u:
                    usage_accumulator["input_tokens"] = u.get("input_tokens", 0)
                    usage_accumulator["output_tokens"] = u.get("output_tokens", 0)
                    usage_accumulator["total_tokens"] = u.get("total_tokens", 0)

    # 結果表示
    full_text = "".join(text_parts)
    print("[応答]")
    print(full_text if full_text else "(テキスト応答なし)")

    if tool_calls:
        print("\n[ツール呼び出し]")
        for tc in tool_calls:
            print(tc)

    inp = usage_accumulator.get("input_tokens", 0)
    out = usage_accumulator.get("output_tokens", 0)
    total_tokens = usage_accumulator.get("total_tokens", 0)
    if total_tokens > 0:
        print("\n[使用トークン]")
        print(f"input: {inp} / output: {out} / total: {total_tokens}")

    print("=" * 50)


async def main() -> None:

    # await run_test_chatmodel()
    # return

    if not VOLUME_PATH:
        print("エラー: TEST_VOLUME_PATH 環境変数が設定されていません。")
        print(
            "例: TEST_VOLUME_PATH=/Volumes/catalog/schema/volume uv run python scripts/test_agent.py"
        )
        sys.exit(1)

    override_model = _make_fake_model() if USE_FAKE_MODEL else None

    if USE_FAKE_MODEL:
        print("*** FakeModel モードで実行中（コストゼロ・高速）***")
    else:
        print("*** 実LLM モードで実行中 ***")

    print(f"Volume Path: {VOLUME_PATH}")
    print(f"テストケース数: {len(TEST_CASES)}")

    for i, tc in enumerate(TEST_CASES, start=1):
        await run_test_case(
            name=tc["name"],
            message=tc["message"],
            volume_path=VOLUME_PATH,
            thread_id=tc.get("thread_id", f"test-{i:03d}"),
            override_model=override_model,
            case_index=i,
            total=len(TEST_CASES),
        )

    print("\n全テストケース完了。")


if __name__ == "__main__":
    # asyncio.run(main())
    asyncio.run(run_test_chatmodel())
