from collections.abc import Sequence

from ayu.config import Config, State, load_config, load_state
from ayu.llm import initialize_runtime
from ayu.session import Session, SessionMessage
from ayu.storage import MessageQuery, PersistenceBackend, StoredMessage, StoredSession
from ayu.tools import ToolRegistry, build_default_tool_registry


class ChatRuntime:
    def __init__(
        self,
        config: Config,
        state: State,
        session: Session,
        tool_registry: ToolRegistry,
        backend: PersistenceBackend,
    ) -> None:
        self.config = config
        self.state = state
        self.session = session
        self.tool_registry = tool_registry
        self.backend = backend

    async def add_message(
        self,
        role: str,
        content: str,
        name: str | None = None,
        tool_call_id: str | None = None,
        tool_calls_json: str | None = None,
        reasoning_content: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> SessionMessage:
        msg = self.session.add_message(role, content, name, tool_call_id, tool_calls_json, reasoning_content)
        stored = StoredMessage(
            id=msg.id,
            session_id=msg.session_id,
            event_ts=msg.event_ts,
            role=msg.role,
            content=msg.content,
            name=msg.name,
            tool_call_id=msg.tool_call_id,
            tool_calls_json=msg.tool_calls_json,
            reasoning_content=msg.reasoning_content,
            metadata=metadata or {},
        )
        await self.backend.append_message(stored)
        return msg

    async def list_sessions(self) -> Sequence[StoredSession]:
        return await self.backend.list_sessions()

    async def switch_session(self, session_id: str) -> Session:
        stored_messages = await self.backend.list_messages(
            MessageQuery(session_id=session_id)
        )
        session = Session(id=session_id)
        for sm in stored_messages:
            session.add_message(sm.role, sm.content, sm.name, sm.tool_call_id, sm.tool_calls_json, sm.reasoning_content)
        self.session = session
        return session


def build_chat_runtime(backend: PersistenceBackend) -> ChatRuntime:
    config = load_config()
    state = load_state()
    session = Session()
    initialize_runtime(force=True)
    tool_registry = build_default_tool_registry()
    return ChatRuntime(
        config=config,
        state=state,
        session=session,
        tool_registry=tool_registry,
        backend=backend,
    )
