import json
from datetime import datetime
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, object]


ToolHandler = Callable[..., Awaitable[str]]


class RegisteredTool(BaseModel):
    spec: ToolSpec
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, object] | None = None,
        parameters_model: type[BaseModel] | None = None,
    ) -> Callable[[ToolHandler], ToolHandler]:
        if parameters is None and parameters_model is None:
            raise ValueError("parameters 和 parameters_model 不能同时为空")
        if parameters is not None and parameters_model is not None:
            raise ValueError("parameters 和 parameters_model 只能传一个")

        resolved_parameters = (
            parameters_model.model_json_schema() if parameters_model is not None else parameters
        )

        def decorator(func: ToolHandler) -> ToolHandler:
            self._tools[name] = RegisteredTool(
                spec=ToolSpec(
                    name=name,
                    description=description,
                    parameters=resolved_parameters or {},
                ),
                handler=func,
            )
            return func

        return decorator

    def openai_tools(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.spec.name,
                    "description": tool.spec.description,
                    "parameters": tool.spec.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    async def execute(self, name: str, arguments_json: str) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"工具不存在: {name}"
        try:
            arguments = json.loads(arguments_json) if arguments_json else {}
        except json.JSONDecodeError as exc:
            return f"工具参数解析失败: {exc}"
        try:
            result = await tool.handler(**arguments)
        except Exception as exc:
            return f"工具执行失败: {exc}"
        return str(result)


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    class WriteFileParameters(BaseModel):
        path: str
        content: str
        overwrite: bool = True

    @registry.register(
        name="write_file",
        description="Write content to a file path in workspace.",
        parameters_model=WriteFileParameters,
    )
    async def write_file(path: str, content: str, overwrite: bool = True) -> str:
        target = Path(path)
        if target.exists() and not overwrite:
            return f"写入失败: 文件已存在 {path}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, "utf-8")
        return f"写入成功: {path} ({len(content.encode('utf-8'))} bytes)"

    class ReadFileParameters(BaseModel):
        path: str
        start_line: int = 1
        line_count: int = 200

    class FeedbackParameters(BaseModel):
        opinion: str
        category: Literal["tool_missing", "blocked", "env_issue", "general"] = "general"

    @registry.register(
        name="read_file",
        description="Read file content by start line and line count.",
        parameters_model=ReadFileParameters,
    )
    async def read_file(
        path: str,
        start_line: int = 1,
        line_count: int = 200,
    ) -> str:
        if start_line < 1:
            return "读取失败: start_line 必须 >= 1"
        if line_count < 1:
            return "读取失败: line_count 必须 >= 1"
        if line_count > 1000:
            return "读取失败: line_count 不能大于 1000"

        target = Path(path)
        if not target.exists():
            return f"读取失败: 文件不存在 {path}"
        if target.is_dir():
            return f"读取失败: 目标是目录 {path}"

        content = target.read_text("utf-8")
        lines = content.splitlines()
        total_lines = len(lines)

        if total_lines == 0:
            return f"文件: {path}\n总行数: 0\n内容为空"

        selected_start = start_line
        selected_end = selected_start + line_count - 1

        if selected_start > total_lines:
            return (
                f"文件: {path}\n总行数: {total_lines}\n"
                f"请求区间: {selected_start}-{selected_end}\n"
                "结果: 超出文件范围"
            )

        selected_end = min(selected_end, total_lines)
        selected_lines = lines[selected_start - 1 : selected_end]

        rendered_content = "\n".join(
            f"{line_number}: {line_text}"
            for line_number, line_text in enumerate(selected_lines, start=selected_start)
        )
        return (
            f"文件: {path}\n"
            f"总行数: {total_lines}\n"
            f"返回区间: {selected_start}-{selected_end}\n"
            "内容:\n"
            f"{rendered_content}"
        )

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

    return registry
