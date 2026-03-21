from typing import Any, cast

from langchain_core.messages.block_translators import register_translator
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_openai.chat_models.base import BaseChatOpenAI


def _strip_index(block: dict) -> dict:
    """merge_lists() 用の内部フィールド "index" を除去する."""
    return {k: v for k, v in block.items() if k != "index"}


def _translate_openai_with_reasoning(message) -> list:
    """additional_kwargs["reasoning"] を content_blocks に含めるトランスレータ.

    ストリーミング中は reasoning が additional_kwargs["reasoning"]（文字列）に
    蓄積されるため、content_blocks プロパティアクセス時にここで変換する。
    """
    blocks: list = []
    # reasoning ブロックを先頭に
    reasoning = message.additional_kwargs.get("reasoning", "")
    if reasoning:
        blocks.append({"type": "reasoning", "reasoning": reasoning})
    # content (str or list) を変換
    content = message.content
    if isinstance(content, str):
        if content:
            blocks.append({"type": "text", "text": content})
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                blocks.append(_strip_index(block))
    return blocks


register_translator(
    "openai_with_reasoning",
    _translate_openai_with_reasoning,
    _translate_openai_with_reasoning,
)


class ChatOpenAIWithReasoning(BaseChatOpenAI):
    """reasoning/reasoning_content をコンテンツブロックとして注入する BaseChatOpenAI サブクラス.

    Note on private method overrides:
    This class overrides several private methods that are the ONLY extension points
    where raw API response data (including non-standard `reasoning` fields) is
    still accessible before LangChain discards it.

    - `_convert_chunk_to_generation_chunk`: receives the raw SSE chunk dict.
      `_convert_delta_to_message_chunk()` called internally discards `reasoning`.
      Stable override as of langchain-openai==0.3.x — review on major version bumps.
    - `_create_chat_result`: receives the raw OpenAI response object.
      `_convert_dict_to_message()` called internally discards `reasoning`.
      Stable override as of langchain-openai==0.3.x — review on major version bumps.
    - `_generate_with_cache` / `_agenerate_with_cache`: called for both streaming and
      non-streaming paths. Normalises content blocks after accumulation.
      Stable override as of langchain-openai==0.3.x — review on major version bumps.
    - `_get_request_payload`: normalises content list before sending.
      AzureChatOpenAI uses the same pattern — effectively an official override point.
      Stable override as of langchain-openai==0.3.x — review on major version bumps.
    """

    @staticmethod
    def _extract_reasoning_text(delta_or_message: dict) -> str | None:
        """delta/message dictからreasoningテキストを抽出. reasoning → reasoning_content の優先順."""
        for key in ("reasoning", "reasoning_content"):
            val = delta_or_message.get(key)
            if val:
                return val
        return None

    @staticmethod
    def _build_content_blocks(reasoning_text: str, existing: str | list) -> list:
        """reasoning ブロックを先頭にしてコンテンツブロックリストを構築する（immutable）."""
        blocks: list = [{"type": "reasoning", "reasoning": reasoning_text}]
        if isinstance(existing, str) and existing:
            blocks.append({"type": "text", "text": existing})
        elif isinstance(existing, list):
            blocks.extend(existing)
        return blocks

    @staticmethod
    def _normalize_content(content: str | list) -> list:
        """コンテンツリストを正規化する.

        - 素の文字列 → {"type": "text", "text": "..."} ブロックに変換
        - 空文字列を除去
        - 連続する同一 type ブロック（reasoning / text）を統合
        """
        if isinstance(content, str):
            return [{"type": "text", "text": content}] if content else []

        normalized: list = []
        for block in content:
            if isinstance(block, str):
                if block:
                    block = {"type": "text", "text": block}
                else:
                    continue
            if isinstance(block, dict):
                # "index" フィールドを除去（merge_lists() 用の内部フィールド）
                block = _strip_index(block)
                block_type = block.get("type")
                key = (
                    "reasoning"
                    if block_type == "reasoning"
                    else "text"
                    if block_type == "text"
                    else None
                )
                if (
                    key
                    and normalized
                    and normalized[-1].get("type") == block_type
                    and key in normalized[-1]
                    and key in block
                ):
                    # 連続する同一 type ブロックを統合
                    normalized[-1] = {
                        **normalized[-1],
                        key: normalized[-1][key] + block[key],
                    }
                else:
                    normalized.append(block)
        return normalized

    def _normalize_result(self, result: ChatResult) -> ChatResult:
        """ChatResult の全 generation の content を正規化する.

        reasoning の content_blocks への変換はトランスレータが担当するため、
        ここでは content の正規化のみ行う。
        """
        new_generations = []
        for gen in result.generations:
            new_msg = gen.message.model_copy(
                update={"content": self._normalize_content(gen.message.content)}
            )
            new_generations.append(
                ChatGeneration(message=new_msg, generation_info=gen.generation_info)
            )
        result.generations = new_generations
        return result

    # Overrides _generate_with_cache() / _agenerate_with_cache() to normalize content blocks
    # after accumulation. These methods cover BOTH streaming and non-streaming paths:
    # - Non-streaming: _generate() → _create_chat_result() → _generate_with_cache()
    # - Streaming: generate_from_stream() → _generate_with_cache()
    # Previous _generate() / _agenerate() overrides were bypassed during streaming.
    def _generate_with_cache(self, messages, stop=None, run_manager=None, **kwargs):
        result = super()._generate_with_cache(
            messages, stop=stop, run_manager=run_manager, **kwargs
        )
        return self._normalize_result(result)

    async def _agenerate_with_cache(
        self, messages, stop=None, run_manager=None, **kwargs
    ):
        result = await super()._agenerate_with_cache(
            messages, stop=stop, run_manager=run_manager, **kwargs
        )
        return self._normalize_result(result)

    # Stable override as of langchain-openai==0.3.x — review on major version bumps.
    # NOTE: This is the only extension point with access to the raw SSE chunk dict.
    # `_convert_delta_to_message_chunk()` (called by super) discards `reasoning` fields,
    # so we cannot inject reasoning at the higher `_stream()` / `_astream()` level.
    #
    # Reasoning text is stored in additional_kwargs["reasoning"] (string) during streaming
    # rather than as a list in content, because LangChain passes content directly to
    # on_llm_new_token as the `token` arg. MLflow records it as an OTel span event attribute
    # named "token"; OTel rejects sequences containing dicts with a WARNING.
    # Using additional_kwargs (merged via merge_dicts string concatenation) avoids this.
    def _convert_chunk_to_generation_chunk(
        self, chunk, default_chunk_class, base_generation_info
    ):
        """ストリーミング: reasoningテキストをadditional_kwargs["reasoning"]に格納."""
        gen_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if gen_chunk is None:
            return gen_chunk

        choices = chunk.get("choices") or []
        if not choices:
            return gen_chunk

        delta = choices[0].get("delta") or {}
        reasoning_text = self._extract_reasoning_text(delta)

        # reasoning が無ければ変換不要（content は str のまま）
        if not reasoning_text:
            return gen_chunk

        # reasoning を additional_kwargs に蓄積（merge_dicts が文字列結合する）
        new_additional_kwargs = {
            **gen_chunk.message.additional_kwargs,
            "reasoning": reasoning_text,
        }
        new_msg = gen_chunk.message.model_copy(
            update={
                "additional_kwargs": new_additional_kwargs,
                "response_metadata": {
                    **gen_chunk.message.response_metadata,
                    "model_provider": "openai_with_reasoning",
                },
            }
        )
        return ChatGenerationChunk(
            message=new_msg,
            generation_info=gen_chunk.generation_info,
        )

    # Stable override as of langchain-openai==0.3.x — review on major version bumps.
    # NOTE: This is the only extension point with access to the raw API response object.
    # `_convert_dict_to_message()` (called by super) discards `reasoning` fields,
    # so we cannot inject reasoning at the higher `_generate()` level.
    def _create_chat_result(self, response, generation_info=None) -> ChatResult:
        """非ストリーミング: reasoningブロックをコンテンツリストに注入."""
        result = super()._create_chat_result(response, generation_info)

        # response を dict 化（OpenAI Pydantic モデルの場合 model_dump を使用）
        resp: Any = response
        if hasattr(resp, "model_dump"):
            response_dict: dict[str, Any] = resp.model_dump(
                exclude={"choices": {"__all__": {"message": {"parsed"}}}}
            )
        else:
            response_dict = cast(dict[str, Any], resp)

        choices = response_dict.get("choices") or []
        new_generations = []
        for i, gen in enumerate(result.generations):
            if i >= len(choices):
                new_generations.append(gen)
                continue

            message_dict = choices[i].get("message") or {}
            reasoning_text = self._extract_reasoning_text(message_dict)
            if not reasoning_text:
                new_generations.append(gen)
                continue

            blocks = self._build_content_blocks(reasoning_text, gen.message.content)
            blocks = self._normalize_content(blocks)
            new_msg = gen.message.model_copy(update={"content": blocks})
            new_generations.append(
                ChatGeneration(message=new_msg, generation_info=gen.generation_info)
            )

        result.generations = new_generations
        return result

    # Stable override as of langchain-openai==0.3.x — review on major version bumps.
    # AzureChatOpenAI uses the same pattern — effectively an official override point.
    def _get_request_payload(
        self, input_: Any, *, stop: list[str] | None = None, **kwargs: Any
    ) -> dict:
        """リクエスト送信前に、コンテンツリスト内の文字列項目と "index" フィールドを正規化する。

        ストリーミング時に reasoning ブロック（list）とテキストチャンク（str）が混在し、
        AIMessageChunk 蓄積後に content が混在リストになる問題を修正する。
        - 非空の文字列項目 → {"type": "text", "text": "..."} ブロックに変換
        - 空文字列項目 → 除去
        - "index" フィールド → 除去（merge_lists() 用の内部フィールドのため送信不要）
        """
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)

        normalized_messages = []
        for msg in payload.get("messages", []):
            content = msg.get("content")
            if isinstance(content, list):
                clean_blocks = []
                for block in content:
                    if isinstance(block, str):
                        if block:  # 非空文字列 → text ブロックに変換
                            clean_blocks.append({"type": "text", "text": block})
                        # 空文字列 → 除去
                    elif isinstance(block, dict):
                        # "index" フィールドを除去してから送信
                        clean_block = _strip_index(block)
                        if clean_block:
                            clean_blocks.append(clean_block)
                msg = {**msg, "content": clean_blocks if clean_blocks else ""}
            normalized_messages.append(msg)

        payload["messages"] = normalized_messages
        return payload
