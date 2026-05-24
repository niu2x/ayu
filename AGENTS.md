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
  cli.py        # typer CLI: 无参→启动TUI, serve→FastAPI
  tui_app.py    # Textual TUI: 聊天面板 + 输入框
  server.py     # FastAPI: 健康检查端点
```

## 常用命令

```bash
uv run ayu          # 启动 TUI（无参数默认行为）
uv run ayu serve    # 启动 FastAPI 服务 (默认 127.0.0.1:8000)
uv run ayu serve --host 0.0.0.0 --port 8080
uv run ayu --help   # 查看帮助

uv sync             # 安装/同步依赖
uv add <package>    # 添加依赖
uv lock             # 更新 lock 文件
```

## 编码约定

- **注释用中文** — 需要时用中文写注释，清晰直接
- **类型注解** — 所有函数必须标注类型
- **字符串引号** — 双引号
- **import 顺序** — 标准库 → 第三方 → 本地（每组空行分隔）
- **不用中文命名** — 代码、变量全英文
- **Textual CSS** — TUI 样式写在 `CSS` 类属性中，不单独写 .css 文件
- **模块职责单一** — cli 只做路由，tui 只管界面，server 只管 API
- **Python 3.13** — 使用最新语法特性，如 `elif` 外的 match/case 等
- **Pydantic v2** — 所有数据模型用 `BaseModel`，不用 dataclass 和 TypedDict

## 设计原则

1. **站巨人肩膀** — 不自己造 TUI 框架、不自己造 LLM SDK、不自己造协议
2. **Python 生态优先** — 遇到问题先找 Python 社区方案
3. **轻量单体** — 不搞 monorepo、不搞客户端/服务器分离（serve 子命令是可选功能）
4. **模型中立** — 通过标准 API 接入，不走逆向工程
5. **开箱即用** — 无参数启动 TUI，--help 完善

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
