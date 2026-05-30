from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel


class FeedbackParameters(BaseModel):
    opinion: str
    category: Literal["tool_missing", "blocked", "env_issue", "general"] = "general"


class ToolRegistryLike(Protocol):
    def register(self, *args: object, **kwargs: object) -> object: ...


def register_feedback_tool(registry: ToolRegistryLike) -> None:
    @registry.register(
        name="feedback",
        description="Collect agent feedback about blockers, missing tools, or constraints.",
        parameters_model=FeedbackParameters,
    )
    async def feedback(
        opinion: str,
        category: Literal["tool_missing", "blocked", "env_issue", "general"] = "general",
    ) -> str:
        cleaned_opinion = opinion.strip()
        if not cleaned_opinion:
            return "反馈失败: opinion 不能为空"

        feedback_file = Path.cwd() / "agent_feedback.md"
        timestamp = datetime.now().isoformat(timespec="seconds")
        entry = (
            "## Agent Feedback\n"
            f"- time: {timestamp}\n"
            f"- category: {category}\n"
            f"- opinion: {cleaned_opinion}\n\n"
        )
        with feedback_file.open("a", encoding="utf-8") as file:
            file.write(entry)

        return "好的，你反映的状况之后会优化，现在请您发挥主观能动性，尝试其他变通方案"
