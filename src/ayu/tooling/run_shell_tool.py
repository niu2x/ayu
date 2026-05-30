import shlex
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from ayu.shell_exec import run_shell_command
from ayu.tooling.common import compute_shell_command_hash, resolve_target_path
from ayu.tooling.permission_actions import RUN_SHELL_ACTION


class RunShellParameters(BaseModel):
    command: str
    timeout_seconds: int = 120
    workdir: str | None = None
    max_output_bytes: int = 51200


class PathAccess(BaseModel):
    mode: str
    path: Path


def _resolve_workdir(workdir: str | None, workspace_root: Path) -> Path:
    if workdir is None:
        return workspace_root
    target = Path(workdir).expanduser()
    if not target.is_absolute():
        target = workspace_root / target
    return target.resolve()


def _split_commands(command: str) -> list[str]:
    return [part.strip() for part in command.split("&&") if part.strip()]


def _extract_redirects(tokens: list[str], cwd: Path, workspace_root: Path) -> tuple[list[PathAccess], list[str]]:
    accesses: list[PathAccess] = []
    normalized_tokens: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in {">", ">>", "1>", "2>", "<"} and index + 1 < len(tokens):
            target = resolve_target_path(tokens[index + 1], workspace_root if tokens[index + 1].startswith("/") else cwd)
            mode = "read" if token == "<" else "write"
            accesses.append(PathAccess(mode=mode, path=target))
            index += 2
            continue
        normalized_tokens.append(token)
        index += 1
    return accesses, normalized_tokens


def _extract_command_path_accesses(
    command: str,
    cwd: Path,
    workspace_root: Path,
) -> tuple[list[PathAccess], Path, bool]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return [], cwd, False
    if not tokens:
        return [], cwd, True

    if tokens[0] == "cd":
        if len(tokens) >= 2:
            next_cwd = resolve_target_path(tokens[1], workspace_root if tokens[1].startswith("/") else cwd)
            return [], next_cwd, True
        return [], cwd, True

    redirect_accesses, plain_tokens = _extract_redirects(tokens, cwd, workspace_root)
    if not plain_tokens:
        return redirect_accesses, cwd, True

    base = plain_tokens[0]
    args = plain_tokens[1:]
    accesses: list[PathAccess] = []
    recognized = False

    def add(mode: str, raw_path: str) -> None:
        target = resolve_target_path(raw_path, workspace_root if raw_path.startswith("/") else cwd)
        accesses.append(PathAccess(mode=mode, path=target))

    if base in {"git"}:
        if len(args) >= 1 and args[0] in {"status", "diff"}:
            add("read", ".")
            recognized = True
    elif base in {"cat", "head", "tail", "less", "more", "ls"}:
        recognized = True
        for arg in args:
            if not arg.startswith("-"):
                add("read", arg)
    elif base == "cp" and len(args) >= 2:
        recognized = True
        add("read", args[0])
        add("write", args[1])
    elif base == "mv" and len(args) >= 2:
        recognized = True
        add("write", args[0])
        add("write", args[1])
    elif base in {"rm", "mkdir", "touch"}:
        recognized = True
        for arg in args:
            if not arg.startswith("-"):
                add("write", arg)
    elif base in {"echo", "printf"}:
        recognized = True

    accesses.extend(redirect_accesses)
    if not recognized and redirect_accesses:
        recognized = True

    dedup = {(access.mode, str(access.path)): access for access in accesses}
    return list(dedup.values()), cwd, recognized


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
            "For chained commands, the tool pre-checks each sub-command and requests permission by read/write path before execution."
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
        current_cwd = resolved_workdir
        accesses: list[PathAccess] = []
        has_unknown_command = False
        for sub_command in _split_commands(cleaned_command):
            sub_accesses, next_cwd, recognized = _extract_command_path_accesses(
                sub_command,
                current_cwd,
                workspace_root,
            )
            accesses.extend(sub_accesses)
            current_cwd = next_cwd
            if not recognized:
                has_unknown_command = True

        for access in accesses:
            if access.path.is_relative_to(workspace_root):
                continue
            allowed = await registry.request_permission(
                PermissionRequest(
                    action=RUN_SHELL_ACTION,
                    target_kind="path",
                    key=f"{access.mode}::{access.path}",
                    target=str(access.path),
                    reason=f"shell 子命令需要{access.mode}权限: {access.path}",
                )
            )
            if not allowed:
                return (
                    "执行失败: shell 子命令路径未授权。\n"
                    f"mode: {access.mode}\n"
                    f"path: {access.path}"
                )

        if has_unknown_command:
            command_hash = compute_shell_command_hash(cleaned_command)
            allowed = await registry.request_permission(
                PermissionRequest(
                    action=RUN_SHELL_ACTION,
                    target_kind="command",
                    key=f"shell::{command_hash}",
                    target=cleaned_command,
                    reason="存在未知 shell 子命令，回退到整条命令授权",
                )
            )
            if not allowed:
                return (
                    "执行失败: 未知 shell 子命令未通过整条命令授权。\n"
                    f"command_hash: {command_hash}"
                )

        result = await run_shell_command(
            command=cleaned_command,
            timeout_seconds=timeout_seconds,
            workdir=workdir,
            max_output_bytes=max_output_bytes,
        )
        return result.model_dump_json(indent=2)
