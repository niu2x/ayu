from ayu.config import Config, State, ModelConfig, LLMProviderConfig


def test_config_defaults() -> None:
    config = Config()
    assert config.llm.providers == {}
    assert config.agent.max_tool_rounds == 25
    assert config.agent.auto_approve is False


def test_state_defaults() -> None:
    state = State()
    assert state.provider == "dummy"
    assert state.model == "dummy"
    assert state.theme == "ansi-dark"


def test_add_provider() -> None:
    config = Config()
    config.llm.providers["test"] = LLMProviderConfig(api_key="sk-test")
    assert config.llm.providers["test"].api_key == "sk-test"


def test_add_model() -> None:
    config = Config()
    config.llm.providers["test"] = LLMProviderConfig()
    config.llm.providers["test"].models["gpt-4"] = ModelConfig(max_tokens=8192)
    assert config.llm.providers["test"].models["gpt-4"].max_tokens == 8192


def test_serialize_roundtrip() -> None:
    config = Config()
    config.llm.providers["openai"] = LLMProviderConfig(
        api_key="sk-xxx",
        models={"gpt-4": ModelConfig(max_tokens=4096)},
    )
    data = config.model_dump_json()
    restored = Config.model_validate_json(data)
    assert restored.llm.providers["openai"].api_key == "sk-xxx"
    assert restored.llm.providers["openai"].models["gpt-4"].max_tokens == 4096
