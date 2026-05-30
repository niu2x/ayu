from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from ayu.tooling.common import resolve_target_path
from ayu.tooling.permission_actions import READ_FILE_ACTION


class ReadFileParameters(BaseModel):
    path: str
    start_line: int = 1
    line_count: int = 200


class ToolRegistryLike(Protocol):
    def register(self, *args: object, **kwargs: object) -> object: ...

    async def request_permission(self, request: object) -> bool: ...


def register_read_file_tool(registry: ToolRegistryLike, workspace_root: Path) -> None:
    @registry.register(
        name="read_file",
        description="Read file content by start line and line count.",
        parameters_model=ReadFileParameters,
    )
    async def read_file(path: str, start_line: int = 1, line_count: int = 200) -> str:
        from ayu.tools import PermissionRequest

        if start_line < 1:
            return "读取失败: start_line 必须 >= 1"
        if line_count < 1:
            return "读取失败: line_count 必须 >= 1"
        if line_count > 1000:
            return "读取失败: line_count 不能大于 1000"

        target = resolve_target_path(path, workspace_root)
        if not target.is_relative_to(workspace_root):
            allowed = await registry.request_permission(
                PermissionRequest(
                    action=READ_FILE_ACTION,
                    target_kind="path",
                    key=f"read::{target}",
                    target=str(target),
                    reason=f"读取路径不在当前工作目录内（workspace: {workspace_root}）",
                )
            )
            if not allowed:
                return (
                    "读取失败: 未获授权访问工作目录外路径。\n"
                    f"workspace: {workspace_root}\n"
                    f"target: {target}"
                )
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
