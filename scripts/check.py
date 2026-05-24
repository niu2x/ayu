#!/usr/bin/env python3
"""运行项目中 AGENTS.md 中定义的全部检查"""

import glob
import subprocess
import sys
from pathlib import Path

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

results: list[tuple[str, str, str]] = []


def run(
    name: str,
    description: str,
    cmd: list[str],
    cwd: str | None = None,
    skip_on_error: bool = False,
) -> None:
    print(f"  [{name}] {description}...", end=" ", flush=True)
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd or PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode == 0:
            print(f"{PASS}")
            results.append((name, PASS, ""))
        else:
            if skip_on_error:
                print(f"{SKIP}")
                results.append((name, SKIP, proc.stdout + proc.stderr))
            else:
                print(f"{FAIL}")
                results.append((name, FAIL, proc.stdout + proc.stderr))
    except FileNotFoundError as e:
        print(f"{FAIL} (command not found: {e})")
        results.append((name, FAIL, str(e)))
    except subprocess.TimeoutExpired:
        print(f"{FAIL} (timeout)")
        results.append((name, FAIL, "timeout"))


PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)

print("=" * 60)
print("  ayu 项目检查清单")
print("=" * 60)
print()

# 1. 语法检查
run("syntax", "语法检查（py_compile）", ["uv", "run", "python", "-m", "py_compile", "src/ayu/cli.py"])
run("syntax", "语法检查（py_compile）", ["uv", "run", "python", "-m", "py_compile", "src/ayu/config.py"])
run("syntax", "语法检查（py_compile）", ["uv", "run", "python", "-m", "py_compile", "src/ayu/tui_app.py"])
run("syntax", "语法检查（py_compile）", ["uv", "run", "python", "-m", "py_compile", "src/ayu/server.py"])
run("syntax", "语法检查（py_compile）", ["uv", "run", "python", "-m", "py_compile", "src/ayu/llm.py"])

print()

# 2. import 验证
run("import", "模块导入验证", ["uv", "run", "python", "-c", "import ayu; print('ok')"])

print()

# 3. ruff 检查（含类型注解和通用规则）
run("ruff", "ruff 静态分析（通用规则）", ["uv", "run", "ruff", "check", "src/ayu/"])
run("ruff-ann", "ruff 类型注解检查（ANN）", ["uv", "run", "ruff", "check", "--select", "ANN", "src/ayu/"])

print()

# 4. 类型注解检查 — 用 ruff ANN 规则替代手工 grep
# （在 ruff 阶段已执行 --select ANN）

print()

# 5. Pydantic 合规 - 检查是否用了 dataclass 或 TypedDict
print("  [pydantic] Pydantic v2 合规检查...")
pydantic_errors: list[str] = []
for pyfile in glob.glob("src/ayu/**/*.py", recursive=True):
    with open(pyfile) as f:
        content = f.read()
        if "from dataclasses import" in content or "import dataclass" in content:
            pydantic_errors.append(f"  {pyfile}: 使用了 dataclass 而非 BaseModel")
        if "from typing import TypedDict" in content or "TypedDict" in content:
            pydantic_errors.append(f"  {pyfile}: 使用了 TypedDict 而非 BaseModel")

if pydantic_errors:
    print(f"{FAIL}")
    for err in pydantic_errors:
        print(err)
    results.append(("pydantic", FAIL, "\n".join(pydantic_errors)))
else:
    print(f"{PASS}")
    results.append(("pydantic", PASS, ""))

print()

# 6. 功能验证
run("cli", "CLI --help", ["uv", "run", "ayu", "--help"])

print()

# 7. 单元测试
run("test", "单元测试", ["uv", "run", "pytest"])

print()
print("=" * 60)
print("  检查结果汇总")
print("=" * 60)

all_pass = True
has_fail = False
for name, status, detail in results:
    if status == FAIL:
        print(f"  [{name:10}] ❌ {status}")
        all_pass = False
        has_fail = True
    elif status == SKIP:
        print(f"  [{name:10}] ⚠️  {status}")
    else:
        print(f"  [{name:10}] ✅ {status}")

print()
if all_pass:
    print("  🎉 全部通过！")
    sys.exit(0)
else:
    print("  ❌ 存在失败的检查项，请修复后重试")
    sys.exit(1)
