from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from ayu.tooling.common import resolve_target_path
from ayu.tooling.permission_actions import WRITE_FILE_ACTION


class WriteFileParameters(BaseModel):
    path: str
    content: str
    overwrite: bool = True


class ToolRegistryLike(Protocol):
    def register(self, *args: object, **kwargs: object) -> object: ...

    async def request_permission(self, request: object) -> bool: ...


def register_write_file_tool(registry: ToolRegistryLike, workspace_root: Path) -> None:
    @registry.register(
        name="write_file",
        description="Write content to a file path in workspace.",
        parameters_model=WriteFileParameters,
    )
    async def write_file(path: str, content: str, overwrite: bool = True) -> str:
        from ayu.tools import PermissionRequest

        target = resolve_target_path(path, workspace_root)
        if not target.is_relative_to(workspace_root):
            allowed = await registry.request_permission(
                PermissionRequest(
                    action=WRITE_FILE_ACTION,
                    target_kind="path",
                    key=f"write::{target}",
                    target=str(target),
                    reason=f"写入路径不在当前工作目录内（workspace: {workspace_root}）",
                )
            )
            if not allowed:
                return (
                    "写入失败: 未获授权访问工作目录外路径。\n"
                    f"workspace: {workspace_root}\n"
                    f"target: {target}"
                )
        if target.exists() and not overwrite:
            return f"写入失败: 文件已存在 {path}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, "utf-8")
        return f"写入成功: {path} ({len(content.encode('utf-8'))} bytes)"
