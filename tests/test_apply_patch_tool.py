import json
from pathlib import Path

import pytest

from ayu.tools import PermissionRequest, build_default_tool_registry
from ayu.tooling.run_shell_tool import _extract_command_path_accesses, _split_commands


@pytest.mark.asyncio
async def test_apply_patch_add_update_delete_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    registry = build_default_tool_registry()

    add_patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Add File: notes.txt",
            "+line1",
            "+line2",
            "*** End Patch",
        ]
    )
    add_result = await registry.execute("apply_patch", json.dumps({"patch": add_patch}))
    assert "执行成功" in add_result
    assert (tmp_path / "notes.txt").read_text("utf-8") == "line1\nline2\n"

    update_patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: notes.txt",
            "@@ -2,1 +2,1 @@",
            "-line2",
            "+line2-updated",
            "*** End Patch",
        ]
    )
    update_result = await registry.execute("apply_patch", json.dumps({"patch": update_patch}))
    assert "执行成功" in update_result
    assert (tmp_path / "notes.txt").read_text("utf-8") == "line1\nline2-updated\n"

    delete_patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Delete File: notes.txt",
            "*** End Patch",
        ]
    )
    delete_result = await registry.execute("apply_patch", json.dumps({"patch": delete_patch}))
    assert "执行成功" in delete_result
    assert not (tmp_path / "notes.txt").exists()


@pytest.mark.asyncio
async def test_apply_patch_move_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "src.txt"
    source.write_text("hello\n", "utf-8")

    registry = build_default_tool_registry()
    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: src.txt",
            "*** Move to: moved/dst.txt",
            "@@ -1,1 +1,1 @@",
            "-hello",
            "+world",
            "*** End Patch",
        ]
    )
    result = await registry.execute("apply_patch", json.dumps({"patch": patch}))
    assert "执行成功" in result
    assert not source.exists()
    assert (tmp_path / "moved" / "dst.txt").read_text("utf-8") == "world\n"


@pytest.mark.asyncio
async def test_apply_patch_insert_by_hunk_position(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "sample.txt"
    target.write_text("a\nb\n", "utf-8")

    registry = build_default_tool_registry()
    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: sample.txt",
            "@@ -2,0 +2,1 @@",
            "+x",
            "*** End Patch",
        ]
    )
    result = await registry.execute("apply_patch", json.dumps({"patch": patch}))
    assert "执行成功" in result
    assert target.read_text("utf-8") == "a\nx\nb\n"


@pytest.mark.asyncio
async def test_apply_patch_hunk_error_contains_detail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "bad.txt"
    target.write_text("a\nb\n", "utf-8")

    registry = build_default_tool_registry()
    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: bad.txt",
            "@@ -10,1 +10,1 @@",
            "-not-found",
            "+replaced",
            "*** End Patch",
        ]
    )
    result = await registry.execute("apply_patch", json.dumps({"patch": patch}))
    assert "执行失败" in result
    assert "第 1 个 hunk" in result
    assert "未命中上下文" in result


@pytest.mark.asyncio
async def test_apply_patch_anchor_text_match_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "anchor.txt"
    target.write_text("def foo():\n    old\n", "utf-8")

    registry = build_default_tool_registry()
    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: anchor.txt",
            "@@ -1,2 +1,2 @@ def foo():",
            " def foo():",
            "-    old",
            "+    new",
            "*** End Patch",
        ]
    )
    result = await registry.execute("apply_patch", json.dumps({"patch": patch}))
    assert "执行成功" in result
    assert target.read_text("utf-8") == "def foo():\n    new\n"


@pytest.mark.asyncio
async def test_apply_patch_anchor_text_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "anchor-miss.txt"
    target.write_text("def bar():\n    old\n", "utf-8")

    registry = build_default_tool_registry()
    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: anchor-miss.txt",
            "@@ -1,2 +1,2 @@ def foo():",
            " def bar():",
            "-    old",
            "+    new",
            "*** End Patch",
        ]
    )
    result = await registry.execute("apply_patch", json.dumps({"patch": patch}))
    assert "锚点与行号不匹配" in result


@pytest.mark.asyncio
async def test_apply_patch_anchor_text_with_duplicate_lines_by_position(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "anchor-multi.txt"
    target.write_text("def foo():\n    old1\ndef foo():\n    old2\n", "utf-8")

    registry = build_default_tool_registry()
    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: anchor-multi.txt",
            "@@ -1,2 +1,2 @@ def foo():",
            " def foo():",
            "-    old1",
            "+    new1",
            "*** End Patch",
        ]
    )
    result = await registry.execute("apply_patch", json.dumps({"patch": patch}))
    assert "执行成功" in result
    assert target.read_text("utf-8") == "def foo():\n    new1\ndef foo():\n    old2\n"


@pytest.mark.asyncio
async def test_apply_patch_anchor_text_line_out_of_range(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "anchor-range.txt"
    target.write_text("line1\n", "utf-8")

    registry = build_default_tool_registry()
    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: anchor-range.txt",
            "@@ -5,0 +5,1 @@ line5",
            "+new",
            "*** End Patch",
        ]
    )
    result = await registry.execute("apply_patch", json.dumps({"patch": patch}))
    assert "锚点行号越界" in result


@pytest.mark.asyncio
async def test_apply_patch_outside_workspace_requires_permission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside\n", "utf-8")

    registry = build_default_tool_registry()

    async def deny_permission(request: PermissionRequest) -> str:
        assert request.action == "apply_patch"
        return "deny"

    registry.set_permission_handler(deny_permission)
    patch = "\n".join(
        [
            "*** Begin Patch",
            f"*** Update File: {outside}",
            "@@ -1,1 +1,1 @@",
            "-outside",
            "+outside-updated",
            "*** End Patch",
        ]
    )
    result = await registry.execute("apply_patch", json.dumps({"patch": patch}))
    assert "未获授权" in result
    assert outside.read_text("utf-8") == "outside\n"


def test_split_shell_commands() -> None:
    assert _split_commands("git status && git diff -- src") == ["git status", "git diff -- src"]
    assert _split_commands("  cd a &&   ls  ") == ["cd a", "ls"]


def test_extract_command_path_accesses_with_redirect(tmp_path: Path) -> None:
    workspace = tmp_path.resolve()
    cwd = workspace
    accesses, next_cwd, recognized = _extract_command_path_accesses("cat a.txt > out.txt", cwd, workspace)
    assert next_cwd == cwd
    assert recognized
    assert {(item.mode, item.path) for item in accesses} == {
        ("read", workspace / "a.txt"),
        ("write", workspace / "out.txt"),
    }


def test_extract_command_path_accesses_mv_write_write(tmp_path: Path) -> None:
    workspace = tmp_path.resolve()
    cwd = workspace
    accesses, _, recognized = _extract_command_path_accesses("mv old.txt new.txt", cwd, workspace)
    assert recognized
    assert {(item.mode, item.path) for item in accesses} == {
        ("write", workspace / "old.txt"),
        ("write", workspace / "new.txt"),
    }


def test_extract_command_path_accesses_unknown_command(tmp_path: Path) -> None:
    workspace = tmp_path.resolve()
    cwd = workspace
    accesses, next_cwd, recognized = _extract_command_path_accesses("unknown_tool arg", cwd, workspace)
    assert accesses == []
    assert next_cwd == cwd
    assert not recognized


def test_extract_command_path_accesses_grep(tmp_path: Path) -> None:
    workspace = tmp_path.resolve()
    cwd = workspace
    accesses, next_cwd, recognized = _extract_command_path_accesses("grep foo a.txt b.txt", cwd, workspace)
    assert recognized
    assert next_cwd == cwd
    assert {(item.mode, item.path) for item in accesses} == {
        ("read", workspace / "a.txt"),
        ("read", workspace / "b.txt"),
    }


def test_extract_command_path_accesses_git_commit(tmp_path: Path) -> None:
    workspace = tmp_path.resolve()
    cwd = workspace
    accesses, next_cwd, recognized = _extract_command_path_accesses("git commit -m test", cwd, workspace)
    assert recognized
    assert next_cwd == cwd
    assert {(item.mode, item.path) for item in accesses} == {
        ("write", workspace),
    }


def test_extract_command_path_accesses_git_log(tmp_path: Path) -> None:
    workspace = tmp_path.resolve()
    cwd = workspace
    accesses, next_cwd, recognized = _extract_command_path_accesses("git log --oneline -5", cwd, workspace)
    assert recognized
    assert next_cwd == cwd
    assert {(item.mode, item.path) for item in accesses} == {
        ("read", workspace),
    }


def test_extract_command_path_accesses_git_add(tmp_path: Path) -> None:
    workspace = tmp_path.resolve()
    cwd = workspace
    accesses, next_cwd, recognized = _extract_command_path_accesses("git add .", cwd, workspace)
    assert recognized
    assert next_cwd == cwd
    assert {(item.mode, item.path) for item in accesses} == {
        ("write", workspace),
    }


def test_extract_command_path_accesses_find(tmp_path: Path) -> None:
    workspace = tmp_path.resolve()
    cwd = workspace

    accesses, next_cwd, recognized = _extract_command_path_accesses("find src tests -name '*.py'", cwd, workspace)
    assert recognized
    assert next_cwd == cwd
    assert {(item.mode, item.path) for item in accesses} == {
        ("read", workspace / "src"),
        ("read", workspace / "tests"),
    }

    accesses_default, _, recognized_default = _extract_command_path_accesses("find -name '*.py'", cwd, workspace)
    assert recognized_default
    assert {(item.mode, item.path) for item in accesses_default} == {
        ("read", workspace),
    }


@pytest.mark.asyncio
async def test_run_shell_combined_command_requires_all_permissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    outside_output = tmp_path.parent / "out.txt"
    (tmp_path / "a.txt").write_text("a\n", "utf-8")
    registry = build_default_tool_registry()

    requested_keys: list[str] = []

    async def handler(request: PermissionRequest) -> str:
        requested_keys.append(request.key)
        if request.key == f"write::{outside_output}":
            return "deny"
        return "allow_once"

    registry.set_permission_handler(handler)
    result = await registry.execute(
        "run_shell",
        json.dumps({"command": f"cat a.txt > {outside_output} && git status"}),
    )
    assert "未授权" in result
    assert f"write::{outside_output}" in requested_keys


@pytest.mark.asyncio
async def test_run_shell_unknown_command_fallback_hash_permission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    registry = build_default_tool_registry()

    requested: list[str] = []

    async def handler(request: PermissionRequest) -> str:
        requested.append(request.key)
        if request.key.startswith("shell::"):
            return "deny"
        return "allow_once"

    registry.set_permission_handler(handler)
    result = await registry.execute(
        "run_shell",
        json.dumps({"command": "unknown_cmd arg1"}),
    )
    assert "整条命令授权" in result
    assert any(item.startswith("shell::") for item in requested)
