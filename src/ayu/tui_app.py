from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.widgets import Footer, Input, OptionList, Static
from textual.widgets.option_list import Option


class ChatPanel(VerticalScroll):
    def add_message(self, role: str, content: str) -> None:
        self.mount(Static(f"[bold]{role}:[/] {content}"))
        self.scroll_end(animate=False)


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
        "/quit": "退出 ayu",
    }
    CSS = """
    Screen {
        layout: vertical;
    }
    ChatPanel {
        border: solid $primary;
        height: 1fr;
        margin: 1;
        padding: 1;
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
        yield ChatPanel()
        yield Container(OptionList(id="command-palette"), id="command-popup")
        yield Input(placeholder="Type a message and press Enter...", id="chat-input")
        yield Footer()

    def on_mount(self) -> None:
        from ayu.config import load_config, load_state
        self.config = load_config()
        state = load_state()
        self.theme = state.theme
        chat = self.query_one(ChatPanel)
        chat.add_message("ayu", "Hello! I'm ayu. How can I help you?")
        self.query_one("#chat-input", Input).focus()
        self.command_popup = self.query_one("#command-popup", Container)
        self.command_palette = self.query_one("#command-palette", OptionList)

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

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "command-palette":
            return
        self.fill_input_with_command(str(event.option.id))
        self.hide_command_popup()

    def fill_input_with_command(self, command: str) -> None:
        input_widget = self.query_one("#chat-input", Input)
        completed_command = command + self.COMMAND_SUFFIX
        input_widget.value = completed_command
        input_widget.cursor_position = len(completed_command)
        input_widget.focus()

    def action_command_up(self) -> None:
        if not self.command_popup.display:
            return
        self.command_palette.action_cursor_up()

    def action_command_down(self) -> None:
        if not self.command_popup.display:
            return
        self.command_palette.action_cursor_down()

    def action_command_select(self) -> None:
        if not self.command_popup.display:
            return
        self.command_palette.action_select()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in {"command_up", "command_down", "command_select"}:
            return self.command_popup.display
        return super().check_action(action, parameters)

    def handle_command(self, raw_command: str) -> None:
        command = raw_command.split()[0]
        chat = self.query_one(ChatPanel)
        match command:
            case "/help":
                supported = "、".join(self.SLASH_COMMANDS.keys())
                chat.add_message("ayu", f"可用命令: {supported}")
            case "/quit":
                self.exit()
            case _:
                chat.add_message("ayu", f"未知命令: {command}，输入 /help 查看可用命令")

    @work(exclusive=False)
    async def call_llm(self, message: str) -> None:
        from ayu.llm import chat
        chat_panel = self.query_one(ChatPanel)
        response = await chat([{"role": "user", "content": message}])
        chat_panel.add_message("ayu", response)
