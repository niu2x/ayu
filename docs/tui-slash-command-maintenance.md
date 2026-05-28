# Ayu TUI 斜杠命令面板维护说明

这份文档写给后续维护 `src/ayu/tui_app.py` 的同学，尽量用直白、可直接照着改的方式说明。

目标功能：

- 输入框首字符输入 `/` 时，显示命令候选面板。
- 支持上下箭头选择，回车选中并补全到输入框。
- 回车提交时，`/` 开头文本作为命令执行；普通文本走 LLM 聊天。
- `/models` 命令可弹出模型列表并切换 `state.provider/state.model`。
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
6. `uv run python scripts/check.py` 全部通过。
