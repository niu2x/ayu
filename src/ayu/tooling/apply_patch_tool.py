from pathlib import Path
import re
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from ayu.tooling.permission_actions import APPLY_PATCH_ACTION


class ApplyPatchParameters(BaseModel):
    patch: str


class ToolRegistryLike(Protocol):
    def register(self, *args: object, **kwargs: object) -> object: ...

    async def request_permission(self, request: object) -> bool: ...


class PatchOperation(BaseModel):
    kind: Literal["add", "update", "delete"]
    path: str
    move_to: str | None = None
    lines: list[str] = Field(default_factory=list)


def _resolve_target_path(path: str, workspace_root: Path) -> Path:
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = workspace_root / target
    return target.resolve()


def _parse_patch_operations(patch: str) -> list[PatchOperation]:
    patch_lines = patch.splitlines()
    if not patch_lines or patch_lines[0] != "*** Begin Patch":
        raise ValueError("patch 首行必须是 *** Begin Patch")
    if patch_lines[-1] != "*** End Patch":
        raise ValueError("patch 末行必须是 *** End Patch")

    operations: list[PatchOperation] = []
    index = 1
    while index < len(patch_lines) - 1:
        line = patch_lines[index]
        if not line.strip():
            index += 1
            continue

        if line.startswith("*** Add File: "):
            path = line.removeprefix("*** Add File: ").strip()
            index += 1
            content_lines: list[str] = []
            while index < len(patch_lines) - 1 and not patch_lines[index].startswith("*** "):
                current = patch_lines[index]
                if not current.startswith("+"):
                    raise ValueError(f"Add File {path} 中存在未以 + 开头的行: {current}")
                content_lines.append(current[1:])
                index += 1
            operations.append(PatchOperation(kind="add", path=path, lines=content_lines))
            continue

        if line.startswith("*** Delete File: "):
            path = line.removeprefix("*** Delete File: ").strip()
            operations.append(PatchOperation(kind="delete", path=path))
            index += 1
            continue

        if line.startswith("*** Update File: "):
            path = line.removeprefix("*** Update File: ").strip()
            index += 1
            move_to: str | None = None
            if index < len(patch_lines) - 1 and patch_lines[index].startswith("*** Move to: "):
                move_to = patch_lines[index].removeprefix("*** Move to: ").strip()
                index += 1
            body_lines: list[str] = []
            while index < len(patch_lines) - 1 and not patch_lines[index].startswith("*** "):
                body_lines.append(patch_lines[index])
                index += 1
            operations.append(PatchOperation(kind="update", path=path, move_to=move_to, lines=body_lines))
            continue

        raise ValueError(f"未知 patch 指令: {line}")

    if not operations:
        raise ValueError("patch 中没有可执行操作")
    return operations


def _validate_update_lines(path: str, lines: list[str]) -> None:
    if not lines:
        raise ValueError(f"Update File {path} 缺少 hunk 内容")
    has_hunk = False
    for line in lines:
        if line.startswith("@@"):
            has_hunk = True
            continue
        if line.startswith(("+", "-", " ")):
            continue
        raise ValueError(f"Update File {path} 包含非法 hunk 行: {line}")
    if not has_hunk:
        raise ValueError(f"Update File {path} 缺少 @@ hunk 头")


def _apply_update_hunks(content: str, lines: list[str], path: str) -> str:
    original_lines = content.splitlines()
    has_trailing_newline = content.endswith("\n")
    index = 0
    hunk_number = 0
    line_offset = 0

    while index < len(lines):
        line = lines[index]
        if not line.startswith("@@"):
            index += 1
            continue

        hunk_number += 1
        header = line
        header_match = re.match(
            r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:\s+(.*))?$",
            header,
        )
        if header_match is None:
            raise ValueError(f"文件 {path} 第 {hunk_number} 个 hunk 头非法: {header}")
        old_start = int(header_match.group(1))
        anchor_text = (header_match.group(5) or "").strip()
        index += 1
        hunk_deletes: list[str] = []
        hunk_adds: list[str] = []
        while index < len(lines):
            current = lines[index]
            if current.startswith("@@"):
                break
            if current.startswith("+"):
                hunk_adds.append(current[1:])
            elif current.startswith("-"):
                hunk_deletes.append(current[1:])
            elif current.startswith(" "):
                context_line = current[1:]
                hunk_deletes.append(context_line)
                hunk_adds.append(context_line)
            else:
                raise ValueError(f"文件 {path} 第 {hunk_number} 个 hunk 存在非法行: {current}")
            index += 1

        if not hunk_deletes and not hunk_adds:
            raise ValueError(f"文件 {path} 第 {hunk_number} 个 hunk 为空: {header}")

        anchor_index: int | None = None
        if anchor_text:
            expected_anchor_index = old_start - 1 + line_offset
            if expected_anchor_index < 0 or expected_anchor_index >= len(original_lines):
                raise ValueError(
                    f"文件 {path} 第 {hunk_number} 个 hunk 锚点行号越界: "
                    f"line={old_start}, anchor={anchor_text}"
                )
            actual_anchor_line = original_lines[expected_anchor_index].strip()
            if actual_anchor_line != anchor_text:
                raise ValueError(
                    f"文件 {path} 第 {hunk_number} 个 hunk 锚点与行号不匹配: "
                    f"line={old_start}, expected={anchor_text}, actual={actual_anchor_line}"
                )
            anchor_index = expected_anchor_index

        if not hunk_deletes:
            if anchor_index is not None:
                insert_at = anchor_index + 1
            else:
                insert_at = old_start - 1 + line_offset
            insert_at = max(0, min(insert_at, len(original_lines)))
            original_lines[insert_at:insert_at] = hunk_adds
            line_offset += len(hunk_adds)
            continue

        found_at = -1
        search_limit = len(original_lines) - len(hunk_deletes) + 1
        if anchor_index is not None:
            search_range = range(anchor_index, max(search_limit, 0))
        else:
            search_range = range(max(search_limit, 0))

        for search_index in search_range:
            if original_lines[search_index : search_index + len(hunk_deletes)] == hunk_deletes:
                found_at = search_index
                break

        if found_at < 0:
            snippet = "\\n".join(hunk_deletes[:5])
            raise ValueError(
                f"文件 {path} 第 {hunk_number} 个 hunk 未命中上下文。"
                f"hunk 头: {header}; 期望片段: {snippet}"
            )

        original_lines[found_at : found_at + len(hunk_deletes)] = hunk_adds
        line_offset += len(hunk_adds) - len(hunk_deletes)

    updated = "\n".join(original_lines)
    if has_trailing_newline:
        updated += "\n"
    return updated


async def _check_path_permission(
    registry: ToolRegistryLike,
    mode: Literal["read", "write"],
    path: Path,
    workspace_root: Path,
) -> bool:
    from ayu.tools import PermissionRequest

    if path.is_relative_to(workspace_root):
        return True

    return await registry.request_permission(
        PermissionRequest(
            action=APPLY_PATCH_ACTION,
            target_kind="path",
            key=f"{mode}::{path}",
            target=str(path),
            reason=f"apply_patch 需要 {mode} 路径授权（workspace: {workspace_root}）",
        )
    )


def register_apply_patch_tool(registry: ToolRegistryLike, workspace_root: Path) -> None:
    @registry.register(
        name="apply_patch",
        description=(
            "Use this to edit files with structured patch text. "
            "Input must include *** Begin Patch and *** End Patch. "
            "Supported operations: *** Add File, *** Update File (optional *** Move to), and *** Delete File. "
            "Add File lines must start with '+'. Update File uses @@ hunks with +, -, and space context lines. "
            "You can append anchor text after @@ header (for example: @@ -10,2 +10,2 @@ def foo():). "
            "When anchor text exists, it must match the line pointed by @@ old_start after previous hunks offset; mismatch returns an error. "
            "Returns changed files or detailed hunk error when context does not match. "
            "Example: *** Begin Patch | *** Update File: src/app.py | @@ -1,1 +1,1 @@ | -old_line | +new_line | *** End Patch"
        ),
        parameters_model=ApplyPatchParameters,
    )
    async def apply_patch(patch: str) -> str:
        try:
            operations = _parse_patch_operations(patch)
        except ValueError as exc:
            return f"执行失败: patch 结构非法: {exc}"

        planned_accesses: set[tuple[str, Path]] = set()
        for operation in operations:
            source_path = _resolve_target_path(operation.path, workspace_root)
            if operation.kind == "add":
                planned_accesses.add(("write", source_path))
            elif operation.kind == "delete":
                planned_accesses.add(("write", source_path))
            elif operation.kind == "update":
                planned_accesses.add(("read", source_path))
                planned_accesses.add(("write", source_path))
            if operation.move_to is not None:
                planned_accesses.add(("write", _resolve_target_path(operation.move_to, workspace_root)))

        for mode, path in sorted(planned_accesses, key=lambda item: (str(item[1]), item[0])):
            allowed = await _check_path_permission(registry, mode, path, workspace_root)
            if not allowed:
                return (
                    "执行失败: apply_patch 未获授权访问路径。\n"
                    f"mode: {mode}\n"
                    f"target: {path}"
                )

        changed: list[str] = []
        for operation in operations:
            source = _resolve_target_path(operation.path, workspace_root)

            if operation.kind == "add":
                if source.exists():
                    return f"执行失败: Add File 目标已存在 {operation.path}"
                source.parent.mkdir(parents=True, exist_ok=True)
                content = "\n".join(operation.lines)
                if operation.lines:
                    content += "\n"
                source.write_text(content, "utf-8")
                changed.append(operation.path)
                continue

            if operation.kind == "delete":
                if not source.exists():
                    return f"执行失败: Delete File 目标不存在 {operation.path}"
                if source.is_dir():
                    return f"执行失败: Delete File 目标是目录 {operation.path}"
                source.unlink()
                changed.append(operation.path)
                continue

            if operation.kind == "update":
                if not source.exists():
                    return f"执行失败: Update File 目标不存在 {operation.path}"
                if source.is_dir():
                    return f"执行失败: Update File 目标是目录 {operation.path}"
                try:
                    _validate_update_lines(operation.path, operation.lines)
                except ValueError as exc:
                    return f"执行失败: {exc}"
                old_content = source.read_text("utf-8")
                try:
                    new_content = _apply_update_hunks(old_content, operation.lines, operation.path)
                except ValueError as exc:
                    return f"执行失败: {exc}"
                target_path = source
                if operation.move_to is not None:
                    target_path = _resolve_target_path(operation.move_to, workspace_root)
                if new_content != old_content or target_path != source:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    target_path.write_text(new_content, "utf-8")
                    if target_path != source:
                        source.unlink()
                        changed.append(f"{operation.path} -> {operation.move_to}")
                    else:
                        changed.append(operation.path)
                continue

            return f"执行失败: 未知操作类型 {operation.kind}"

        if not changed:
            return "执行完成: 无文件变更"
        rendered = "\n".join(f"- {item}" for item in changed)
        return f"执行成功: 已处理 {len(changed)} 项变更\n{rendered}"
