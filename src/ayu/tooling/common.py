import hashlib
from pathlib import Path


def resolve_target_path(path: str, workspace_root: Path) -> Path:
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = workspace_root / target
    return target.resolve()


def compute_shell_command_hash(command: str) -> str:
    return hashlib.sha256(command.encode("utf-8")).hexdigest()
