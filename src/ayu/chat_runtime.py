from ayu.config import Config, State, load_config, load_state
from ayu.llm import initialize_runtime
from ayu.session import Session
from ayu.tools import ToolRegistry, build_default_tool_registry

SYSTEM_PROMPT = "You are ayu, a helpful AI coding assistant."


class ChatRuntime:
    def __init__(
        self,
        config: Config,
        state: State,
        session: Session,
        tool_registry: ToolRegistry,
    ) -> None:
        self.config = config
        self.state = state
        self.session = session
        self.tool_registry = tool_registry


def build_chat_runtime() -> ChatRuntime:
    config = load_config()
    state = load_state()
    session = Session()
    session.add_message("system", SYSTEM_PROMPT)
    initialize_runtime(force=True)
    tool_registry = build_default_tool_registry()
    return ChatRuntime(
        config=config,
        state=state,
        session=session,
        tool_registry=tool_registry,
    )
