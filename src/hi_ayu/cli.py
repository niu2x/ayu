import asyncio
import sys

import typer
from rich.console import Console

console = Console()

app = typer.Typer(
    name="ayu",
    help="A terminal AI agent that surpasses opencode and claudecode.",
    no_args_is_help=False,
)

config_app = typer.Typer(help="管理静态配置 config.json", no_args_is_help=True)
state_app = typer.Typer(help="管理运行态 state.json", no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(state_app, name="state")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    api_key: str = typer.Option("", "--api-key", help="临时 API key（需与 --base-url --model 同时使用）"),
    base_url: str = typer.Option("", "--base-url", help="临时 API 地址（需与 --api-key --model 同时使用）"),
    model: str = typer.Option("", "--model", help="临时模型名（需与 --api-key --base-url 同时使用）"),
    disable_all_tools: bool = typer.Option(False, "--disable-all-tools", help="禁用所有工具（不注册）"),
) -> None:
    from hi_ayu.llm import set_runtime_override
    from hi_ayu.tools import set_tools_disabled

    if api_key or base_url or model:
        if not (api_key and base_url and model):
            console.print("错误：--api-key、--base-url、--model 必须同时使用")
            raise typer.Exit(1)
        set_runtime_override(api_key, base_url, model)

    if disable_all_tools:
        set_tools_disabled(True)

    if ctx.invoked_subcommand is None:
        from hi_ayu.tui_app import AyuTUIApp
        AyuTUIApp().run()


@app.command()
def chat(
    message: str = typer.Argument(..., help="单次对话消息"),
) -> None:
    """单次对话模式：不打开 TUI，不持久化，输出到 stdout"""
    asyncio.run(_run_single_turn(message))


async def _run_single_turn(message: str) -> None:
    from hi_ayu.chat_runtime import build_chat_runtime
    from hi_ayu.llm import chat_stream
    from hi_ayu.storage.memory_backend import InMemoryBackend
    from hi_ayu.system_prompt import build_system_prompt

    backend = InMemoryBackend()
    await backend.setup()
    runtime = build_chat_runtime(backend)

    runtime.session.add_message("system", build_system_prompt())
    runtime.session.add_message("user", message)

    async for event in chat_stream(
        runtime.session.to_llm_messages(),
        tool_registry=runtime.tool_registry,
    ):
        if event.type == "content":
            sys.stdout.write(event.text)
            sys.stdout.flush()
    sys.stdout.write("\n")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-H", help="Bind address"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of workers"),
) -> None:
    from hi_ayu.server import run_server
    run_server(host=host, port=port, workers=workers)


@config_app.command()
def show() -> None:
    """查看完整 config.json"""
    from hi_ayu.config import load_config
    console.print(load_config().model_dump_json(indent=2))


@config_app.command()
def path() -> None:
    """显示 config.json 路径"""
    from hi_ayu.config import get_config_path
    console.print(get_config_path())


@config_app.command()
def set_provider(
    name: str = typer.Argument(help="提供商名称"),
    api_key: str = typer.Option("", "--api-key", "-k", help="API key"),
    base_url: str = typer.Option("", "--base-url", "-b", help="API 地址"),
    api_style: str = typer.Option("openai", "--api-style", "-s", help="API 风格 (openai/anthropic/google)"),
) -> None:
    """添加或更新一个 LLM 提供商"""
    from hi_ayu.config import LLMProviderConfig, load_config, save_config
    config = load_config()
    config.llm.providers[name] = LLMProviderConfig(
        api_style=api_style, api_key=api_key, base_url=base_url
    )
    save_config(config)
    console.print(f"已保存提供商 [bold]{name}[/]")


@config_app.command()
def remove_provider(
    name: str = typer.Argument(help="提供商名称"),
) -> None:
    """删除一个 LLM 提供商"""
    from hi_ayu.config import load_config, save_config
    config = load_config()
    if name not in config.llm.providers:
        console.print(f"提供商 [bold]{name}[/] 不存在")
        raise typer.Exit(1)
    del config.llm.providers[name]
    save_config(config)
    console.print(f"已删除提供商 [bold]{name}[/]")


@config_app.command()
def set_model(
    provider: str = typer.Argument(help="提供商名称"),
    name: str = typer.Argument(help="模型名称"),
    max_tokens: int = typer.Option(4096, "--max-tokens", "-m", help="最大 token 数"),
    temperature: float = typer.Option(0.7, "--temperature", "-t", help="温度"),
) -> None:
    """在指定提供商下添加或更新一个模型"""
    from hi_ayu.config import ModelConfig, load_config, save_config
    config = load_config()
    if provider not in config.llm.providers:
        console.print(f"提供商 [bold]{provider}[/] 不存在，请先添加")
        raise typer.Exit(1)
    config.llm.providers[provider].models[name] = ModelConfig(
        max_tokens=max_tokens, temperature=temperature
    )
    save_config(config)
    console.print(f"已保存模型 [bold]{provider}/{name}[/]")


@config_app.command()
def remove_model(
    provider: str = typer.Argument(help="提供商名称"),
    name: str = typer.Argument(help="模型名称"),
) -> None:
    """从指定提供商删除一个模型"""
    from hi_ayu.config import load_config, save_config
    config = load_config()
    if provider not in config.llm.providers:
        console.print(f"提供商 [bold]{provider}[/] 不存在")
        raise typer.Exit(1)
    if name not in config.llm.providers[provider].models:
        console.print(f"模型 [bold]{provider}/{name}[/] 不存在")
        raise typer.Exit(1)
    del config.llm.providers[provider].models[name]
    save_config(config)
    console.print(f"已删除模型 [bold]{provider}/{name}[/]")


@state_app.command("show")
def state_show() -> None:
    """查看当前 state.json"""
    from hi_ayu.config import load_state
    console.print(load_state().model_dump_json(indent=2))


@state_app.command("path")
def state_path() -> None:
    """显示 state.json 路径"""
    from hi_ayu.config import get_state_path
    console.print(get_state_path())
