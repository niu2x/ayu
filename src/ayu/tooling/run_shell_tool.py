from pathlib import Path
import shlex
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


def _resolve_workdir(workdir: str | None, workspace_root: Path) -> Path:
    if workdir is None:
        return workspace_root
    target = Path(workdir).expanduser()
    if not target.is_absolute():
        target = workspace_root / target
    return target.resolve()


def _is_readonly_git_command(command: str, workdir: Path, workspace_root: Path) -> bool:
    normalized = command.strip()
    if ">" in normalized:
        return False

    effective_workdir = workdir
    git_command = normalized

    if "&&" in normalized:
        parts = [part.strip() for part in normalized.split("&&") if part.strip()]
        if len(parts) != 2:
            return False
        left, right = parts
        if not left.startswith("cd "):
            return False
        try:
            cd_tokens = shlex.split(left)
        except ValueError:
            return False
        if len(cd_tokens) != 2 or cd_tokens[0] != "cd":
            return False
        cd_target = Path(cd_tokens[1]).expanduser()
        if not cd_target.is_absolute():
            cd_target = workdir / cd_target
        effective_workdir = cd_target.resolve()
        git_command = right

    if effective_workdir != workspace_root:
        return False
    return git_command.startswith("git status") or git_command.startswith("git diff")


class ToolRegistryLike(Protocol):
    def register(self, *args: object, **kwargs: object) -> object: ...

    async def request_permission(self, request: object) -> bool: ...


def register_run_shell_tool(registry: ToolRegistryLike, workspace_root: Path) -> None:
    @registry.register(
        name="run_shell",
        description=(
            "Use this to execute one shell command and get structured result. "
            "Input: command, optional timeout_seconds/workdir/max_output_bytes. "
            "Returns exit code, stdout, stderr, timeout status, and duration in JSON. "
            "Each command requires user permission by command hash before execution."
        ),
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

        resolved_workdir = _resolve_workdir(workdir, workspace_root)
        if not _is_readonly_git_command(cleaned_command, resolved_workdir, workspace_root):
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
