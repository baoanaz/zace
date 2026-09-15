# zace

面向 Coding Agent 的 Workspace Context Engine：融合代码图谱、Spec 文档、混合检索与基于事实依据的回答，
替代 Agent 在 Debug / 开发前大量 grep、read、调用链分析所消耗的 Context Acquisition 成本。

> 核心指标不是搜索延迟，而是 **Context Acquisition Cost**：Agent 为正确理解任务所需的时间、Tool Calls、Token 与人工干预。
>
> 对 Agent 只暴露两个工具：`search_context`（Fast，不调 LLM）/ `ask_project`（Deep，grounded answer + citation 回验）。

> **新人/新会话先读 [`HANDOFF.md`](HANDOFF.md)**：项目现状、下一步任务、环境事实、协作纪律与已知缺口，一份读完即可开工。
>
> **要用三靶场（`leveldb` / `HelloAgents` / `langchain`）跑基准**：先读 [`benches/README.md`](benches/README.md) 的「新会话从这里开始」——
> 索引已持久化在 `/root/.zace/bench/voyage-4-lite-d1024`，**复用即可，不要再 ingest**（清单见 `benches/results/raw/ingest-vps/INDEXES.json`）。

## 仓库布局（monorepo，D-35）

### 顶层

| 目录 | 内容 | 状态 |
|---|---|---|
| `core/` | **zace-core** 纯库（Module/01-04）：解析 → 切片 → 存储 → 检索 → 组装 | 可用（Phase 1 完成） |
| `service/` | **zace-service** 外壳（Module/06）：HTTP API、索引 job、MCP 端点 | 可用（M2a 完成） |
| `client/` | **zace-client**（Rust，Module/05）：MCP stdio + 本地同步代理 | 可用 |
| `npm/` | 分发包装器：`npx zace-client` 按平台取二进制并拉起 | 已发布 `zace-client@0.0.1` |
| `web/` | **zace-web** SPA（Module/07）：管理面 + Playground，只消费 service 的 REST API | 骨架（Phase 4） |
| `benches/` | golden 集与基准跑分（`golden/` 用例、`bakeoff/` 模型选型、`embed-bench/` 索引计量、`results/` 报告与证据） | — |
| `docs/design/` | 设计文档（`INDEX.md` 为入口，决策以 §3 决策登记表为准） | 活文档 |
| `docs/contracts/` | 冻结契约（DDL / JSON schema / OpenAPI / MCP tools）——变更须走编排流程 | 冻结 |
| `docs/plan/` | roadmap / 编排流程 / 契约清单 / 云端 MCP 就绪度报告 | — |
| `docs/tasks/` | 任务板与任务卡（实施入口：`README.md` 是任务板） | — |
| `docs/handbook/` | 操作手册（M2a 验收、云端 embedding 接入、provider 切换） | — |
| `scripts/` | 工具脚本：依赖方向检查、版本一致性、泳道管理、冒烟 | — |
| `.github/workflows/` | `ci.yml`（推送触发）+ `release.yml`（`v*` tag 触发五平台构建） | — |
| `server.json` | MCP registry 清单（stdio 传输 + runtime 参数） | — |

**依赖方向（CI 强制）**：`web, client → service → core`，core 零上层依赖（D-33/D-34）。

### 包内模块

```text
core/zace_core/            service/zace_service/        client/src/
├── parsing/   tree-sitter 抽取（Python/C/C++/MD）      ├── identity.rs  D-29 身份
├── chunking/  切片 + unresolved 两阶段解析             ├── blobref.rs   CF-02 哈希
├── storage/   SQLite+FTS5（jieba 双侧预分词）          ├── ignore.rs    D-28 三层忽略
├── vectors/   LanceDB + hash 复用对账                  ├── index.rs     本地缓存与对账
├── retrieval/ exact/bm25/vector/rrf/expand/rerank      ├── remote.rs    CF-05 客户端
├── contextpack/ 组装 + Markdown 渲染（D-21）           ├── tools.rs     CF-06 两工具
├── embedding/ 双实现：本地 ONNX / OpenAI 兼容 API      ├── protocol.rs  MCP stdio
├── pipeline/  ignore 规则 / source / indexer           └── main.rs      CLI 入口
├── text/      CJK 分词（D-45）
├── engine.py  引擎装配        routers/  auth|projects|query|sync|ops
├── hashing.py CF-02 哈希      mcp.py    /mcp 端点（HTTP 形态）
├── types.py   CF-01 类型      runtime.py EngineManager（懒构造/懒重扫）
└── interfaces.py CF-07/08/09  indexer.py 后台索引 + 进度
```

`core/{types,interfaces,hashing}.py` 与 `docs/contracts/**` 是**冻结契约**：改它们必须走
`docs/plan/orchestration.md` §4 的流程，实施任务不得直接改。

### 运行时形态

```text
编辑器（Claude Code / Codex / Cursor / pi）
        │ stdio MCP（npx zace-client）
        ▼
   zace-client（本地：扫描 / 忽略 / 哈希 / 增量上传）
        │ HTTPS + Bearer（resolve → batch-upload → query/search）
        ▼
   zace-service（FastAPI：API / 索引 job / 渲染）
        │ 进程内调用
        ▼
   zace-core（引擎：检索 → 组装 → ContextPack）
```

## 开发环境

```bash
# 需要 Python >= 3.12、uv（https://docs.astral.sh/uv/）
uv sync --all-packages --all-extras     # 安装 core + service（含 dev extras）
uv run ruff check .                     # lint
uv run python scripts/check_dependency_direction.py   # 依赖方向检查（D-34）
uv run pytest                           # 测试
```

## 状态

V1 开发中。已完成：Phase 0 骨架 ｜ Phase 1 = core 最小闭环 ｜ M2a = service + 本地 MCP。
可用接入（最终形态）：`npx zace-client --base-url <你的服务地址>`，暴露 `search_context` / `ask_project`
两个工具，见 `npm/README.md`。

设计与分工入口：`docs/design/INDEX.md`（设计）、`docs/tasks/README.md`（任务板）、
`docs/evidence/task-051-cloud-mcp-readiness.md`（云端接入的已知缺口，**含服务端鉴权未落地**这一硬前置）。

## 许可

TBD（开源发布前确定）。
