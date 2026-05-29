from ayu.config import Config, State, load_config, load_state
from ayu.llm import initialize_runtime
from ayu.session import Session


class ChatRuntime:
    def __init__(self, config: Config, state: State, session: Session) -> None:
        self.config = config
        self.state = state
        self.session = session


def build_chat_runtime() -> ChatRuntime:
    config = load_config()
    state = load_state()
    session = Session()
    session.add_message("system", config.agent.system_prompt)
    initialize_runtime(force=True)
    return ChatRuntime(config=config, state=state, session=session)
