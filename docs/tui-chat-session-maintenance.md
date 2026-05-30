# Ayu TUI 斜杠命令面板维护说明

这份文档写给后续维护 `src/ayu/tui_app.py` 的同学，尽量用直白、可直接照着改的方式说明。

目标功能：

- 输入框首字符输入 `/` 时，显示命令候选面板。
- 支持上下箭头选择，回车选中并补全到输入框。
- 回车提交时，`/` 开头文本作为命令执行；普通文本走 LLM 聊天。
- 会话基于 `Session` 聚合多条消息，不再是每次请求单轮对话。
- LLM 响应使用 streaming 增量渲染到聊天区。
- streaming 使用结构化事件流：`reasoning` 与 `content` 分开渲染。
- 应用启动后会后台执行一次最小请求 warmup，降低首条真实消息的首包延迟。
- `/models` 命令可弹出模型列表并切换 `state.provider/state.model`。
- `/log` 命令可切换右侧日志侧栏，展示运行期 logger 输出。
- 不使用 Textual 默认 `ctrl+p` 命令面板（避免和自定义命令系统冲突）。

## 1. 核心结构

代码位置：`src/ayu/tui_app.py`

- `ChatPanel`：聊天消息滚动区。
- `AyuTUIApp`：主应用。
- `#chat-input`：主输入框。
- `#command-popup`：命令候选容器（输入框上方）。
- `#command-palette`：`OptionList` 命令列表。
- `#model-popup`：模型选择容器（居中弹出）。
- `#model-palette`：模型选择 `OptionList`。
- `#log-panel`：右侧日志面板（默认隐藏，可通过 `/log` 开关）。

新增模块：`src/ayu/session.py`

- `SessionMessage`：统一消息结构，支持 `system/user/assistant/tool`。
- `Session`：维护消息列表，并提供 `to_llm_messages()` 转换。

新增模块：`src/ayu/chat_runtime.py`

- `build_chat_runtime()`：构建 UI 无关的聊天运行时（config/state/session + LLM runtime 初始化）。
- `ChatRuntime`：统一承载 `config/state/session`，供 TUI/GUI/API 复用。

## 2. 为什么禁用默认命令面板

`AyuTUIApp` 里有两个关键类属性：

- `ENABLE_COMMAND_PALETTE = False`
- `COMMAND_PALETTE_DISPLAY = ""`

目的：

- 禁用 Textual 自带 `ctrl+p` 面板。
- 不显示与命令面板相关的 UI 提示。

注意：不要再把我们自己的命令字典命名成 `COMMANDS`。Textual `App` 里本身也使用 `COMMANDS` 语义，容易冲突。当前项目使用 `SLASH_COMMANDS`，这是正确做法。

## 3. 回调与职责（框架回调 + 业务方法）

### 3.1 框架回调

- `compose()`：组装页面组件。
- `on_mount()`：初始化配置、欢迎语、查询组件引用。
- `on_input_changed()`：输入变化时，判断是否展示命令候选。
- `on_input_submitted()`：回车提交，分流命令/普通消息。
- `on_option_list_option_selected()`：命令候选被选中后回填输入框。

### 3.2 业务方法

- `should_show_command_popup(value: str) -> bool`
  - 当前规则：`value.startswith("/") and value.strip() == value`
  - 含义：斜杠命令编辑态可见；带前后空格时不弹出。

- `show_command_popup(prefix: str)`
  - 根据前缀过滤 `SLASH_COMMANDS`，刷新 `OptionList`。

- `show_model_popup()`
  - 读取 `config.llm.providers` 下所有模型，渲染为 `provider/model` 列表。
  - 无模型时在聊天区给出提示。

- `toggle_log_panel()`
  - 切换日志面板显示状态。
  - 日志通过 `TUILogHandler` 写入 `LogPanel`。

- `fill_input_with_command(command: str)`
  - 选中命令后，写入 `command + COMMAND_SUFFIX`。
  - 默认 `COMMAND_SUFFIX = " "`，目的是：
    1) 用户可直接继续输入参数；
    2) 避免回填后再次触发面板重开。

- `action_command_up/down/select()` + `check_action(...)`
  - 仅在任一 `OptionList` 弹窗显示时接管上下/回车按键。
  - 其它动作必须回退 `super().check_action(...)`，否则会误伤全局快捷键。

- `on_option_list_option_selected(...)`
  - `command-palette`：回填 slash 命令。
  - `model-palette`：更新 `state.provider` / `state.model`，并 `save_state(...)`。

- `TUILogHandler.emit(...)`
  - 将 Python `logging` 记录转发到右侧日志面板。

- `ChatPanel.begin_stream_message(...)` / `update_stream_message(...)`
  - 先插入一条空的 ayu 消息，再随 chunk 增量更新文本，实现流式显示。

- `ChatPanel.begin_reasoning_message(...)` / `update_reasoning_message(...)`
  - 针对推理模型的思考内容单独渲染（`ayu thinking:`），与最终回答分离。

- `llm.chat_stream(...)`
  - 返回结构化事件：`{"type": "reasoning"|"content", "text": ...}`。
  - OpenAI 流中同时读取 `delta.content` 与 `delta.reasoning_content`（兼容 `reasoning` 字段）。

- `Session`
  - 运行时初始化时写入一条 `system` 消息（由 `src/ayu/system_prompt.py` 的 pipeline 生成）。
  - 用户发送时写入 `user` 消息。
  - 流式结束后写入 `assistant` 消息。
  - LLM 调用改为传入 `session.to_llm_messages()`，确保多轮上下文连续。

- `build_chat_runtime()`
  - 在 UI 层之外完成初始化：读取 config/state、创建 session、写入 system prompt、初始化 LLM runtime。
  - TUI 仅消费运行时对象，不负责初始化细节。

- `build_system_prompt()`（`src/ayu/system_prompt.py`）
  - system prompt 改为多段拼接 pipeline，而非单一常量。
  - 当前已接入环境片段：当前工作目录、是否 git 仓库、当前操作系统、当前时间。

- `ayu config path-log`（`src/ayu/cli.py`）
  - 用于输出日志目录路径（`PlatformDirs.user_log_dir`）。
  - 便于定位 TUI 文件日志 `ayu.log` 的实际落盘位置。

- `build_default_tool_registry()`（`src/ayu/tools.py`）
  - 注册默认工具：`write_file`、`read_file`、`feedback`、`run_shell`、`apply_patch`。
  - `read_file` 使用 `start_line` + `line_count` 读取。
  - 默认从第 1 行开始读取 200 行，`line_count` 最大 1000。
  - 返回内容统一带行号，便于后续基于行号继续编辑或复查。
  - `read_file` / `write_file` 默认直接执行；访问工作目录外路径时会触发授权回调并等待用户决策。
  - `read_file` / `write_file` 授权 key 统一为 `read::<abs_path>` / `write::<abs_path>`。
  - `feedback` 用于记录 agent 在执行中遇到的阻塞信息（如缺少工具、受限条件）。
  - `feedback` 支持 `category` 分类：`tool_missing` / `blocked` / `env_issue` / `general`。
  - `feedback` 会把意见追加到当前工作目录固定文件 `agent_feedback.md`。
  - `run_shell` 使用 asyncio + subprocess 执行命令，返回结构化 JSON（exit code/stdout/stderr/超时/耗时）。
  - `run_shell` 平台分支：Windows 走 PowerShell，Ubuntu/macOS 走 bash。
  - `run_shell` 会先拆分组合命令（如 `cmd1 && cmd2`），逐条提取读写路径（含 `<`、`>`、`>>`、`1>`、`2>` 重定向）。
  - 所有子命令的路径权限都通过后才执行；授权 key 统一为 `read::<abs_path>` / `write::<abs_path>`。
  - 当前内置识别示例：`git status/diff/log`（读目录）、`git commit`（写目录）、`cp`（读源写目标）、`mv`（写源写目标）等。
  - 若存在无法识别的子命令，会回退到整条命令 hash 授权（`shell::<sha256(command)>`）。
  - 特例：当有效目录为当前工作目录且命令是无重定向的 `git status` / `git diff` 时，视为只读命令，免授权执行。
  - 组合命令 `cd <dir> && git status|git diff` 也会识别，并以 `cd` 后目录作为有效目录判断。
  - 授权决策支持 `deny` / `allow_once` / `allow_session`，其中 `allow_session` 在本次会话内缓存。
  - `apply_patch` 支持结构化 patch：`*** Add File`、`*** Update File`、`*** Delete File`、`*** Move to`。
  - `apply_patch` 会对内部每个文件操作分别做路径权限检查，授权 key 同样使用 `read::<abs_path>` / `write::<abs_path>`。
  - `apply_patch` 内置结构校验和 hunk 精确报错（定位到第几个 hunk 与未命中上下文片段）。
  - `apply_patch` 支持 `Update File` 中纯 `+` hunk 按 `@@` 行号位置插入，不再仅依赖上下文替换。
  - `apply_patch` 支持在 `@@ ... @@` 后追加锚点文本；当存在锚点时，会校验 `@@` 行号位置对应文本是否匹配，不匹配会报错。

- `PermissionScreen`（`src/ayu/tui_app.py`）
  - 当工具请求权限时弹窗，让用户选择拒绝、允许一次或本会话一直允许。
  - TUI 在 `on_mount()` 中把 `request_permission` 回调注册到 `tool_registry`。
  - `PermissionRequest` 带 `target_kind`（`path`/`command`），弹窗会按类型显示“路径”或“命令”标签。

- `permission_actions.py`（`src/ayu/tooling/permission_actions.py`）
  - 统一定义权限动作常量（`read_file/write_file/run_shell`），避免字符串散落在各工具模块。

- `warmup_llm()` + `llm.warmup_stream()`
  - 启动后执行最小 `stream=True` 请求（`max_tokens=1`），仅用于预热连接与请求路径。
  - 预热失败只记录日志，不影响主聊天流程。

## 4. 常见坑位

### 4.1 `ctrl+p` 打开后报错 `TypeError: 'str' object is not callable`

通常是把业务命令表命名成了 `COMMANDS`，和 Textual 命令系统冲突。

修复：改名为 `SLASH_COMMANDS` 并全量替换引用。

### 4.2 上下箭头没效果

检查点：

- `BINDINGS` 是否包含 `up/down/enter` 对应 action。
- `check_action` 是否正确只在弹窗可见时放行。
- `OptionList` 是否在显示时设置了 `highlighted = 0`。

### 4.3 回车不能正常发送消息

通常是回车 binding 总是生效，抢走了输入框提交。

修复思路：`check_action` 对 `command_select` 返回 `self.command_popup.display`，弹窗关闭时不拦截回车。

### 4.4 流式返回没有输出

检查点：

- `llm.py` 是否走 `chat_stream(...)` 而非一次性 `chat(...)`。
- OpenAI 请求是否设置 `stream=True`。
- TUI 是否在 `async for chunk in chat_stream(...)` 中持续更新同一条消息组件。

### 4.5 DeepSeek 有 thinking 但界面不显示

检查点：

- 流式 chunk 中是否包含 `reasoning_content` 或 `reasoning`。
- `chat_stream(...)` 是否把 reasoning 字段转成 `type=reasoning` 事件。
- TUI 是否处理了 `reasoning` 事件并调用 `update_reasoning_message(...)`。

## 5. 后续扩展建议（低风险顺序）

1. 新增命令：只改 `SLASH_COMMANDS` + `handle_command`。
2. 支持参数提示：在 `show_command_popup` 增加参数说明行。
3. 增加 `Esc` 关闭候选框。
4. 命令拆分成独立模块：`src/ayu/commands.py`，减少 `tui_app.py` 体积。

## 6. 手工回归清单

每次改动命令相关逻辑，建议至少手测：

1. 输入 `/` 后，候选框出现在输入框附近。
2. `↑/↓` 有高亮变化，`Enter` 一次即可选中并关闭面板。
3. 回车在面板关闭时可正常发送消息。
4. `/help`、`/models`、`/quit` 行为正确。
5. `/models` 选中后，`state.json` 中 provider/model 已更新。
6. `/log` 可切换日志面板，且能看到请求开始/结束日志。
7. `uv run python scripts/check.py` 全部通过。
