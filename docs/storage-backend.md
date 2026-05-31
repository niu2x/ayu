# 存储后端

## 架构

通过 `PersistenceBackend` Protocol 实现可替换存储后端，当前支持：

- **InMemoryBackend** — 内存存储，适合测试和临时使用
- **SqliteBackend** — SQLite 持久化存储，适合生产使用

## SqliteBackend

### 数据表

**sessions 表**

| 列 | 类型 | 说明 |
|---|---|
| id | TEXT PK | 会话 ID |
| title | TEXT | 会话标题 |
| created_at | TEXT | ISO 8601 创建时间 |
| updated_at | TEXT | ISO 8601 更新时间 |
| metadata | TEXT | JSON 字符串 |

**messages 表**

| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | 消息 ID |
| session_id | TEXT | 所属会话 ID |
| event_ts | TEXT | ISO 8601 事件时间 |
| role | TEXT | user/assistant/system/tool |
| content | TEXT | 消息内容 |
| name | TEXT | tool 消息的函数名 |
| tool_call_id | TEXT | tool 消息关联的调用 ID |
| metadata | TEXT | JSON 字符串 |

索引：`idx_messages_session_ts` on `messages(session_id, event_ts)`

### 数据库路径

默认路径：`~/.local/share/ayu/ayu.db`（通过 `PlatformDirs.user_data_dir` 计算）

可通过 `SqliteBackend(db_path=Path(...))` 自定义路径。

### 使用方式

```python
from ayu.storage import create_backend

# 默认 SQLite
backend = create_backend()

# 内存（测试用）
backend = create_backend("memory")

# SQLite
backend = create_backend("sqlite")

# 自定义路径
backend = create_backend("sqlite", db_path=Path("/tmp/ayu.db"))
```

必须调用 `await backend.setup()` 初始化（创建表结构），使用完毕后调用 `await backend.close()` 关闭连接。

### 实现要点

- 使用 `aiosqlite` 实现异步非阻塞数据库访问
- `metadata` 字段存储为 JSON 字符串，读写时序列化/反序列化
- 会话删除级联删除关联消息
- 消息列表按 `event_ts ASC` 排序（与追加顺序一致）
- 不支持 FTS 全文搜索（`bm25=False`）、不支持向量搜索（`vector=False`）、不支持事务（`transactions=False`）
