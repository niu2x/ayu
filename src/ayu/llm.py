import asyncio

from ayu.config import LLMProviderConfig, load_config, load_state


async def chat(messages: list[dict]) -> str:
    state = load_state()

    if state.provider == "dummy":
        await asyncio.sleep(0.3)
        return "OK"

    config = load_config()
    provider_config = config.llm.providers.get(state.provider)
    if provider_config is None:
        return (
            f"提供商 [bold]{state.provider}[/] 未配置。"
            f"请先运行: ayu config set-provider {state.provider}"
        )

    if provider_config.api_style == "openai":
        return await _chat_openai(provider_config, state.model, messages)

    return f"不支持的 API 风格: {provider_config.api_style}"


async def _chat_openai(
    provider_config: LLMProviderConfig, model: str, messages: list[dict]
) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=provider_config.api_key,
        base_url=provider_config.base_url or None,
    )
    model_config = provider_config.models.get(model)
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=model_config.max_tokens if model_config else None,
        temperature=model_config.temperature if model_config else None,
    )
    return response.choices[0].message.content or ""
