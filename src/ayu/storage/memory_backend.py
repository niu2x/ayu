from collections.abc import Sequence

from ayu.storage.interfaces import PersistenceBackend
from ayu.storage.models import MessageQuery, StorageCapabilities, StoredMessage, StoredSession


class InMemoryBackend(PersistenceBackend):
    def __init__(self) -> None:
        self._sessions: dict[str, StoredSession] = {}
        self._messages: dict[str, StoredMessage] = {}
        self._messages_by_session: dict[str, list[str]] = {}
        self._capabilities = StorageCapabilities(bm25=False, vector=False, transactions=False)

    @property
    def capabilities(self) -> StorageCapabilities:
        return self._capabilities

    async def setup(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def create_session(self, session: StoredSession) -> None:
        self._sessions[session.id] = session
        self._messages_by_session.setdefault(session.id, [])

    async def get_session(self, session_id: str) -> StoredSession | None:
        return self._sessions.get(session_id)

    async def list_sessions(self, limit: int = 50, offset: int = 0) -> Sequence[StoredSession]:
        items = sorted(self._sessions.values(), key=lambda item: item.updated_at, reverse=True)
        return items[offset : offset + limit]

    async def update_session_title(self, session_id: str, title: str) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        self._sessions[session_id] = session.model_copy(update={"title": title})

    async def delete_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        message_ids = self._messages_by_session.pop(session_id, [])
        for message_id in message_ids:
            self._messages.pop(message_id, None)

    async def append_message(self, message: StoredMessage) -> None:
        self._messages[message.id] = message
        self._messages_by_session.setdefault(message.session_id, []).append(message.id)

    async def append_messages(self, messages: Sequence[StoredMessage]) -> None:
        for message in messages:
            await self.append_message(message)

    async def get_message(self, message_id: str) -> StoredMessage | None:
        return self._messages.get(message_id)

    async def list_messages(self, query: MessageQuery) -> Sequence[StoredMessage]:
        message_ids = self._messages_by_session.get(query.session_id, [])
        messages = [self._messages[item] for item in message_ids if item in self._messages]
        if query.roles is not None:
            roles = set(query.roles)
            messages = [message for message in messages if message.role in roles]
        if query.after_ts is not None:
            messages = [message for message in messages if message.event_ts >= query.after_ts]
        if query.before_ts is not None:
            messages = [message for message in messages if message.event_ts <= query.before_ts]
        return messages[query.offset : query.offset + query.limit]

    async def delete_message(self, message_id: str) -> None:
        message = self._messages.pop(message_id, None)
        if message is None:
            return
        ids = self._messages_by_session.get(message.session_id)
        if ids is None:
            return
        self._messages_by_session[message.session_id] = [item for item in ids if item != message_id]

    async def delete_messages_by_session(self, session_id: str) -> int:
        ids = self._messages_by_session.get(session_id, [])
        for message_id in ids:
            self._messages.pop(message_id, None)
        self._messages_by_session[session_id] = []
        return len(ids)

    async def index_message(self, message: StoredMessage) -> None:
        return None

    async def remove_message_index(self, message_id: str) -> None:
        return None

    async def search_bm25(self, text: str, session_id: str | None, limit: int = 20) -> Sequence[str]:
        return []

    async def search_vector(self, embedding: list[float], session_id: str | None, limit: int = 20) -> Sequence[str]:
        return []
