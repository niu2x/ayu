from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from ayu.shell_exec import run_shell_command
from ayu.tooling.common import compute_shell_command_hash
from ayu.tooling.permission_actions import RUN_SHELL_ACTION


class RunShellParameters(BaseModel):
    command: str
    timeout_seconds: int = 120
    workdir: str | None = None
    max_output_bytes: int = 51200


class ToolRegistryLike(Protocol):
    def register(self, *args: object, **kwargs: object) -> object: ...

    async def request_permission(self, request: object) -> bool: ...


def register_run_shell_tool(registry: ToolRegistryLike, workspace_root: Path) -> None:
    @registry.register(
        name="run_shell",
        description="Run shell command with asyncio subprocess and return structured output.",
        parameters_model=RunShellParameters,
    )
    async def run_shell(
        command: str,
        timeout_seconds: int = 120,
        workdir: str | None = None,
        max_output_bytes: int = 51200,
    ) -> str:
        from ayu.tools import PermissionRequest

        cleaned_command = command.strip()
        if not cleaned_command:
            return "执行失败: command 不能为空"
        if timeout_seconds < 1:
            return "执行失败: timeout_seconds 必须 >= 1"
        if timeout_seconds > 600:
            return "执行失败: timeout_seconds 不能大于 600"
        if max_output_bytes < 1024:
            return "执行失败: max_output_bytes 必须 >= 1024"
        if max_output_bytes > 1024 * 1024:
            return "执行失败: max_output_bytes 不能大于 1048576"

        command_hash = compute_shell_command_hash(cleaned_command)
        allowed = await registry.request_permission(
            PermissionRequest(
                action=RUN_SHELL_ACTION,
                target_kind="command",
                key=f"shell::{command_hash}",
                target=cleaned_command,
                reason=f"shell 命令执行需要用户授权（workspace: {workspace_root}）",
            )
        )
        if not allowed:
            return (
                "执行失败: 当前 shell 命令未授权。\n"
                f"command_hash: {command_hash}\n"
                "用户已拒绝或未完成授权。"
            )

        result = await run_shell_command(
            command=cleaned_command,
            timeout_seconds=timeout_seconds,
            workdir=workdir,
            max_output_bytes=max_output_bytes,
        )
        return result.model_dump_json(indent=2)
