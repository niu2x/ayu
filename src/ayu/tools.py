import json
from pathlib import Path
from collections.abc import Awaitable, Callable

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

    return registry
