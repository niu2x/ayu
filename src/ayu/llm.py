import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel

from ayu.config import LLMProviderConfig, load_config, load_state


_runtime_config = None
_runtime_state = None
_runtime_client: AsyncOpenAI | None = None


class StreamEvent(BaseModel):
    type: Literal["reasoning", "content"]
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


async def chat(messages: list[dict]) -> str:
    parts: list[str] = []
    async for event in chat_stream(messages):
        parts.append(event.text)
    return "".join(parts)


async def chat_stream(messages: list[dict]) -> AsyncIterator[StreamEvent]:
    logging.getLogger("ayu").info("开始请求模型 4")

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

    logging.getLogger("ayu").info("开始请求模型 5")
    provider_config = _runtime_config.llm.providers.get(_runtime_state.provider)
    logging.getLogger("ayu").info("开始请求模型 6")
    if provider_config is None:
        yield StreamEvent(
            type="content",
            text=(
                f"提供商 [bold]{_runtime_state.provider}[/] 未配置。"
                f"请先运行: ayu config set-provider {_runtime_state.provider}"
            ),
        )
        return

    if provider_config.api_style == "openai":
        logging.getLogger("ayu").info("开始请求模型 7")
        async for event in _chat_openai_stream(provider_config, _runtime_state.model, messages):
            yield event
        return

    yield StreamEvent(type="content", text=f"不支持的 API 风格: {provider_config.api_style}")


async def _chat_openai_stream(
    provider_config: LLMProviderConfig, model: str, messages: list[dict]
) -> AsyncIterator[StreamEvent]:
    logging.getLogger("ayu").info("开始请求模型 8")
    client = _runtime_client or _build_openai_client(provider_config)
    logging.getLogger("ayu").info("开始请求模型 9")
    model_config = provider_config.models.get(model)
    logging.getLogger("ayu").info("开始请求模型 10")
    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        max_tokens=model_config.max_tokens if model_config else None,
        temperature=model_config.temperature if model_config else None,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta_data = chunk.choices[0].delta.model_dump(exclude_none=True)
        reasoning_text = delta_data.get("reasoning_content") or delta_data.get("reasoning")
        if isinstance(reasoning_text, str) and reasoning_text:
            yield StreamEvent(type="reasoning", text=reasoning_text)
        content_text = delta_data.get("content")
        if isinstance(content_text, str) and content_text:
            yield StreamEvent(type="content", text=content_text)


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
