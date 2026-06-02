import asyncio
import platform
import time
from pathlib import Path

from pydantic import BaseModel


class ShellResult(BaseModel):
    ok: bool
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int
    cmdline: str
    workdir: str


def _truncate_text(content: str, max_output_bytes: int) -> str:
    encoded = content.encode("utf-8")
    if len(encoded) <= max_output_bytes:
        return content
    clipped = encoded[:max_output_bytes]
    restored = clipped.decode("utf-8", errors="ignore")
    return f"{restored}\n...[truncated]"


def _resolve_workdir(workdir: str | None) -> Path:
    if workdir is None:
        return Path.cwd()
    return Path(workdir).expanduser().resolve()


async def run_shell_command(
    command: str,
    timeout_seconds: int = 120,
    workdir: str | None = None,
    max_output_bytes: int = 51200,
) -> ShellResult:
    started_at = time.perf_counter()
    resolved_workdir = _resolve_workdir(workdir)
    system_name = platform.system().lower()

    if system_name == "windows":
        process = await asyncio.create_subprocess_exec(
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
            cwd=str(resolved_workdir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    else:
        process = await asyncio.create_subprocess_exec(
            "bash",
            "-lc",
            command,
            cwd=str(resolved_workdir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
        timed_out = False
    except asyncio.TimeoutError:
        process.kill()
        stdout_bytes, stderr_bytes = await process.communicate()
        timed_out = True

    stdout = _truncate_text(stdout_bytes.decode("utf-8", errors="replace"), max_output_bytes)
    stderr = _truncate_text(stderr_bytes.decode("utf-8", errors="replace"), max_output_bytes)
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    exit_code = process.returncode

    return ShellResult(
        ok=(not timed_out and exit_code == 0),
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        duration_ms=duration_ms,
        cmdline=command,
        workdir=str(resolved_workdir),
    )
