from datetime import datetime

import pytest

from ayu.storage import MessageQuery, SqliteBackend, StoredMessage, StoredSession


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


@pytest.mark.asyncio
async def test_sqlite_backend_session_and_message_flow(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    backend = SqliteBackend(db_path=db_path)
    await backend.setup()

    session = StoredSession(id="s1", title="demo", created_at=_now_iso(), updated_at=_now_iso())
    await backend.create_session(session)

    loaded = await backend.get_session("s1")
    assert loaded is not None
    assert loaded.id == "s1"
    assert loaded.title == "demo"

    msg1 = StoredMessage(
        id="m1",
        session_id="s1",
        event_ts=_now_iso(),
        role="user",
        content="hello",
    )
    msg2 = StoredMessage(
        id="m2",
        session_id="s1",
        event_ts=_now_iso(),
        role="assistant",
        content="world",
    )
    await backend.append_messages([msg1, msg2])

    items = await backend.list_messages(MessageQuery(session_id="s1"))
    assert [item.id for item in items] == ["m1", "m2"]

    await backend.delete_message("m1")
    items_after_delete = await backend.list_messages(MessageQuery(session_id="s1"))
    assert [item.id for item in items_after_delete] == ["m2"]

    deleted_count = await backend.delete_messages_by_session("s1")
    assert deleted_count == 1
    items_after_clear = await backend.list_messages(MessageQuery(session_id="s1"))
    assert items_after_clear == []

    await backend.close()


@pytest.mark.asyncio
async def test_sqlite_backend_session_title_update(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    backend = SqliteBackend(db_path=db_path)
    await backend.setup()

    session = StoredSession(id="s1", title="old", created_at=_now_iso(), updated_at=_now_iso())
    await backend.create_session(session)
    await backend.update_session_title("s1", "new")

    loaded = await backend.get_session("s1")
    assert loaded is not None
    assert loaded.title == "new"

    await backend.close()


@pytest.mark.asyncio
async def test_sqlite_backend_list_sessions_order(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    backend = SqliteBackend(db_path=db_path)
    await backend.setup()

    now = _now_iso()
    s1 = StoredSession(id="s1", title="first", created_at=now, updated_at="2000-01-01T00:00:00")
    s2 = StoredSession(id="s2", title="second", created_at=now, updated_at="2000-01-02T00:00:00")
    s3 = StoredSession(id="s3", title="third", created_at=now, updated_at="2000-01-03T00:00:00")
    await backend.create_session(s1)
    await backend.create_session(s2)
    await backend.create_session(s3)

    sessions = await backend.list_sessions()
    assert [s.id for s in sessions] == ["s3", "s2", "s1"]

    sessions = await backend.list_sessions(limit=2)
    assert [s.id for s in sessions] == ["s3", "s2"]

    await backend.close()


@pytest.mark.asyncio
async def test_sqlite_backend_delete_session_cascade(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    backend = SqliteBackend(db_path=db_path)
    await backend.setup()

    session = StoredSession(id="s1", title="demo", created_at=_now_iso(), updated_at=_now_iso())
    await backend.create_session(session)
    msg = StoredMessage(id="m1", session_id="s1", event_ts=_now_iso(), role="user", content="hi")
    await backend.append_message(msg)

    await backend.delete_session("s1")

    assert await backend.get_session("s1") is None
    items = await backend.list_messages(MessageQuery(session_id="s1"))
    assert items == []

    await backend.close()


@pytest.mark.asyncio
async def test_sqlite_backend_get_nonexistent(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    backend = SqliteBackend(db_path=db_path)
    await backend.setup()

    assert await backend.get_message("nonexistent") is None
    assert await backend.get_session("nonexistent") is None

    await backend.close()
