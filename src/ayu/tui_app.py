from textual import work
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Header, Footer, Input, Static


class ChatPanel(VerticalScroll):
    def add_message(self, role: str, content: str) -> None:
        self.mount(Static(f"[bold]{role}:[/] {content}"))
        self.scroll_end(animate=False)


class AyuTUIApp(App):
    TITLE = "ayu"
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
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield ChatPanel()
        yield Input(placeholder="Type a message and press Enter...")
        yield Footer()

    def on_mount(self) -> None:
        from ayu.config import load_config, load_state
        self.config = load_config()
        state = load_state()
        self.theme = state.theme
        chat = self.query_one(ChatPanel)
        chat.add_message("ayu", "Hello! I'm ayu. How can I help you?")
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        chat = self.query_one(ChatPanel)
        chat.add_message("you", event.value)
        self.query_one(Input).clear()
        self.call_llm(event.value)

    @work(exclusive=False)
    async def call_llm(self, message: str) -> None:
        from ayu.llm import chat
        chat_panel = self.query_one(ChatPanel)
        response = await chat([{"role": "user", "content": message}])
        chat_panel.add_message("ayu", response)
