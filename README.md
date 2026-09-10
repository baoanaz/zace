# zace

面向 Coding Agent 的 Workspace Context Engine：融合代码图谱、Spec 文档、混合检索与基于事实依据的回答，
替代 Agent 在 Debug / 开发前大量 grep、read、调用链分析所消耗的 Context Acquisition 成本。

> 核心指标不是搜索延迟，而是 **Context Acquisition Cost**：Agent 为正确理解任务所需的时间、Tool Calls、Token 与人工干预。

## 形态

```text
Codex / Claude Code / Cursor
        │ MCP stdio
        ▼
zace-client（Rust 单二进制：MCP 适配 + 同步客户端）
        │ HTTPS + Bearer
        ▼
zace-service（FastAPI：API / 鉴权 / 租户 / 索引 job / 审计）
        │ 进程内调用
        ▼
zace-core（纯库引擎：切片存储 → 检索 → 上下文组装 → AI 总结）
```

两个工具：`search_context`（Fast，不调 LLM）/ `ask_project`（Deep，grounded answer + citation 回验）。

## 仓库布局（monorepo，D-35）

| 目录 | 内容 |
|---|---|
| `core/` | zace-core 纯库（Module/01-04）：切片存储 / 检索 / 上下文组装 / AI 总结 |
| `service/` | zace-service 外壳（Module/06）：HTTP API、鉴权、租户、索引 job |
| `client/` | zace-client（Rust，Module/05）：MCP stdio + 同步客户端（Phase 2） |
| `web/` | zace-web SPA（Module/07，Phase 4） |
| `docs/design/` | 设计文档（INDEX.md 为入口，决策登记表 §3 为准） |
| `docs/contracts/` | 冻结契约（DDL / JSON schema / OpenAPI / MCP tools）——变更须走编排流程 |
| `docs/plan/` | roadmap / 编排流程 / 契约冻结清单 |
| `docs/tasks/` | 任务板与任务卡（子 AI 实施入口） |
| `benches/` | golden set 与基准跑分 |

依赖方向（CI 强制）：`web, client → service → core`，core 零上层依赖（D-33/D-34）。

## 开发环境

```bash
# 需要 Python >= 3.12、uv（https://docs.astral.sh/uv/）
uv sync --all-packages --all-extras     # 安装 core + service（含 dev extras）
uv run ruff check .                     # lint
uv run python scripts/check_dependency_direction.py   # 依赖方向检查（D-34）
uv run pytest                           # 测试
```

## 状态

V1 开发中：Phase 0 骨架完成，Phase 1 = core 最小闭环（索引 → 检索 → ContextPack → CLI）。
设计文档见 `docs/design/INDEX.md`；任务分工见 `docs/tasks/README.md`。

## 许可

TBD（开源发布前确定）。
