# ayu — AI Agent超越opencode和claude code

## 项目定位

ayu 是一个终端 AI Agent 产品，目标是超越 opencode 和 Claude Code。
核心竞争力：Python 原生 AI 生态 + Textual 成熟 TUI + 轻量单体架构，不做自研轮子。

## 技术栈

| 层 | 选型 |
|------|------|
| 语言 | Python >=3.13 |
| CLI 框架 | typer |
| TUI 框架 | Textual |
| Web 服务 | FastAPI + uvicorn |
| 包管理 | uv |
| 构建 | uv_build |

## 架构

```
src/ayu/
  __init__.py   # main = app (typer 入口)
  cli.py        # typer CLI: 消息参数→单次对话, 无参→TUI, serve→FastAPI
  config.py     # Pydantic 配置 schema，自动初始化到 ~/.config/ayu/config.json
  tui_app.py    # Textual TUI: 聊天面板 + 输入框
  server.py     # FastAPI: 健康检查端点
```

## 常用命令

```bash
uv run ayu          # 启动 TUI（无参默认行为）
uv run ayu chat "hello"  # 单次对话模式（不打开 TUI，不持久化，输出到 stdout，用 dummy 返回 "OK"）
uv run ayu --api-key <key> --base-url <url> --model <name> chat "hello"  # 使用临时 provider 的单次对话
uv run ayu serve    # 启动 FastAPI 服务 (默认 127.0.0.1:8000)
uv run ayu serve --host 0.0.0.0 --port 8080
uv run ayu --help   # 查看帮助

uv run ayu config show              # 查看完整配置
uv run ayu config set-provider <name> --api-key <key>   # 添加/更新提供商
uv run ayu config remove-provider <name>                # 删除提供商
uv run ayu config set-model <provider> <name>           # 添加/更新模型
uv run ayu config remove-model <provider> <name>        # 删除模型
uv run ayu state show        # 查看 state.json
uv run ayu state path        # 显示 state.json 路径

uv sync             # 安装/同步依赖
uv add <package>    # 添加依赖
uv lock             # 更新 lock 文件
uv run python scripts/check.py   # 运行全部检查
```

## 编码约定

- **注释用中文** — 需要时用中文写注释，清晰直接
- **类型注解** — 所有函数必须标注类型
- **字符串引号** — 双引号
- **asyncio 优先** — IO 操作统一用 async/await，避免同步阻塞
- **import 顺序** — 标准库 → 第三方 → 本地（每组空行分隔）
- **不用中文命名** — 代码、变量全英文
- **Textual CSS** — TUI 样式写在 `CSS` 类属性中，不单独写 .css 文件
- **模块职责单一** — cli 只做路由，tui 只管界面，server 只管 API
- **Python 3.13** — 使用最新语法特性，如 `elif` 外的 match/case 等
- **Pydantic v2** — 所有数据模型用 `BaseModel`，不用 dataclass 和 TypedDict

## 修改代码后的检查清单

修改代码后必须执行检查，全部通过才能提交：

- [ ] **检查脚本** — `uv run python scripts/check.py`

## 文档维护规范

- 只要修改了代码逻辑（尤其是 CLI/TUI 交互、配置/state 行为、命令语义），必须同步更新 `docs/` 下对应技术文档。
- 技术文档默认写给维护人员，要求能解释“为什么这样实现”，并包含关键回调、数据流、常见坑与回归步骤。
- 若没有现成文档，需在 `docs/` 新增一份维护文档；禁止只改代码不补文档。

## 设计原则

1. **站巨人肩膀** — 不自己造 TUI 框架、不自己造 LLM SDK、不自己造协议
2. **Python 生态优先** — 遇到问题先找 Python 社区方案
3. **轻量单体** — 不搞 monorepo、不搞客户端/服务器分离（serve 子命令是可选功能）
4. **模型中立** — 通过标准 API 接入，不走逆向工程
5. **开箱即用** — 无参数启动 TUI，--help 完善

## Tool Description 规范

tool 的 `description` 主要写给 agent，不是写给开发者看实现细节。目标是让 agent 清楚：

1. **什么时候用**（触发场景）
2. **怎么用**（关键参数与输入格式）
3. **能做什么**（能力边界与主要结果）

编写规则：

- 优先写使用语义，不写实现细节（例如不要写 asyncio、内部库名、内部函数名）。
- 对输入格式敏感的工具（如 `apply_patch`）必须在描述里给最小格式约束（例如需要 Begin/End、支持哪些指令）。
- 说明失败边界或前置条件（如“仅限工作区内路径，越界会触发授权”）。
- 保持简洁，但要足够可执行，避免“过短导致 agent 不知道如何调用”。

## Git 规范

- 使用 conventional commits: `feat:` `fix:` `chore:` `refactor:` `docs:`
- commit 信息用中文写
- commit 前检查 git status 和 git diff，只提交预期文件
- 不 amend、不 force-push

## 后续方向

- LLM Agent 核心（tool calling、文件编辑、bash 执行）
- LSP 集成
- 多会话管理
- 插件系统
