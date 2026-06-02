import pytest

from hi_ayu.config import State
from hi_ayu.llm import chat, initialize_runtime


@pytest.mark.asyncio
async def test_dummy_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hi_ayu.llm.load_state", lambda: State(provider="dummy", model="dummy"))
    initialize_runtime(force=True)
    result = await chat([{"role": "user", "content": "hello"}])
    assert result == "OK"
