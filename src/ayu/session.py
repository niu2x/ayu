from datetime import datetime
import json
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


MessageRole = Literal["system", "user", "assistant", "tool"]


class SessionMessage(BaseModel):
    id: str
    session_id: str
    event_ts: str
    role: MessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls_json: str | None = None
    reasoning_content: str | None = None

    def to_llm_message(self) -> dict[str, str | list | None]:
        message: dict[str, str | list | None] = {"role": self.role, "content": self.content}
        if self.name:
            message["name"] = self.name
        if self.tool_call_id:
            message["tool_call_id"] = self.tool_call_id
        if self.tool_calls_json:
            message["tool_calls"] = json.loads(self.tool_calls_json)
        if self.reasoning_content:
            message["reasoning_content"] = self.reasoning_content
        return message


class Session(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    messages: list[SessionMessage] = Field(default_factory=list)

    def add_message(
        self,
        role: MessageRole,
        content: str,
        name: str | None = None,
        tool_call_id: str | None = None,
        tool_calls_json: str | None = None,
        reasoning_content: str | None = None,
    ) -> SessionMessage:
        event_id = uuid4().hex
        event_ts = datetime.now().astimezone().isoformat(timespec="milliseconds")
        msg = SessionMessage(
            id=event_id,
            session_id=self.id,
            event_ts=event_ts,
            role=role,
            content=content,
            name=name,
            tool_call_id=tool_call_id,
            tool_calls_json=tool_calls_json,
            reasoning_content=reasoning_content,
        )
        self.messages.append(msg)
        return msg

    def to_llm_messages(self) -> list[dict[str, str]]:
        return [message.to_llm_message() for message in self.messages]
