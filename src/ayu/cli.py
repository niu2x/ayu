import typer
from rich.console import Console

console = Console()

app = typer.Typer(
    name="ayu",
    help="A terminal AI agent that surpasses opencode and claudecode.",
    no_args_is_help=True,
)

config_app = typer.Typer(help="管理静态配置 config.json")
state_app = typer.Typer(help="管理运行态 state.json")
app.add_typer(config_app, name="config")
app.add_typer(state_app, name="state")


@app.command()
def tui() -> None:
    """启动 TUI 界面"""
    from ayu.tui_app import AyuTUIApp
    AyuTUIApp().run()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-H", help="Bind address"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of workers"),
) -> None:
    from ayu.server import run_server
    run_server(host=host, port=port, workers=workers)


@config_app.command()
def show() -> None:
    """查看完整 config.json"""
    from ayu.config import load_config
    console.print(load_config().model_dump_json(indent=2))


@config_app.command()
def path() -> None:
    """显示 config.json 路径"""
    from ayu.config import get_config_path
    console.print(get_config_path())


@config_app.command()
def set_provider(
    name: str = typer.Argument(help="提供商名称"),
    api_key: str = typer.Option("", "--api-key", "-k", help="API key"),
    base_url: str = typer.Option("", "--base-url", "-b", help="API 地址"),
    api_style: str = typer.Option("openai", "--api-style", "-s", help="API 风格 (openai/anthropic/google)"),
) -> None:
    """添加或更新一个 LLM 提供商"""
    from ayu.config import LLMProviderConfig, load_config, save_config
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
    from ayu.config import load_config, save_config
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
    from ayu.config import ModelConfig, load_config, save_config
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
    from ayu.config import load_config, save_config
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


@state_app.command()
def show_state() -> None:
    """查看当前 state.json"""
    from ayu.config import load_state
    console.print(load_state().model_dump_json(indent=2))


@state_app.command()
def state_path() -> None:
    """显示 state.json 路径"""
    from ayu.config import get_state_path
    console.print(get_state_path())


@state_app.command()
def set_state(
    key: str = typer.Argument(help="字段名 (provider/model/theme)"),
    value: str = typer.Argument(help="值"),
) -> None:
    """设置运行态字段"""
    from ayu.config import load_state, save_state
    allowed = {"provider", "model", "theme"}
    if key not in allowed:
        console.print(f"不允许的字段: {key}，可选: {', '.join(sorted(allowed))}")
        raise typer.Exit(1)
    state = load_state()
    setattr(state, key, value)
    save_state(state)
    console.print(f"已设置 state.{key} = {value}")
