from typing import Final, Literal

PermissionAction = Literal["read_file", "write_file", "run_shell"]

READ_FILE_ACTION: Final[PermissionAction] = "read_file"
WRITE_FILE_ACTION: Final[PermissionAction] = "write_file"
RUN_SHELL_ACTION: Final[PermissionAction] = "run_shell"
