from pathlib import Path
import re
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from ayu.tooling.permission_actions import APPLY_PATCH_ACTION


class ApplyPatchParameters(BaseModel):
    patch: str
    dry_run: bool = False


class ToolRegistryLike(Protocol):
    def register(self, *args: object, **kwargs: object) -> object: ...

    async def request_permission(self, request: object) -> bool: ...


def _norm_trailing(line: str) -> str:
    return line.rstrip()


class PatchOperation(BaseModel):
    kind: Literal["add", "update", "delete", "rename"]
    path: str
    move_to: str | None = None
    lines: list[str] = Field(default_factory=list)


def _resolve_target_path(path: str, workspace_root: Path) -> Path:
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = workspace_root / target
    return target.resolve()


# ── 解析器 ──────────────────────────────────────────────

def _parse_patch_operations(patch: str) -> list[PatchOperation]:
    lines = patch.splitlines()
    if not lines:
        raise ValueError("patch 为空")
    if lines[0].startswith("--- "):
        return _parse_standard_diff(lines)
    return _parse_legacy_format(lines)


def _parse_legacy_format(lines: list[str]) -> list[PatchOperation]:
    if lines[0] != "*** Begin Patch":
        raise ValueError("patch 首行必须是 *** Begin Patch")
    if lines[-1] != "*** End Patch":
        raise ValueError("patch 末行必须是 *** End Patch")

    operations: list[PatchOperation] = []
    index = 1
    while index < len(lines) - 1:
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        if line.startswith("*** Add File: "):
            path = line.removeprefix("*** Add File: ").strip()
            index += 1
            content_lines: list[str] = []
            while index < len(lines) - 1 and not lines[index].startswith("*** "):
                current = lines[index]
                if current.startswith("+"):
                    content_lines.append(current[1:])
                elif current.startswith(" "):
                    content_lines.append(current[1:])
                else:
                    raise ValueError(f"Add File {path} 中存在非法行: {current}")
                index += 1
            operations.append(PatchOperation(kind="add", path=path, lines=content_lines))
            continue

        if line.startswith("*** Delete File: "):
            path = line.removeprefix("*** Delete File: ").strip()
            operations.append(PatchOperation(kind="delete", path=path))
            index += 1
            continue

        if line.startswith("*** Rename File: "):
            rest = line.removeprefix("*** Rename File: ").strip()
            if " -> " not in rest:
                raise ValueError(f"Rename File 格式错误，需要 'old -> new': {rest}")
            old_path, new_path = rest.split(" -> ", 1)
            operations.append(PatchOperation(kind="rename", path=old_path.strip(), move_to=new_path.strip()))
            index += 1
            continue

        if line.startswith("*** Update File: "):
            path = line.removeprefix("*** Update File: ").strip()
            index += 1
            move_to: str | None = None
            if index < len(lines) - 1 and lines[index].startswith("*** Move to: "):
                move_to = lines[index].removeprefix("*** Move to: ").strip()
                index += 1
            body_lines: list[str] = []
            while index < len(lines) - 1 and not lines[index].startswith("*** "):
                body_lines.append(lines[index])
                index += 1
            operations.append(PatchOperation(kind="update", path=path, move_to=move_to, lines=body_lines))
            continue

        raise ValueError(f"未知 patch 指令: {line}")

    if not operations:
        raise ValueError("patch 中没有可执行操作")
    return operations


def _parse_standard_diff(lines: list[str]) -> list[PatchOperation]:
    operations: list[PatchOperation] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        if line.startswith("--- "):
            old_path = line.removeprefix("--- ").strip()
            i += 1
            if i >= len(lines) or not lines[i].startswith("+++ "):
                raise ValueError(f"标准 diff 格式错误：缺少 +++ 行（--- {old_path} 之后）")
            new_path = lines[i].removeprefix("+++ ").strip()
            i += 1

            if old_path == "/dev/null":
                kind = "add"
                path = new_path
            elif new_path == "/dev/null":
                kind = "delete"
                path = old_path
            else:
                kind = "update"
                path = new_path if new_path != "/dev/null" else old_path

            if kind == "delete":
                operations.append(PatchOperation(kind="delete", path=old_path))
                continue

            body_lines: list[str] = []
            while i < len(lines):
                if lines[i].startswith("--- ") or not lines[i].strip():
                    if i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
                        break
                if lines[i].startswith("--- ") or lines[i].startswith("diff "):
                    break
                body_lines.append(lines[i])
                i += 1

            if kind == "add":
                ops = _parse_add_from_standard(body_lines, path)
                operations.extend(ops)
            else:
                operations.append(PatchOperation(kind="update", path=path, lines=body_lines))
        else:
            i += 1

    if not operations:
        raise ValueError("标准 diff 中没有可执行操作")
    return operations


def _parse_add_from_standard(body_lines: list[str], path: str) -> list[PatchOperation]:
    content_lines: list[str] = []
    for line in body_lines:
        if line.startswith("+") and not line.startswith("+++"):
            content_lines.append(line[1:])
    if not content_lines:
        raise ValueError(f"标准 diff Add File {path} 没有内容行")
    return [PatchOperation(kind="add", path=path, lines=content_lines)]


# ── hunk 校验 ───────────────────────────────────────────

def _validate_update_lines(path: str, lines: list[str]) -> None:
    if not lines:
        raise ValueError(f"Update File {path} 缺少 hunk 内容")
    has_hunk = False
    for line in lines:
        if line.startswith("@@"):
            has_hunk = True
            continue
        if not line or line.startswith(("+", "-", " ")):
            continue
        raise ValueError(f"Update File {path} 包含非法 hunk 行: {line}")
    if not has_hunk:
        raise ValueError(f"Update File {path} 缺少 @@ hunk 头")


# ── hunk 应用 ───────────────────────────────────────────

class HunkResult(BaseModel):
    success: bool
    message: str = ""
    applied_lines: int = 0


def _match_hunk_deletes(
    original_lines: list[str],
    hunk_deletes: list[str],
    search_start: int,
) -> int:
    search_limit = len(original_lines) - len(hunk_deletes) + 1
    for i in range(max(search_start, 0), max(search_limit, 0)):
        match = True
        for j, delete_line in enumerate(hunk_deletes):
            orig_line = original_lines[i + j]
            if _norm_trailing(orig_line) != _norm_trailing(delete_line):
                match = False
                break
        if match:
            return i
    return -1


def _apply_hunk(
    original_lines: list[str],
    hunk_deletes: list[str],
    hunk_adds: list[str],
    hunk_number: int,
    path: str,
    header: str,
    anchor_index: int | None,
    old_start: int = 1,
    line_offset: int = 0,
) -> HunkResult:
    if not hunk_deletes and not hunk_adds:
        return HunkResult(success=False, message=f"第 {hunk_number} 个 hunk 为空: {header}")

    if not hunk_deletes:
        if anchor_index is not None:
            insert_at = anchor_index + 1
        else:
            insert_at = old_start - 1 + line_offset
        insert_at = max(0, min(insert_at, len(original_lines)))
        original_lines[insert_at:insert_at] = hunk_adds
        return HunkResult(success=True, applied_lines=len(hunk_adds))

    search_start = anchor_index if anchor_index is not None else 0
    found_at = _match_hunk_deletes(original_lines, hunk_deletes, search_start)

    if found_at < 0:
        snippet = "\\n".join(hunk_deletes[:5])
        return HunkResult(
            success=False,
            message=(
                f"第 {hunk_number} 个 hunk 未命中上下文。"
                f"hunk 头: {header}; 期望片段: {snippet}"
            ),
        )

    original_lines[found_at : found_at + len(hunk_deletes)] = hunk_adds
    return HunkResult(success=True, applied_lines=len(hunk_adds) - len(hunk_deletes))


def _apply_update_hunks(content: str, lines: list[str], path: str) -> tuple[str, list[str]]:
    original_lines = content.splitlines()
    has_trailing_newline = content.endswith("\n")
    index = 0
    line_offset = 0
    hunk_number = 0
    errors: list[str] = []

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
            errors.append(f"第 {hunk_number} 个 hunk 头非法: {header}")
            index += 1
            continue
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
                context = current[1:]
                hunk_deletes.append(context)
                hunk_adds.append(context)
            elif not current:
                pass
            else:
                errors.append(f"第 {hunk_number} 个 hunk 存在非法行: {current}")
                break
            index += 1

        if not hunk_deletes and not hunk_adds:
            errors.append(f"第 {hunk_number} 个 hunk 为空: {header}")
            continue

        anchor_index: int | None = None
        effective_line = old_start - 1 + line_offset
        if anchor_text:
            if 0 <= effective_line < len(original_lines):
                actual_anchor_line = original_lines[effective_line].strip()
                if actual_anchor_line == anchor_text:
                    anchor_index = effective_line
                else:
                    found_anchor = False
                    search_radius = 5
                    for offset in range(-search_radius, search_radius + 1):
                        check = effective_line + offset
                        if 0 <= check < len(original_lines):
                            if original_lines[check].strip() == anchor_text:
                                anchor_index = check
                                found_anchor = True
                                break
                    if not found_anchor:
                        errors.append(
                            f"第 {hunk_number} 个 hunk 锚点文本 '{anchor_text}' 未在行 {effective_line + 1} 附近找到"
                        )
                        continue
            else:
                errors.append(f"第 {hunk_number} 个 hunk 锚点行号越界: line={old_start}, anchor={anchor_text}")
                continue

        result = _apply_hunk(
            original_lines,
            hunk_deletes,
            hunk_adds,
            hunk_number=hunk_number,
            path=path,
            header=header,
            anchor_index=anchor_index,
            old_start=old_start,
            line_offset=line_offset,
        )
        if result.success:
            line_offset += result.applied_lines
        else:
            errors.append(result.message)

    updated = "\n".join(original_lines)
    if has_trailing_newline:
        updated += "\n"
    return updated, errors


# ── 权限检查 ────────────────────────────────────────────

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


# ── 工具注册 ────────────────────────────────────────────

def _count_lines(text: str) -> int:
    return len(text.splitlines()) if text else 0


async def _apply_operations(
    operations: list[PatchOperation],
    workspace_root: Path,
    dry_run: bool,
) -> str:
    changed: list[str] = []
    for operation in operations:
        source = _resolve_target_path(operation.path, workspace_root)

        if operation.kind == "add":
            if source.exists():
                return f"执行失败: Add File 目标已存在 {operation.path}"
            content = "\n".join(operation.lines)
            if operation.lines:
                content += "\n"
            if dry_run:
                changed.append(f"[dry-run] + {operation.path} ({_count_lines(content)} 行)")
            else:
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text(content, "utf-8")
                changed.append(operation.path)
            continue

        if operation.kind == "delete":
            if not source.exists():
                return f"执行失败: Delete File 目标不存在 {operation.path}"
            if source.is_dir():
                return f"执行失败: Delete File 目标是目录 {operation.path}"
            if dry_run:
                old_lines = _count_lines(source.read_text("utf-8"))
                changed.append(f"[dry-run] - {operation.path} ({old_lines} 行)")
            else:
                source.unlink()
                changed.append(operation.path)
            continue

        if operation.kind == "rename":
            if not source.exists():
                return f"执行失败: Rename File 目标不存在 {operation.path}"
            target = _resolve_target_path(operation.move_to or "", workspace_root)
            if dry_run:
                changed.append(f"[dry-run] {operation.path} -> {operation.move_to}")
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                source.rename(target)
                changed.append(f"{operation.path} -> {operation.move_to}")
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
                new_content, errors = _apply_update_hunks(old_content, operation.lines, operation.path)
            except ValueError as exc:
                return f"执行失败: {exc}"

            if errors:
                errors_str = "; ".join(errors)
                if not dry_run and new_content != old_content:
                    target_path = source
                    if operation.move_to is not None:
                        target_path = _resolve_target_path(operation.move_to, workspace_root)
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    target_path.write_text(new_content, "utf-8")
                    if target_path != source:
                        source.unlink()
                    label = f"{operation.path} -> {operation.move_to}" if operation.move_to else operation.path
                    changed.append(label)
                return f"执行完成（部分 hunk 失败）: {errors_str}"

            target_path = source
            if operation.move_to is not None:
                target_path = _resolve_target_path(operation.move_to, workspace_root)

            if new_content != old_content or target_path != source:
                if dry_run:
                    old_line_count = _count_lines(old_content)
                    new_line_count = _count_lines(new_content)
                    delta = new_line_count - old_line_count
                    delta_str = f"+{delta}" if delta >= 0 else str(delta)
                    label = f"{operation.path} -> {operation.move_to}" if operation.move_to else operation.path
                    changed.append(f"[dry-run] ~ {label} ({old_line_count}→{new_line_count} 行, Δ{delta_str})")
                else:
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


def register_apply_patch_tool(registry: ToolRegistryLike, workspace_root: Path) -> None:
    @registry.register(
        name="apply_patch",
        description=(
            "Use this to edit files with structured patch text. "
            "Input must include *** Begin Patch and *** End Patch. "
            "Supported operations: *** Add File, *** Update File (optional *** Move to), "
            "*** Delete File, and *** Rename File. "
            "Also supports standard unified diff format (--- a/file, +++ b/file, @@ ... @@). "
            "Add File lines must start with '+'. Update File uses @@ hunks with +, -, and space context lines. "
            "You can append anchor text after @@ header (for example: @@ -10,2 +10,2 @@ def foo():). "
            "Anchor text is matched flexibly: it first tries the exact line number, then searches nearby lines. "
            "Returns changed files or detailed hunk error when context does not match. "
            "Dry-run mode: set dry_run=true to preview changes without writing. "
            "Example (legacy): *** Begin Patch | *** Update File: src/app.py | @@ -1,1 +1,1 @@ | -old_line | +new_line | *** End Patch. "
            "Example (unified): --- a/src/app.py | +++ b/src/app.py | @@ -1,1 +1,1 @@ | -old_line | +new_line"
        ),
        parameters_model=ApplyPatchParameters,
    )
    async def apply_patch(patch: str, dry_run: bool = False) -> str:
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
            elif operation.kind == "rename":
                planned_accesses.add(("write", source_path))
                if operation.move_to:
                    planned_accesses.add(("write", _resolve_target_path(operation.move_to, workspace_root)))
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

        return await _apply_operations(operations, workspace_root, dry_run)
