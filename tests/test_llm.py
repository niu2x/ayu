import pytest

from ayu.llm import chat


@pytest.mark.asyncio
async def test_dummy_provider() -> None:
    result = await chat([{"role": "user", "content": "hello"}])
    assert result == "OK"
