import platform
from datetime import datetime
from pathlib import Path


def _build_base_prompt() -> str:
    return "You are ayu, a helpful AI coding assistant."


def _is_in_git_repo(path: Path) -> bool:
    current = path
    while True:
        git_marker = current / ".git"
        if git_marker.exists():
            return True
        if current.parent == current:
            return False
        current = current.parent


def _build_environment_prompt() -> str:
    cwd = Path.cwd().resolve()
    is_git_repo = _is_in_git_repo(cwd)
    operating_system = platform.system()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    return (
        "Environment:\n"
        f"- Current working directory: {cwd}\n"
        f"- Is git repository: {'yes' if is_git_repo else 'no'}\n"
        f"- Operating system: {operating_system}\n"
        f"- Current time: {now}"
    )


def _build_agents_prompt() -> str:
    agents_file = Path.cwd().resolve() / "AGENTS.md"
    if not agents_file.exists() or not agents_file.is_file():
        return ""
    content = agents_file.read_text("utf-8").strip()
    if not content:
        return ""
    return f"Project instructions from AGENTS.md:\n{content}"


def build_system_prompt() -> str:
    sections = [
        _build_base_prompt(),
        _build_environment_prompt(),
        _build_agents_prompt(),
    ]
    return "\n\n".join(section for section in sections if section.strip())
