import asyncio

from langchain.agents.middleware import wrap_model_call, wrap_tool_call
from langchain_core.messages import SystemMessage, ToolMessage

_tool_call_semaphore = asyncio.Semaphore(4)


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
