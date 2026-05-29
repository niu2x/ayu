import asyncio
import logging
from openai import AsyncOpenAI

from ayu.config import LLMProviderConfig, load_config, load_state


_runtime_config = None
_runtime_state = None
_runtime_client: AsyncOpenAI | None = None


def _build_openai_client(provider_config: LLMProviderConfig) -> AsyncOpenAI:
    logging.getLogger(__name__).info("_build_openai_client")
    return AsyncOpenAI(
        api_key=provider_config.api_key,
        base_url=provider_config.base_url or None,
    )


def initialize_runtime(force: bool = False) -> None:

    logging.getLogger(__name__).info("initialize_runtime 1")
    global _runtime_config, _runtime_state, _runtime_client

    logging.getLogger(__name__).info("initialize_runtime 2")
    if _runtime_config is not None and _runtime_state is not None and not force:
        return

    logging.getLogger(__name__).info("initialize_runtime 3")
    _runtime_config = load_config()
    logging.getLogger(__name__).info("initialize_runtime 4")
    _runtime_state = load_state()
    logging.getLogger(__name__).info("initialize_runtime 5")
    _runtime_client = None

    if _runtime_state.provider == "dummy":
        return

    logging.getLogger(__name__).info("initialize_runtime 6")
    provider_config = _runtime_config.llm.providers.get(_runtime_state.provider)
    logging.getLogger(__name__).info("initialize_runtime 7")
    if provider_config is None:
        return

    if provider_config.api_style == "openai":
        logging.getLogger(__name__).info("initialize_runtime 8")
        _runtime_client = _build_openai_client(provider_config)
        logging.getLogger(__name__).info("initialize_runtime 9")


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
    if _runtime_state is None:
        return "运行态未初始化，请先调用 initialize_runtime()"

    if _runtime_state.provider == "dummy":
        await asyncio.sleep(0.3)
        return "OK"

    if _runtime_config is None:
        return "配置未初始化"

    provider_config = _runtime_config.llm.providers.get(_runtime_state.provider)
    if provider_config is None:
        return (
            f"提供商 [bold]{_runtime_state.provider}[/] 未配置。"
            f"请先运行: ayu config set-provider {_runtime_state.provider}"
        )

    if provider_config.api_style == "openai":
        return await _chat_openai(provider_config, _runtime_state.model, messages)

    return f"不支持的 API 风格: {provider_config.api_style}"


async def _chat_openai(
    provider_config: LLMProviderConfig, model: str, messages: list[dict]
) -> str:
    client = _runtime_client or _build_openai_client(provider_config)
    model_config = provider_config.models.get(model)
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=model_config.max_tokens if model_config else None,
        temperature=model_config.temperature if model_config else None,
    )
    return response.choices[0].message.content or ""
