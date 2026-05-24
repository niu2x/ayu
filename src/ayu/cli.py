from pathlib import Path

import typer

app = typer.Typer(
    name="ayu",
    help="A terminal AI agent that surpasses opencode and claudecode.",
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
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
