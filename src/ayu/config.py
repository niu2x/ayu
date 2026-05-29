from pathlib import Path

from platformdirs import PlatformDirs
from pydantic import BaseModel, Field

DIRS = PlatformDirs("ayu", "ayu")


class ModelConfig(BaseModel):
    """单个模型的配置"""

    max_tokens: int = 4096
    temperature: float = 0.7


class LLMProviderConfig(BaseModel):
    """单个 LLM 提供商的配置（api_key/base_url 提供商级别）"""

    api_style: str = "openai"
    api_key: str = ""
    base_url: str = ""
    models: dict[str, ModelConfig] = Field(default_factory=dict)


class LLMConfig(BaseModel):
    """LLM 提供商静态配置"""

    providers: dict[str, LLMProviderConfig] = Field(default_factory=dict)


class TUIConfig(BaseModel):
    """TUI 静态配置（暂无）"""

    pass


class AgentConfig(BaseModel):
    """Agent 行为配置"""

    max_tool_rounds: int = 25
    auto_approve: bool = False


class Config(BaseModel):
    """ayu 全局配置"""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    tui: TUIConfig = Field(default_factory=TUIConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)


class State(BaseModel):
    """用户当前选择（运行态，与静态配置分离）"""

    provider: str = "dummy"
    model: str = "dummy"
    theme: str = "ansi-dark"


def get_config_path() -> Path:
    return Path(DIRS.user_config_dir) / "config.json"


def get_state_path() -> Path:
    return Path(DIRS.user_config_dir) / "state.json"


def load_config() -> Config:
    path = get_config_path()
    if not path.exists():
        config = Config()
        save_config(config)
        return config
    return Config.model_validate_json(path.read_text("utf-8"))


def save_config(config: Config) -> None:
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config.model_dump_json(indent=2), "utf-8")


def load_state() -> State:
    path = get_state_path()
    if not path.exists():
        return State()
    return State.model_validate_json(path.read_text("utf-8"))


def save_state(state: State) -> None:
    path = get_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json(indent=2), "utf-8")
