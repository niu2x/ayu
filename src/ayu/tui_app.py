import logging
import sys

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from ayu.llm import chat_stream


class ChatPanel(VerticalScroll):
    def add_message(self, role: str, content: str) -> None:
        if role == "you":
            self.mount(Static(content, classes="chat-message message-user"))
        else:
            self.mount(Markdown(content, classes="chat-message message-ai"))
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
        message.update(f"[dim]{content}[/]")
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


class AyuTUIApp(App):
    TITLE = "ayu"
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
    #log-panel {
        border: solid $accent;
        width: 45;
        padding: 1;
        display: none;
    }
    Input {
        margin: 0 1 1 1;
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
        yield Footer()

    def on_mount(self) -> None:
        from ayu.chat_runtime import build_chat_runtime

        self.runtime = build_chat_runtime()
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
        file_handler = logging.FileHandler("ayu.log", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
        self.logger.handlers = [self.log_handler, stderr_handler, file_handler]
        self.logger.info("日志系统已初始化")
        self.warmup_llm()

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

    def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        if message.startswith("/"):
            self.handle_command(message)
            self.query_one("#chat-input", Input).clear()
            self.hide_command_popup()
            return

        chat = self.query_one(ChatPanel)
        chat.add_message("you", event.value)
        self.runtime.session.add_message("user", event.value)
        self.query_one("#chat-input", Input).clear()
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

    def show_model_popup(self) -> None:
        options = [Option("dummy/dummy", id="dummy::dummy")]
        options.extend([
            Option(f"{provider}/{model}", id=f"{provider}::{model}")
            for provider, models in self.runtime.config.llm.providers.items()
            for model in models.models.keys()
        ])
        self.push_screen(ModelPickerScreen(options), self.on_model_selected)

    def on_model_selected(self, selected: str | None) -> None:
        from ayu.config import save_state
        from ayu.llm import update_runtime_selection

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
        if self.command_popup.display:
            return self.command_palette
        return None

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in {"command_up", "command_down", "command_select"}:
            return self.get_active_option_list() is not None
        return super().check_action(action, parameters)

    def handle_command(self, raw_command: str) -> None:
        command = raw_command.split()[0]
        chat = self.query_one(ChatPanel)
        match command:
            case "/help":
                supported = "、".join(self.SLASH_COMMANDS.keys())
                chat.add_message("ayu", f"可用命令: {supported}")
            case "/models":
                self.show_model_popup()
            case "/log":
                self.toggle_log_panel()
            case "/quit":
                self.exit()
            case _:
                chat.add_message("ayu", f"未知命令: {command}，输入 /help 查看可用命令")

    @work(exclusive=False)
    async def call_llm(self, message: str) -> None:
        self.logger.info("开始请求模型")
        chat_panel = self.query_one(ChatPanel)
        reasoning_message = chat_panel.begin_reasoning_message("ayu")
        reasoning_chunks: list[str] = []
        stream_message = chat_panel.begin_stream_message("ayu")
        chunks: list[str] = []
        pending_line = ""
        async for event in chat_stream(self.runtime.session.to_llm_messages()):
            if event.type == "reasoning":
                reasoning_chunks.append(event.text)
                chat_panel.update_reasoning_message(reasoning_message, "ayu", "".join(reasoning_chunks))
                continue
            chunks.append(event.text)
            pending_line += event.text
            if "\n" in pending_line:
                chat_panel.update_stream_message(stream_message, "ayu", "".join(chunks))
                pending_line = pending_line.rsplit("\n", maxsplit=1)[-1]
        assistant_content = "".join(chunks)
        chat_panel.update_stream_message(stream_message, "ayu", assistant_content)
        self.runtime.session.add_message("assistant", assistant_content)
        self.logger.info("模型响应完成")

    @work(exclusive=True)
    async def warmup_llm(self) -> None:
        from ayu.llm import warmup_stream

        self.logger.info("开始预热模型连接")
        try:
            warmed = await warmup_stream()
        except Exception as exc:
            self.logger.warning(f"模型预热失败: {exc}")
            return
        if warmed:
            self.logger.info("模型预热完成")
