from typing import Literal

from pydantic import BaseModel, Field


MessageRole = Literal["system", "user", "assistant", "tool"]


class StoredSession(BaseModel):
    id: str
    title: str | None = None
    created_at: str
    updated_at: str
    metadata: dict[str, object] = Field(default_factory=dict)


class StoredMessage(BaseModel):
    id: str
    session_id: str
    event_ts: str
    role: MessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class MessageQuery(BaseModel):
    session_id: str
    roles: list[MessageRole] | None = None
    after_ts: str | None = None
    before_ts: str | None = None
    limit: int = 200
    offset: int = 0


class StorageCapabilities(BaseModel):
    bm25: bool = False
    vector: bool = False
    transactions: bool = False
