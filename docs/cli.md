# CLI 命令维护说明

`src/ayu/cli.py` 是 typer 入口，负责路由所有 CLI 命令。

## 命令树

```
ayu               无参默认行为 → 启动 TUI
ayu chat "hello"  单次对话模式（不打开 TUI，不持久化，输出到 stdout）
ayu --api-key <key> --base-url <url> --model <name> chat "hello"  # 使用临时 provider
ayu --api-key <key> --base-url <url> --model <name>              # 使用临时 provider 启动 TUI
ayu serve         启动 FastAPI 服务
ayu config        config.json 管理
  show
  path
  set-provider
  remove-provider
  set-model
  remove-model
ayu state         state.json 管理
  show
  path
```

## 全局参数（--api-key / --base-url / --model）

这三个参数在 `main` callback 上定义，可用于 `ayu chat` 和无参 TUI 模式。

- 必须**同时使用**三个参数，缺少任一个会报错
- 注入到 `llm._runtime_override`，`initialize_runtime()` 检测到后会在 `_runtime_config.llm.providers` 中创建名为 `临时provider` 的临时配置
- 不在 `config.json` / `state.json` 中落盘，仅本次进程有效

### 实现

`cli.py` callback 在选项校验通过后调用 `llm.set_runtime_override(api_key, base_url, model)`，将值存入模块级 `_runtime_override`。

`llm.py` 的 `initialize_runtime()` 在加载完 config/state 后优先检查 `_runtime_override`：

1. 创建 `LLMProviderConfig`（api_style=openai，含单模型）
2. 写入 `_runtime_config.llm.providers["临时provider"]`
3. 设置 `_runtime_state.provider / .model`
4. 直接创建 `_runtime_client`

后续 `chat_stream()` / `_chat_openai_stream()` 无需任何改动，因为读取的是已被 injected 的 `_runtime_config` / `_runtime_state`。

## 单次对话模式（ayu chat "hello"）

### 触发条件

`chat` 是 app 下的一个标准子命令，接受必填位置参数 `message`。

- `ayu chat "hello"` → 调用 `chat` 命令 → `message="hello"` → 单次对话
- `ayu config show` → "config" 命中子命令 → 正常路由

### 实现流程

`_run_single_turn(message)` 是一个 `async` 函数，由 `asyncio.run()` 驱动：

1. 创建 `InMemoryBackend`（不写磁盘，进程退出即丢弃）
2. 调用 `build_chat_runtime(backend)` 构建完整 runtime（config/state/session/tool_registry）
3. 写入 system prompt（`build_system_prompt()`）+ user message
4. 调用 `chat_stream()` 流式对话，仅消费 `type="content"` 事件输出到 stdout
5. 结尾输出换行

### 设计要点

- **不持久化**：使用 `InMemoryBackend` 替代 `SqliteBackend`，进程退出后消息自动丢弃
- **不交互**：不给 `ToolRegistry` 注册权限回调，工具自动放行（`request_permission` 在没有 handler 时默认返回 `True`）
- **不打开 TUI**：全程在 CLI 进程内完成，不涉及 Textual 事件循环
- **完整工具链**：`build_chat_runtime()` 创建了完整的 `ToolRegistry`（含 `run_shell`/`read_file`/`write_file`/`apply_patch`/`feedback`），LLM 可以正常调用工具

### 与 TUI 的区别

| 特性 | TUI | 单次对话 |
|------|-----|----------|
| backend | SqliteBackend（持久化） | InMemoryBackend（内存） |
| 权限 | PermissionScreen 弹窗 | 自动放行 |
| 输出 | Textual 渲染 | stdout 流式 |
| 推理内容 | 展示 | 不展示 |
| 工具调用 | 独立 widget 展示 | 不展示 |
