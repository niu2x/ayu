import json
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel

from ayu.tooling.permission_actions import PermissionAction
from ayu.tooling import (
    register_apply_patch_tool,
    register_feedback_tool,
    register_read_file_tool,
    register_run_shell_tool,
    register_write_file_tool,
)


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, object]


ToolHandler = Callable[..., Awaitable[str]]
PermissionDecision = Literal["deny", "allow_once", "allow_session"]
PermissionHandler = Callable[["PermissionRequest"], Awaitable[PermissionDecision]]


class PermissionRequest(BaseModel):
    action: PermissionAction
    target_kind: Literal["path", "command"]
    key: str
    target: str
    reason: str


class RegisteredTool(BaseModel):
    spec: ToolSpec
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        self._permission_handler: PermissionHandler | None = None
        self._session_permissions: set[str] = set()

    def set_permission_handler(self, handler: PermissionHandler) -> None:
        self._permission_handler = handler

    async def request_permission(self, request: PermissionRequest) -> bool:
        if request.key in self._session_permissions:
            return True
        if self._permission_handler is None:
            return True
        decision = await self._permission_handler(request)
        if decision == "allow_session":
            self._session_permissions.add(request.key)
            return True
        if decision == "allow_once":
            return True
        return False

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
    workspace_root = Path.cwd().resolve()

    register_write_file_tool(registry, workspace_root)
    register_read_file_tool(registry, workspace_root)
    register_feedback_tool(registry)
    register_run_shell_tool(registry, workspace_root)
    register_apply_patch_tool(registry, workspace_root)

    return registry
