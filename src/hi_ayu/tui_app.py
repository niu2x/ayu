import logging
from collections.abc import Sequence
from pathlib import Path
import sys
from typing import Literal

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from hi_ayu.llm import chat_stream, format_tool_display
from hi_ayu.config import DIRS
from hi_ayu.storage import StoredSession
from hi_ayu.tools import PermissionRequest


class ChatPanel(VerticalScroll):
    def add_message(self, role: str, content: str) -> None:
        if role == "you":
            self.mount(Static(content, classes="chat-message message-user"))
        else:
            self.mount(Markdown(content, classes="chat-message message-ai"))
        self.scroll_end(animate=False)

    def clear_messages(self) -> None:
        self.remove_children()
        self.scroll_end(animate=False)

    def begin_stream_message(self, role: str) -> Markdown:
        message = Markdown("", classes="chat-message message-ai")
        self.mount(message)
        self.scroll_end(animate=False)
        return message

    def begin_reasoning_message(self, role: str) -> Static:
        message = Static("", classes="chat-message")
        message.display = False
        self.mount(message)
        self.scroll_end(animate=False)
        return message

    def update_stream_message(self, message: Markdown, role: str, content: str) -> None:
        message.update(content)
        self.scroll_end(animate=False)

    def update_reasoning_message(self, message: Static, role: str, content: str) -> None:
        message.display = True
        safe = content.replace("[", r"\[")
        message.update(f"[dim]{safe}[/]")
        self.scroll_end(animate=False)


class LogPanel(VerticalScroll):
    def add_log(self, content: str) -> None:
        self.mount(Static(content))
        self.scroll_end(animate=False)


class TUILogHandler(logging.Handler):
    def __init__(self, app: "AyuTUIApp") -> None:
        super().__init__()
        self.app = app

    def emit(self, record: logging.LogRecord) -> None:
        self.app.log_to_panel(self.format(record))


class ModelPickerScreen(ModalScreen[str | None]):
    CSS = """
    ModelPickerScreen {
        align: center middle;
        background: transparent;
    }
    #model-popup {
        width: 70;
        height: auto;
        max-height: 20;
        border: round $primary;
        background: $surface;
    }
    #model-title {
        padding: 0 1;
    }
    #model-palette {
        height: auto;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, options: list[Option]) -> None:
        super().__init__()
        self.options = options

    def compose(self) -> ComposeResult:
        yield Container(
            Static("选择模型 (Esc 取消)", id="model-title"),
            OptionList(*self.options, id="model-palette"),
            id="model-popup",
        )

    def on_mount(self) -> None:
        palette = self.query_one("#model-palette", OptionList)
        palette.highlighted = 0
        palette.focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(str(event.option.id))


class PermissionScreen(ModalScreen[Literal["deny", "allow_once", "allow_session"]]):
    CSS = """
    PermissionScreen {
        align: center middle;
        background: transparent;
    }
    #permission-popup {
        width: 90;
        height: auto;
        border: round $warning;
        background: $surface;
        padding: 1;
    }
    #permission-title {
        text-style: bold;
        margin-bottom: 1;
    }
    #permission-target {
        margin-bottom: 1;
    }
    #permission-palette {
        height: auto;
    }
    """

    BINDINGS = [
        Binding("escape", "deny", "Deny", show=False),
    ]

    def __init__(self, request: PermissionRequest) -> None:
        super().__init__()
        self.request = request

    def compose(self) -> ComposeResult:
        action_text = f"授权请求: {self.request.action}"
        target_label = "路径" if self.request.target_kind == "path" else "命令"
        detail_text = (
            f"原因: {self.request.reason}\n"
            f"{target_label}: {self.request.target}\n"
            f"key: {self.request.key}"
        )
        options = [
            Option("拒绝", id="deny"),
            Option("允许一次", id="allow_once"),
            Option("本会话一直允许", id="allow_session"),
        ]
        yield Container(
            Static(action_text, id="permission-title"),
            Static(detail_text, id="permission-target"),
            OptionList(*options, id="permission-palette"),
            id="permission-popup",
        )

    def on_mount(self) -> None:
        palette = self.query_one("#permission-palette", OptionList)
        palette.highlighted = 0
        palette.focus()

    def action_deny(self) -> None:
        self.dismiss("deny")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = str(event.option.id)
        if option_id not in {"deny", "allow_once", "allow_session"}:
            self.dismiss("deny")
            return
        self.dismiss(option_id)


class SessionPickerScreen(ModalScreen[str | None]):
    CSS = """
    SessionPickerScreen {
        align: center middle;
        background: transparent;
    }
    #session-popup {
        width: 70;
        height: auto;
        max-height: 20;
        border: round $primary;
        background: $surface;
    }
    #session-title {
        padding: 0 1;
    }
    #session-palette {
        height: auto;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, sessions: Sequence[StoredSession]) -> None:
        super().__init__()
        options: list[Option] = [
            Option(
                session.title or session.id,
                id=session.id,
            )
            for session in sessions
        ]
        self.options = options

    def compose(self) -> ComposeResult:
        yield Container(
            Static("选择会话 (Esc 取消)", id="session-title"),
            OptionList(*self.options, id="session-palette"),
            id="session-popup",
        )

    def on_mount(self) -> None:
        palette = self.query_one("#session-palette", OptionList)
        palette.highlighted = 0
        palette.focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(str(event.option.id))


class AyuTUIApp(App):
    TITLE = "ayu"
    ALLOW_SELECT = False
    ENABLE_COMMAND_PALETTE = False
    COMMAND_PALETTE_DISPLAY = ""
    COMMAND_SUFFIX = " "
    BINDINGS = App.BINDINGS + [
        Binding("up", "command_up", "Command Up", priority=True),
        Binding("down", "command_down", "Command Down", priority=True),
        Binding("enter", "command_select", "Command Select", priority=True),
    ]
    SLASH_COMMANDS = {
        "/help": "显示可用命令",
        "/log": "切换日志侧栏",
        "/models": "选择当前模型",
        "/sessions": "切换会话",
        "/quit": "退出 ayu",
    }
    CSS = """
    Screen {
        layout: vertical;
    }
    #main-row {
        height: 1fr;
        margin: 1;
    }
    ChatPanel {
        border: solid $primary;
        width: 1fr;
        padding: 1;
    }
    .chat-message {
        margin: 0 0 2 0;
        padding: 0 1;
        width: 100%;
    }
    .message-user {
        background: $panel;
        text-style: bold;
        text-align: left;
        border-left: heavy $accent;
        padding: 0 1 0 2;
    }
    .message-ai {
        background: $surface;
        text-align: left;
    }
    .thinking-indicator {
        text-style: italic;
        color: $text-muted;
    }
    #log-panel {
        border: solid $accent;
        width: 45;
        padding: 1;
        display: none;
    }
    Input {
        margin: 0 1 1 1;
    }
    #ai-status {
        margin: 0 1 1 1;
        height: 1;
        text-style: italic;
        color: $text-muted;
    }
    #command-popup {
        margin: 0 1;
        height: auto;
        max-height: 8;
        border: round $primary;
        background: $surface;
        display: none;
    }
    #command-palette {
        height: auto;
    }
    .option-list--option-highlighted {
        background: $accent;
        color: $text;
    }
    """

    def compose(self) -> ComposeResult:
        yield Horizontal(
            ChatPanel(),
            LogPanel(id="log-panel"),
            id="main-row",
        )
        yield Container(OptionList(id="command-palette"), id="command-popup")
        yield Input(placeholder="Type a message and press Enter...", id="chat-input")
        yield Static("✓ 就绪", id="ai-status")
        yield Footer()

    async def on_mount(self) -> None:
        from hi_ayu.chat_runtime import build_chat_runtime
        from hi_ayu.storage import create_backend
        from hi_ayu.system_prompt import build_system_prompt

        backend = create_backend("sqlite")
        await backend.setup()
        self.runtime = build_chat_runtime(backend)
        self._session_persisted = False
        self.runtime.session.add_message("system", build_system_prompt())
        self.theme = self.runtime.state.theme
        chat = self.query_one(ChatPanel)
        welcome = "Hello! I'm ayu. How can I help you?"
        chat.add_message("ayu", welcome)
        self.query_one("#chat-input", Input).focus()
        self.log_panel = self.query_one("#log-panel", LogPanel)
        self.log_visible = False
        self.command_popup = self.query_one("#command-popup", Container)
        self.command_palette = self.query_one("#command-palette", OptionList)
        self.logger = logging.getLogger("ayu")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.log_handler = TUILogHandler(self)
        self.log_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
        log_dir = Path(DIRS.user_log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_dir / "ayu.log"), encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
        self.logger.handlers = [self.log_handler, stderr_handler, file_handler]
        self.logger.info("日志系统已初始化")
        self.runtime.tool_registry.set_permission_handler(self.request_permission)
        self._ai_working = False
        self.warmup_llm()

    async def _ensure_session_persisted(self) -> None:
        if self._session_persisted:
            return
        self._session_persisted = True
        from datetime import datetime
        from hi_ayu.storage import StoredMessage, StoredSession
        now = datetime.now().astimezone().isoformat(timespec="milliseconds")
        await self.runtime.backend.create_session(
            StoredSession(id=self.runtime.session.id, created_at=now, updated_at=now)
        )
        for msg in self.runtime.session.messages:
            if msg.role == "system":
                stored = StoredMessage(
                    id=msg.id, session_id=msg.session_id, event_ts=msg.event_ts,
                    role="system", content=msg.content,
                )
                await self.runtime.backend.append_message(stored)
                break

    def _set_ai_working(self, working: bool, usage: dict[str, object] | None = None) -> None:
        self._ai_working = working
        status = self.query_one("#ai-status", Static)
        msg_count = sum(1 for m in self.runtime.session.messages if m.role != "system") if self.runtime else 0
        if working:
            status.update(f"⏳ AI 正在工作...  [dim]({msg_count} 条消息)[/]")
        else:
            parts: list[str] = [f"{msg_count} 条消息"]
            if usage:
                total = usage.get("total_tokens")
                if total is not None:
                    parts.append(f"total={total}")
                details = usage.get("prompt_tokens_details")
                if isinstance(details, dict):
                    cached = details.get("cached_tokens", 0)
                    if isinstance(cached, (int, float)) and cached > 0:
                        prompt = usage.get("prompt_tokens", 0)
                        if isinstance(prompt, (int, float)) and prompt > 0:
                            pct = round(cached / prompt * 100)
                            parts.append(f"cached={pct}%")
            status.update(f"✓ 就绪  [dim]({' | '.join(parts)})[/]")

    async def request_permission(
        self,
        request: PermissionRequest,
    ) -> Literal["deny", "allow_once", "allow_session"]:
        self.logger.warning(f"等待用户授权: {request.action} -> {request.target}")
        decision = await self.push_screen_wait(PermissionScreen(request))
        if decision in {"deny", "allow_once", "allow_session"}:
            self.logger.info(f"用户授权结果: {decision} ({request.key})")
            return decision
        self.logger.info(f"用户授权结果: deny ({request.key})")
        return "deny"

    def log_to_panel(self, message: str) -> None:
        if hasattr(self, "log_panel"):
            self.log_panel.add_log(message)

    def toggle_log_panel(self) -> None:
        self.log_visible = not self.log_visible
        self.log_panel.display = self.log_visible

    def on_input_changed(self, event: Input.Changed) -> None:
        if self.should_show_command_popup(event.value):
            self.show_command_popup(event.value)
            return
        self.hide_command_popup()

    def should_show_command_popup(self, value: str) -> bool:
        return value.startswith("/") and value.strip() == value

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        self.query_one("#chat-input", Input).clear()
        if message.startswith("/"):
            self.hide_command_popup()
            await self.handle_command(message)
            return

        chat = self.query_one(ChatPanel)
        chat.add_message("you", event.value)
        await self._ensure_session_persisted()
        await self.runtime.add_message("user", event.value)
        self.call_llm(event.value)

    def show_command_popup(self, prefix: str) -> None:
        options = [
            Option(f"{name} - {description}", id=name)
            for name, description in self.SLASH_COMMANDS.items()
            if name.startswith(prefix)
        ]
        if not options:
            self.hide_command_popup()
            return
        self.command_palette.clear_options()
        self.command_palette.add_options(options)
        self.command_palette.highlighted = 0
        self.command_popup.display = True

    def hide_command_popup(self) -> None:
        self.command_popup.display = False

    async def show_session_popup(self) -> None:
        sessions = await self.runtime.list_sessions()
        if not sessions:
            chat = self.query_one(ChatPanel)
            chat.add_message("ayu", "没有其他会话")
            return
        self.push_screen(SessionPickerScreen(sessions), self.on_session_selected)

    def on_session_selected(self, session_id: str | None) -> None:
        self.query_one("#chat-input", Input).focus()
        if session_id is None:
            return
        if session_id == self.runtime.session.id:
            return
        self._switch_to_session(session_id)

    def _switch_to_session(self, session_id: str) -> None:
        import asyncio

        asyncio.ensure_future(self._do_switch_session(session_id))

    async def _do_switch_session(self, session_id: str) -> None:
        self.logger.info(f"切换会话: {session_id}")
        try:
            await self.runtime.switch_session(session_id)
            self._session_persisted = True
        except Exception:
            self.logger.exception("切换会话失败")
            self.query_one(ChatPanel).add_message("ayu", f"会话加载失败: {session_id}")
            return
        chat = self.query_one(ChatPanel)
        chat.clear_messages()
        # 预扫描 tool_calls_json，建立 tool_call_id → arguments 的查找表
        _tool_call_args: dict[str, str] = {}
        import json
        for msg in self.runtime.session.messages:
            if msg.role == "system":
                continue
            if msg.role == "assistant" and msg.tool_calls_json:
                try:
                    calls = json.loads(msg.tool_calls_json)
                    for call in calls:
                        cid = call.get("id", "")
                        func = call.get("function", {})
                        if cid and func.get("arguments"):
                            _tool_call_args[cid] = func["arguments"]
                except json.JSONDecodeError:
                    pass

        for msg in self.runtime.session.messages:
            if msg.role == "system":
                continue
            if msg.role == "user":
                chat.add_message("you", msg.content)
            elif msg.role == "assistant":
                if msg.reasoning_content:
                    chat.mount(Static(f"[dim]{msg.reasoning_content}[/]", classes="chat-message"))
                    chat.scroll_end(animate=False)
                if msg.content:
                    chat.add_message("ayu", msg.content)
            elif msg.role == "tool":
                tool_name = msg.name or "?"
                tool_args = _tool_call_args.get(msg.tool_call_id or "", "")
                display_text = format_tool_display(tool_name, tool_args, "done")
                chat.add_message("ayu", f"✅ {display_text}")
        self.logger.info(f"已切换到会话: {session_id}")

    def show_model_popup(self) -> None:
        options = [Option("dummy/dummy", id="dummy::dummy")]
        options.extend([
            Option(f"{provider}/{model}", id=f"{provider}::{model}")
            for provider, models in self.runtime.config.llm.providers.items()
            for model in models.models.keys()
        ])
        self.push_screen(ModelPickerScreen(options), self.on_model_selected)

    def on_model_selected(self, selected: str | None) -> None:
        from hi_ayu.config import save_state
        from hi_ayu.llm import update_runtime_selection

        self.query_one("#chat-input", Input).focus()
        if selected is None:
            return
        provider, model = selected.split("::", maxsplit=1)
        self.runtime.state.provider = provider
        self.runtime.state.model = model
        save_state(self.runtime.state)
        update_runtime_selection(provider, model)
        chat = self.query_one(ChatPanel)
        chat.add_message("ayu", f"已切换模型: {provider}/{model}")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_list_id = event.option_list.id
        if option_list_id == "command-palette":
            self.fill_input_with_command(str(event.option.id))
            self.hide_command_popup()
            return
        if option_list_id == "model-palette":
            return

    def fill_input_with_command(self, command: str) -> None:
        input_widget = self.query_one("#chat-input", Input)
        completed_command = command + self.COMMAND_SUFFIX
        input_widget.value = completed_command
        input_widget.cursor_position = len(completed_command)
        input_widget.focus()

    def action_command_up(self) -> None:
        palette = self.get_active_option_list()
        if palette is None:
            return
        palette.action_cursor_up()

    def action_command_down(self) -> None:
        palette = self.get_active_option_list()
        if palette is None:
            return
        palette.action_cursor_down()

    def action_command_select(self) -> None:
        palette = self.get_active_option_list()
        if palette is None:
            return
        palette.action_select()

    def get_active_option_list(self) -> OptionList | None:
        popup = getattr(self, "command_popup", None)
        if popup is not None and popup.display:
            return self.command_palette
        return None

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in {"command_up", "command_down", "command_select"}:
            return self.get_active_option_list() is not None
        return super().check_action(action, parameters)

    async def handle_command(self, raw_command: str) -> None:
        command = raw_command.split()[0]
        chat = self.query_one(ChatPanel)
        match command:
            case "/help":
                supported = "、".join(self.SLASH_COMMANDS.keys())
                chat.add_message("ayu", f"可用命令: {supported}")
            case "/models":
                self.show_model_popup()
            case "/sessions":
                await self.show_session_popup()
            case "/log":
                self.toggle_log_panel()
            case "/quit":
                self.exit()
            case _:
                chat.add_message("ayu", f"未知命令: {command}，输入 /help 查看可用命令")

    @work(exclusive=False)
    async def call_llm(self, message: str) -> None:
        self.logger.info("开始请求模型")
        self._set_ai_working(True)
        chat_panel = self.query_one(ChatPanel)
        # 显示等待指示器，第一个事件到达时移除
        thinking: Static | None = Static("🤔 思考中...", classes="chat-message message-ai thinking-indicator")
        chat_panel.mount(thinking)
        chat_panel.scroll_end(animate=False)

        reasoning_message: Static | None = None
        reasoning_chunks: list[str] = []
        reasoning_content: str = ""
        stream_message: Markdown | None = None
        stream_chunks: list[str] = []
        chunks: list[str] = []
        assistant_content = ""
        pending_line = ""
        # tool_call_id -> (Markdown widget, tool_name)，每个工具调用独立显示
        _tool_widgets: dict[str, tuple[Markdown, str]] = {}
        # 收集当前轮次的 tool call，用于构造 assistant 消息
        pending_tool_calls_for_session: list[dict[str, str]] = []
        in_tool_round = False
        # token 用量
        _last_usage: dict[str, object] | None = None
        try:
            async for event in chat_stream(
                self.runtime.session.to_llm_messages(),
                tool_registry=self.runtime.tool_registry,
            ):
                # 第一个事件到达时移除等待指示器
                if thinking is not None:
                    thinking.remove()
                    thinking = None
                if event.type == "reasoning":
                    if reasoning_message is None:
                        reasoning_message = chat_panel.begin_reasoning_message("ayu")
                        reasoning_chunks = []
                    reasoning_chunks.append(event.text)
                    reasoning_content = "".join(reasoning_chunks)
                    chat_panel.update_reasoning_message(reasoning_message, "ayu", reasoning_content)
                    continue
                if event.type == "tool_call":
                    self.logger.info(event.text)
                    # 每个工具调用创建独立 widget
                    widget = Markdown("", classes="chat-message message-ai")
                    chat_panel.mount(widget)
                    widget.update(f"🔧 {event.text}")
                    _tool_widgets[event.tool_call_id or event.tool_name or ""] = (widget, event.tool_name or "")
                    chat_panel.scroll_end(animate=False)
                    # 新轮次的工具调用：重置流消息，准备收集 tool calls
                    reasoning_message = None
                    stream_message = None
                    stream_chunks = []
                    if event.tool_call_id:
                        if not in_tool_round:
                            in_tool_round = True
                            pending_tool_calls_for_session = []
                        pending_tool_calls_for_session.append(
                            {"id": event.tool_call_id,
                             "name": event.tool_name or "",
                             "arguments": event.tool_arguments or ""}
                        )
                    continue
                if event.type == "tool_result":
                    self.logger.info(event.text)
                    # 更新对应工具调用的 widget 为完成状态
                    _key = event.tool_call_id or event.tool_name or ""
                    if _key in _tool_widgets:
                        widget, _ = _tool_widgets[_key]
                        widget.update(f"✅ {event.text}")
                    else:
                        # 容错：找不到对应 widget 时创建新消息
                        widget = Markdown("", classes="chat-message message-ai")
                        chat_panel.mount(widget)
                        widget.update(f"✅ {event.text}")
                    chat_panel.scroll_end(animate=False)
                    # 保存 assistant 消息（含 tool_calls + reasoning）
                    if in_tool_round and pending_tool_calls_for_session:
                        import json
                        tool_calls_json = json.dumps([
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": tc["arguments"],
                                },
                            }
                            for tc in pending_tool_calls_for_session
                        ], ensure_ascii=False)
                        await self.runtime.add_message(
                            role="assistant",
                            content="",
                            tool_calls_json=tool_calls_json,
                            reasoning_content=reasoning_content,
                        )
                        in_tool_round = False
                        pending_tool_calls_for_session = []
                    # 保存 tool 结果
                    await self.runtime.add_message(
                        role="tool",
                        content=event.tool_result or "",
                        tool_call_id=event.tool_call_id or "",
                        name=event.tool_name,
                    )
                    reasoning_message = None
                    continue
                if event.type == "usage":
                    self.logger.info("token 用量: %s", event.usage)
                    _last_usage = event.usage
                    continue
                if stream_message is None:
                    stream_message = chat_panel.begin_stream_message("ayu")
                    stream_chunks = []
                chunks.append(event.text)
                stream_chunks.append(event.text)
                pending_line += event.text
                if "\n" in pending_line:
                    chat_panel.update_stream_message(stream_message, "ayu", "".join(stream_chunks))
                    pending_line = pending_line.rsplit("\n", maxsplit=1)[-1]
            assistant_content = "".join(chunks)
            if stream_message is not None:
                chat_panel.update_stream_message(stream_message, "ayu", "".join(stream_chunks))
        finally:
            if thinking is not None:
                thinking.remove()
                thinking = None
        # 如果有残余的 tool_calls（理论上不会发生），也保存
        if in_tool_round and pending_tool_calls_for_session:
            import json
            tool_calls_json = json.dumps([
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                }
                for tc in pending_tool_calls_for_session
            ], ensure_ascii=False)
            await self.runtime.add_message(
                role="assistant",
                content="",
                tool_calls_json=tool_calls_json,
                reasoning_content=reasoning_content,
            )
        await self.runtime.add_message(
            "assistant", assistant_content, reasoning_content=reasoning_content,
            metadata={"usage": _last_usage} if _last_usage else None,
        )
        self._set_ai_working(False, usage=_last_usage)
        self.logger.info("模型响应完成")

    @work(exclusive=True)
    async def on_unmount(self) -> None:
        if hasattr(self, "runtime"):
            await self.runtime.backend.close()

    async def warmup_llm(self) -> None:
        from hi_ayu.llm import warmup_stream

        self.logger.info("开始预热模型连接")
        try:
            warmed = await warmup_stream()
        except Exception as exc:
            self.logger.warning(f"模型预热失败: {exc}")
            return
        if warmed:
            self.logger.info("模型预热完成")
