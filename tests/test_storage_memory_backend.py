from datetime import datetime

import pytest

from hi_ayu.storage import MessageQuery, StoredMessage, StoredSession, create_backend


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


@pytest.mark.asyncio
async def test_memory_backend_session_and_message_flow() -> None:
    backend = create_backend("memory")
    await backend.setup()

    session = StoredSession(id="s1", title="demo", created_at=_now_iso(), updated_at=_now_iso())
    await backend.create_session(session)

    loaded = await backend.get_session("s1")
    assert loaded is not None
    assert loaded.id == "s1"

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
