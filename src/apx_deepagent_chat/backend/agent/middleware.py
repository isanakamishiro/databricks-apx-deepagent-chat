import asyncio
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import (
    AgentMiddleware,
    Runtime,
    wrap_model_call,
    wrap_tool_call,
)
from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.types import interrupt as langgraph_interrupt

if TYPE_CHECKING:
    from .job_store import JobStore

_tool_call_semaphore = asyncio.Semaphore(4)


class InterruptMiddleware(AgentMiddleware):
    """モデル呼び出し前に割り込みフラグをチェックし、セットされていれば LangGraph を正常停止させる.

    check_subagent=False (デフォルト): メインエージェント用。interrupt_requested フラグを参照。
    check_subagent=True: サブエージェント用。subagent_interrupt_requested フラグを参照。

    非同期対応: abefore_model/aafter_model で job_store を非同期チェックし、
    結果を _cached_interrupt にキャッシュする。同期の before_model/after_model は
    キャッシュ値のみを参照する。
    """

    def __init__(
        self, job_id: str, job_store: "JobStore", check_subagent: bool = False
    ) -> None:
        self.job_id = job_id
        self.job_store = job_store
        self.check_subagent = check_subagent
        self._cached_interrupt: bool = False

    async def _check_interrupt(self) -> bool:
        """job_store から割り込みフラグを非同期で取得する."""
        if self.check_subagent:
            result = self.job_store.is_subagent_interrupt_requested(self.job_id)
        else:
            result = self.job_store.is_interrupt_requested(self.job_id)
        # is_interrupt_requested は InMemoryJobStore では同期、SQLiteJobStore では
        # コルーチンを返す可能性があるため、コルーチンの場合は await する
        if asyncio.iscoroutine(result):
            return await result  # type: ignore[misc]
        return bool(result)

    def before_model(self, state: Any, runtime: Runtime) -> None:
        # 同期コンテキスト: キャッシュ値のみ参照
        if self._cached_interrupt:
            langgraph_interrupt({"reason": "user_interrupt"})
        return None

    def after_model(self, state: Any, runtime: Runtime) -> None:
        return self.before_model(state, runtime)

    async def abefore_model(self, state: Any, runtime: Runtime) -> None:
        # 非同期: job_store をチェックしてキャッシュを更新
        self._cached_interrupt = await self._check_interrupt()
        if self._cached_interrupt:
            langgraph_interrupt({"reason": "user_interrupt"})
        return None

    async def aafter_model(self, state: Any, runtime: Runtime) -> None:
        await self.abefore_model(state, runtime)


@wrap_tool_call  # type: ignore[arg-type]
async def strip_content_block_ids(request, handler):
    """MCP ツール結果の content block から id/index フィールドを除去し、同時実行数を制限する.

    langchain_core の create_text_block() が自動付与する id フィールドが
    Databricks Model Serving 経由の Anthropic API でバリデーションエラーを
    引き起こすため、ツール実行後に除去する。
    また、MCP ツールの同時実行数をセマフォで制限し TaskGroup エラーを防ぐ。
    """
    async with _tool_call_semaphore:
        result = await handler(request)
    if isinstance(result, ToolMessage) and isinstance(result.content, list):
        result.content = [
            (
                {k: v for k, v in block.items() if k not in ("id", "index")}
                if isinstance(block, dict)
                else block
            )
            for block in result.content
        ]
    return result


@wrap_model_call  # type: ignore[arg-type]
async def flatten_system_message(request, handler):
    """SystemMessage の content block リストをプレーン文字列に正規化する.

    deepagents の append_to_system_message が生成する
    [{"type": "text", "text": "..."}] 形式を、Gemini API が受け付ける
    単純な文字列に変換する。
    """
    if request.system_message and isinstance(request.system_message.content, list):
        parts = []
        for block in request.system_message.content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        request.system_message = SystemMessage(content="\n\n".join(parts))
    return await handler(request)
