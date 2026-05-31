import json
from collections.abc import Sequence
from pathlib import Path

import aiosqlite

from ayu.config import DIRS
from ayu.storage.interfaces import PersistenceBackend
from ayu.storage.models import MessageQuery, StorageCapabilities, StoredMessage, StoredSession


class SqliteBackend(PersistenceBackend):
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or Path(DIRS.user_data_dir) / "ayu.db"
        self._conn: aiosqlite.Connection | None = None
        self._capabilities = StorageCapabilities(
            bm25=False, vector=False, transactions=False
        )

    @property
    def capabilities(self) -> StorageCapabilities:
        return self._capabilities

    async def setup(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self._db_path))
        self._conn.row_factory = aiosqlite.Row

        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                event_ts TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                name TEXT,
                tool_call_id TEXT,
                tool_calls_json TEXT,
                metadata TEXT NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session_ts
                ON messages(session_id, event_ts);
        """)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def _require_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("SqliteBackend not setup; call setup() first")
        return self._conn

    def _session_to_row(self, session: StoredSession) -> tuple:
        return (
            session.id,
            session.title,
            session.created_at,
            session.updated_at,
            json.dumps(session.metadata, ensure_ascii=False),
        )

    def _row_to_session(self, row: aiosqlite.Row) -> StoredSession:
        return StoredSession(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata"]),
        )

    def _message_to_row(self, message: StoredMessage) -> tuple:
        return (
            message.id,
            message.session_id,
            message.event_ts,
            message.role,
            message.content,
            message.name,
            message.tool_call_id,
            message.tool_calls_json,
            json.dumps(message.metadata, ensure_ascii=False),
        )

    def _row_to_message(self, row: aiosqlite.Row) -> StoredMessage:
        return StoredMessage(
            id=row["id"],
            session_id=row["session_id"],
            event_ts=row["event_ts"],
            role=row["role"],
            content=row["content"],
            name=row["name"],
            tool_call_id=row["tool_call_id"],
            tool_calls_json=row["tool_calls_json"],
            metadata=json.loads(row["metadata"]),
        )

    async def create_session(self, session: StoredSession) -> None:
        conn = self._require_conn()
        await conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at, metadata) "
            "VALUES (?, ?, ?, ?, ?)",
            self._session_to_row(session),
        )
        await conn.commit()

    async def get_session(self, session_id: str) -> StoredSession | None:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        return self._row_to_session(row) if row else None

    async def list_sessions(
        self, limit: int = 50, offset: int = 0
    ) -> Sequence[StoredSession]:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        return [self._row_to_session(row) for row in rows]

    async def update_session_title(self, session_id: str, title: str) -> None:
        conn = self._require_conn()
        await conn.execute(
            "UPDATE sessions SET title = ? WHERE id = ?", (title, session_id)
        )
        await conn.commit()

    async def delete_session(self, session_id: str) -> None:
        conn = self._require_conn()
        await conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        await conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await conn.commit()

    async def append_message(self, message: StoredMessage) -> None:
        conn = self._require_conn()
        await conn.execute(
            "INSERT INTO messages "
            "(id, session_id, event_ts, role, content, name, tool_call_id, tool_calls_json, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            self._message_to_row(message),
        )
        await conn.commit()

    async def append_messages(self, messages: Sequence[StoredMessage]) -> None:
        conn = self._require_conn()
        await conn.executemany(
            "INSERT INTO messages "
            "(id, session_id, event_ts, role, content, name, tool_call_id, tool_calls_json, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [self._message_to_row(msg) for msg in messages],
        )
        await conn.commit()

    async def get_message(self, message_id: str) -> StoredMessage | None:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        )
        row = await cursor.fetchone()
        return self._row_to_message(row) if row else None

    async def list_messages(self, query: MessageQuery) -> Sequence[StoredMessage]:
        conn = self._require_conn()
        conditions = ["session_id = ?"]
        params: list[object] = [query.session_id]

        if query.roles is not None:
            placeholders = ", ".join("?" for _ in query.roles)
            conditions.append(f"role IN ({placeholders})")
            params.extend(query.roles)
        if query.after_ts is not None:
            conditions.append("event_ts >= ?")
            params.append(query.after_ts)
        if query.before_ts is not None:
            conditions.append("event_ts <= ?")
            params.append(query.before_ts)

        sql = (
            f"SELECT * FROM messages WHERE {' AND '.join(conditions)} "
            f"ORDER BY event_ts ASC LIMIT ? OFFSET ?"
        )
        params.extend([query.limit, query.offset])

        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [self._row_to_message(row) for row in rows]

    async def delete_message(self, message_id: str) -> None:
        conn = self._require_conn()
        await conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        await conn.commit()

    async def delete_messages_by_session(self, session_id: str) -> int:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        count = row[0] if row else 0
        await conn.execute(
            "DELETE FROM messages WHERE session_id = ?", (session_id,)
        )
        await conn.commit()
        return count

    async def index_message(self, message: StoredMessage) -> None:
        return None

    async def remove_message_index(self, message_id: str) -> None:
        return None

    async def search_bm25(
        self, text: str, session_id: str | None, limit: int = 20
    ) -> Sequence[str]:
        return []

    async def search_vector(
        self, embedding: list[float], session_id: str | None, limit: int = 20
    ) -> Sequence[str]:
        return []
