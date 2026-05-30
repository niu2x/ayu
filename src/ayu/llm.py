import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel

from ayu.config import LLMProviderConfig, load_config, load_state
from ayu.tools import ToolRegistry

logger = logging.getLogger("ayu.llm")

_runtime_config = None
_runtime_state = None
_runtime_client: AsyncOpenAI | None = None


class StreamEvent(BaseModel):
    type: Literal["reasoning", "content", "tool_call"]
    text: str


def _build_openai_client(provider_config: LLMProviderConfig) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=provider_config.api_key,
        base_url=provider_config.base_url or None,
    )


def initialize_runtime(force: bool = False) -> None:
    global _runtime_config, _runtime_state, _runtime_client

    if _runtime_config is not None and _runtime_state is not None and not force:
        return

    _runtime_config = load_config()
    _runtime_state = load_state()
    _runtime_client = None

    if _runtime_state.provider == "dummy":
        return

    provider_config = _runtime_config.llm.providers.get(_runtime_state.provider)
    if provider_config is None:
        return

    if provider_config.api_style == "openai":
        _runtime_client = _build_openai_client(provider_config)


def update_runtime_selection(provider: str, model: str) -> None:
    global _runtime_state, _runtime_client

    initialize_runtime()
    if _runtime_state is None:
        return

    _runtime_state.provider = provider
    _runtime_state.model = model
    _runtime_client = None

    if _runtime_config is None:
        return

    provider_config = _runtime_config.llm.providers.get(provider)
    if provider_config is None:
        return
    if provider_config.api_style == "openai":
        _runtime_client = _build_openai_client(provider_config)


async def chat(messages: list[dict], tool_registry: ToolRegistry | None = None) -> str:
    parts: list[str] = []
    async for event in chat_stream(messages, tool_registry=tool_registry):
        parts.append(event.text)
    return "".join(parts)


async def chat_stream(
    messages: list[dict],
    tool_registry: ToolRegistry | None = None,
) -> AsyncIterator[StreamEvent]:
    if _runtime_state is None:
        yield StreamEvent(type="content", text="运行态未初始化，请先调用 initialize_runtime()")
        return

    if _runtime_state.provider == "dummy":
        await asyncio.sleep(0.3)
        yield StreamEvent(type="content", text="OK")
        return

    if _runtime_config is None:
        yield StreamEvent(type="content", text="配置未初始化")
        return

    provider_config = _runtime_config.llm.providers.get(_runtime_state.provider)
    if provider_config is None:
        yield StreamEvent(
            type="content",
            text=(
                f"提供商 [bold]{_runtime_state.provider}[/] 未配置。"
                f"请先运行: ayu config set-provider {_runtime_state.provider}"
            ),
        )
        return

    logger.debug("API 风格: %s, 提供商: %s", provider_config.api_style, _runtime_state.provider)
    if provider_config.api_style == "openai":
        async for event in _chat_openai_stream(
            provider_config,
            _runtime_state.model,
            messages,
            tool_registry=tool_registry,
        ):
            yield event
        return

    yield StreamEvent(type="content", text=f"不支持的 API 风格: {provider_config.api_style}")


async def _chat_openai_stream(
    provider_config: LLMProviderConfig,
    model: str,
    messages: list[dict],
    tool_registry: ToolRegistry | None = None,
) -> AsyncIterator[StreamEvent]:
    logger.debug("开始流式请求: provider=%s, model=%s, messages=%d",
                 provider_config.api_style, model, len(messages))
    client = _runtime_client or _build_openai_client(provider_config)
    model_config = provider_config.models.get(model)
    while True:
        logger.debug("发送请求: model=%s, messages=%d", model, len(messages))
        request_options: dict[str, object] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_tokens": model_config.max_tokens if model_config else None,
            "temperature": model_config.temperature if model_config else None,
        }
        if tool_registry is not None:
            tools = tool_registry.openai_tools()
            if tools:
                request_options["tools"] = tools

        stream = await client.chat.completions.create(**request_options)
        pending_tool_calls: dict[int, dict[str, str]] = {}
        reasoning_chunks: list[str] = []
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta_data = chunk.choices[0].delta.model_dump(exclude_none=True)
            reasoning_text = delta_data.get("reasoning_content") or delta_data.get("reasoning")
            if isinstance(reasoning_text, str) and reasoning_text:
                reasoning_chunks.append(reasoning_text)
                yield StreamEvent(type="reasoning", text=reasoning_text)
            content_text = delta_data.get("content")
            if isinstance(content_text, str) and content_text:
                yield StreamEvent(type="content", text=content_text)
            tool_calls = delta_data.get("tool_calls")
            if isinstance(tool_calls, list):
                for call in tool_calls:
                    index = int(call.get("index", 0))
                    entry = pending_tool_calls.setdefault(
                        index,
                        {"id": "", "name": "", "arguments": ""},
                    )
                    if isinstance(call.get("id"), str):
                        entry["id"] = call["id"]
                    function_data = call.get("function", {})
                    if isinstance(function_data.get("name"), str):
                        entry["name"] = function_data["name"]
                    if isinstance(function_data.get("arguments"), str):
                        entry["arguments"] += function_data["arguments"]

        if not pending_tool_calls or tool_registry is None:
            break

        assistant_tool_calls: list[dict[str, object]] = []
        assistant_message: dict[str, object] = {"role": "assistant", "content": ""}
        if reasoning_chunks:
            assistant_message["reasoning_content"] = "".join(reasoning_chunks)

        for call in pending_tool_calls.values():
            tool_name = call["name"]
            arguments = call["arguments"]
            tool_id = call["id"] or f"call_{tool_name}"
            yield StreamEvent(type="tool_call", text=f"正在调用工具: {tool_name}")
            assistant_tool_calls.append(
                {
                    "id": tool_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": arguments,
                    },
                }
            )
        assistant_message["tool_calls"] = assistant_tool_calls
        messages.append(assistant_message)

        for call in pending_tool_calls.values():
            tool_name = call["name"]
            arguments = call["arguments"]
            tool_id = call["id"] or f"call_{tool_name}"
            tool_result = await tool_registry.execute(tool_name, arguments)
            yield StreamEvent(type="tool_call", text=f"工具调用完成: {tool_name}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": tool_result,
                }
            )


async def warmup_stream() -> bool:
    if _runtime_state is None or _runtime_config is None:
        return False
    if _runtime_state.provider == "dummy":
        return False

    provider_config = _runtime_config.llm.providers.get(_runtime_state.provider)
    if provider_config is None:
        return False
    if provider_config.api_style != "openai":
        return False

    client = _runtime_client or _build_openai_client(provider_config)
    stream = await client.chat.completions.create(
        model=_runtime_state.model,
        messages=[{"role": "user", "content": "ping"}],
        stream=True,
        max_tokens=1,
        temperature=0,
    )
    async for _ in stream:
        break
    return True
