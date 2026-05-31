from ayu.storage.interfaces import PersistenceBackend
from ayu.storage.memory_backend import InMemoryBackend
from ayu.storage.sqlite_backend import SqliteBackend


def create_backend(kind: str = "memory", **kwargs: object) -> PersistenceBackend:
    if kind == "memory":
        return InMemoryBackend()
    if kind == "sqlite":
        db_path = kwargs.get("db_path")
        return SqliteBackend(db_path=db_path)  # type: ignore[arg-type]
    raise ValueError(f"不支持的存储后端: {kind}")
