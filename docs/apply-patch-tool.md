# apply_patch 工具维护文档

## 概述

`apply_patch` 是 ayu 的 Agent 文件编辑工具，支持两种输入格式和 4 种文件操作。核心实现在 `src/ayu/tooling/apply_patch_tool.py`。

## 输入格式

### 1. 传统格式（保持向后兼容）

```
*** Begin Patch
*** Add File: path/to/new.py
+content line 1
+content line 2
*** Update File: path/to/existing.py
*** Move to: path/to/renamed.py   (可选)
@@ -1,2 +1,3 @@
 context
-old
+new
+extra
*** Delete File: path/to/obsolete.py
*** Rename File: old.py -> new.py
*** End Patch
```

### 2. 标准 unified diff 格式（新）

```diff
--- a/src/app.py
+++ b/src/app.py
@@ -10,3 +10,4 @@
 context
-old
+new
+extra
```

支持 `--- /dev/null`（新建文件）和 `+++ /dev/null`（删除文件）语义。

## 操作类型

| 操作 | 传统格式指令 | 说明 |
|------|-------------|------|
| Add | `*** Add File: path` | 新建文件，行前 `+` 为内容 |
| Update | `*** Update File: path` | 修改文件，`@@` hunk 驱动 |
| Delete | `*** Delete File: path` | 删除文件 |
| Rename | `*** Rename File: old -> new` | 独立重命名（不修改内容） |
| Move (附在 Update 后) | `*** Move to: path` | Update 后移动文件到新路径 |

## 关键改进

### 1. 缩进匹配宽松化（Fixes #1）

`_norm_trailing()` 在 hunk 上下文对比前对每行做 `rstrip()`，消除行尾空格差异导致的误判。

### 2. 锚点文本柔性匹配（Fixes #2）

流程：
1. 先按 `old_start - 1 + line_offset` 精确位置匹配
2. 若失败，在 ±5 行范围内搜索锚点文本
3. 都失败则跳过该 hunk（不阻塞后续 hunk）

### 3. 标准 diff 格式（Fixes #3）

`_parse_patch_operations()` 根据首行自动区分格式：以 `--- ` 开头走 `_parse_standard_diff()`，否则走 `_parse_legacy_format()`。

### 4. 部分 hunk 应用（Fixes #4）

`_apply_update_hunks()` 返回 `(new_content, errors[])`。`_apply_operations()` 收到 errors 时：
- 如果内容有变化，写入文件
- 返回 `"执行完成（部分 hunk 失败）"` + 具体错误，不阻止文件写入

### 5. Dry-run 模式（Fixes #5）

`ApplyPatchParameters.dry_run: bool`，默认 `False`。开启后：
- 跳过所有文件写入/删除/重命名
- 输出 `[dry-run]` 前缀的变更摘要（含行数统计）

### 6. 独立 Rename 指令（Fixes #6）

`*** Rename File: old -> new` 作为独立操作类型，不依赖 Update。底层调用 `Path.rename()`。

## Hunk 处理流程

```
_apply_update_hunks()
  │
  ├── 逐行扫描 → 找到 @@ header
  ├── 解析 old_start, anchor_text
  ├── 收集 hunk_deletes (- 行 + 空格行) 和 hunk_adds (+ 行 + 空格行)
  │
  ├── 锚点文本检查（精确→模糊±5行）
  ├── _apply_hunk()
  │     ├── 纯插入（无 delete）：old_start + line_offset 定位插入点
  │     └── 替换：_match_hunk_deletes() 在 original_lines 中搜索（rstrip 对比）
  │
  ├── 成功 → line_offset += applied_lines
  └── 失败 → errors.append(message), 继续下一个 hunk
```

`line_offset` 跨 hunk 累计：`+= len(hunk_adds) - len(hunk_deletes)`。

## 权限模型

所有操作批量检查权限后再执行。对每个操作的源/目标路径，判断是否在工作区内：
- 工作区内：自动允许
- 工作区外：通过 `ToolRegistry.request_permission()` 回调让用户授权

## 回归测试要点

- `test_apply_patch_add_update_delete_file` — 基础增删改
- `test_apply_patch_move_file` — Update + Move to
- `test_apply_patch_insert_by_hunk_position` — `@@ -N,0 +N,1 @@` 纯插入
- `test_apply_patch_hunk_error_contains_detail` — hunk 未命中时返回「部分 hunk 失败」
- `test_apply_patch_anchor_text_*` — 锚点文本匹配/缺失/越界/重复行场景
- 标准 unified diff 格式测试（TODO）
- dry_run 模式测试（TODO）
- Rename File 测试（TODO）
