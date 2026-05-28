import pytest

from ayu.config import State
from ayu.llm import chat


@pytest.mark.asyncio
async def test_dummy_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ayu.llm.load_state", lambda: State(provider="dummy", model="dummy"))
    result = await chat([{"role": "user", "content": "hello"}])
    assert result == "OK"
