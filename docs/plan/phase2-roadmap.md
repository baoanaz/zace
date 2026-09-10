# Phase 2 路线图：MCP 端到端闭环（M2）

> 状态：2026-09-10 编排者制定（用户拍板 R32：先搭整体，再基于真实数据优化检索质量）。
> 目标（M2 验收口径）：**在 WSL 本地起服务 + 编辑器接 MCP，用真实问题验证成功**。
> 设计依据：`docs/design/Module/05-MCP与同步.md`（client）、`Module/06-服务化与部署.md`（service）；契约已冻结（CF-05/CF-06）。
>
> **优化纪律（R29/R30）**：Phase 2 **不再基于现有 60 条 smoke 集调质量参数**；
> 一切质量优化等 TASK-023 采集到真实调用数据后再做（TASK-050）。

## 0. 为什么是这个顺序

Phase 1 交付的 `zace-core` 已经能索引真实仓库（aibox 434 文件 / 5760 chunks）并返回带行号的
ContextPack。但它现在只能通过 CLI 使用——**用户要的形态是"编辑器里直接问"**，
这需要两块目前完全没有的东西：

| 缺口 | 提供者 | 为什么不能省 |
|---|---|---|
| HTTP 服务面（鉴权/租户/索引 job） | `zace-service` | MCP client 需要远端协议面；本地模式下它也是"进程内调用"的同一套接口 |
| MCP stdio client + 懒同步 | `zace-client` | 编辑器的唯一接入口；同步（scan/hash/checkpoint）只在这里做 |

## 1. 任务分解（Phase 2，编号从 TASK-030 起）

### 里程碑 M2a — 本地可跑通（**优先，你的 demo 靠这个**）

**形态裁定（R38）**：MCP 由 **service 直接提供**（Streamable HTTP），编辑器填 URL 直连；
Rust client 后移到 M2c（它是**远端场景**才必需的组件）。理由：原设计把 MCP 放 client 的前提是
"服务在远端（client 要扫描/哈希/上传）"；本地模式下 service 与代码同机，该前提不成立。

| 卡 | 内容 | 依赖 | 状态 |
|---|---|---|---|
| TASK-030 | service 骨架：FastAPI 应用 + 路由分组 + 配置 + `/healthz` + 结构化日志 | — | **done** |
| TASK-031 | core 接入：`EngineManager` + blob 镜像 + 同步账本 + 项目 API + `ingest(source=)` | TASK-030 | **done** |
| TASK-032 | 查询 API：`/api/query/search`（+ `/ask` 降级包） | TASK-031 | **done** |
| TASK-033 | 同步 API：`batch-upload` / `checkpoint` / `deletions` / `sync/status` | TASK-032 | **done** |
| TASK-035 | provider 健康与错误映射（503 语义 + 409 误导修复 + 私有调用收敛） | TASK-033 | pending |
| TASK-034 | 本地单用户模式：attach 本地仓库 + 一键起 + 后台索引进度 + 懒重扫 | TASK-035 | pending |
| TASK-040 | **service 侧 MCP 端点**（Streamable HTTP）+ 编辑器配置输出 | TASK-034 | pending |

**M2a 验收（就是你要的 demo）**：

```text
1. 一条命令起服务并绑定仓库：zace-service local --repo <你的仓库>
2. 在 Cursor 的 mcp.json 里填 URL（TASK-040 会把片段打出来）
3. 问一个真实问题 → AI 自动调 search_context → 拿到带行号与缺失说明的上下文
4. （可选）ask_project → 拿到降级包（LLM 总结属 Phase 3）
```

### 里程碑 M2b — 质量数据与优化（基于真实使用）

| 卡 | 内容 | 依赖 |
|---|---|---|
| TASK-023 | 真实场景用例采集（埋点 + 反馈信号 + 用例生成） | TASK-031 |
| TASK-050 | 质量调优（R21 装填配额 / R24 排序判别力 / TASK-015-B rerank 校准） | TASK-023 数据 |
| TASK-015A | embedding bake-off（**只做模型选型**，回归不调参） | 可并行 |

### 里程碑 M2c — 多用户、部署与 Rust client（如果你要分享给朋友）

| 卡 | 内容 | 依赖 |
|---|---|---|
| TASK-040R | **Rust client**（原计划放 M2a 的 TASK-040..043）：MCP stdio + 扫描/hash/增量上传 + 懒同步 + `npx zace` 分发 | TASK-033 |
| TASK-060 | 鉴权：API token + session（argon2id） | TASK-030 |
| TASK-061 | 租户双层：token→user→owns project + per-project 物理隔离 | TASK-060 |
| TASK-062 | 索引 job：进程内 worker + 进度上报 + 首同步后台化（D-31） | TASK-031 |
| TASK-063 | 部署：docker compose + Caddy TLS + 备份脚本 | TASK-060 |

**顺序说明**：M2a → 你的 demo 可用 → 用一段时间收集真实数据（TASK-023）→ M2b 调优 →
确实要给朋友用（服务上 VPS）时再做 M2c。**Rust client 归 M2c 而不是 M2a**（R38）：
只有当服务在**远端**时，"在代码本地扫描 + 哈希 + 上传"才有存在的理由。

## 2. 关键设计点（Phase 2 必须遵守的既有决策）

| 决策 | 说明 | 影响 |
|---|---|---|
| D-34 core 纯库 | service 只做"薄壳"，不含检索逻辑 | TASK-030/031 必须保持 CI 依赖方向检查通过 |
| D-21 渲染在服务端 | ContextPack → Markdown 由 service 返回，client 只透传 | TASK-032/040 不要各自实现渲染 |
| D-27 懒同步 | 无常驻 watcher；tool call 时对账 | 本地模式：服务端懒重扫（TASK-034 §C）；远端模式：client 对账（TASK-040R） |
| D-28 三层 ignore | `.zaceignore` > `.gitignore`（真实解析）> 内置默认 | TASK-040R；**已知缺口**：core 的 DirectorySource 只做内置默认，本地模式会把 `cmake-build-*/`、`.claude/skills/**` 一并索引（TASK-034 记录） |
| D-30 freshness 语义 | 上传完成 ≠ 索引完成，如实报告 `indexingFiles` | TASK-032 响应字段；TASK-034 的 indexProgress |
| MCP 形态（R38） | M2a：service 直出 Streamable HTTP（编辑器 URL 直连）；M2c：Rust client + stdio（远端场景） | TASK-040 / TASK-040R |
| 分层超时矩阵 | upload 30s / search 15s / ask 90s / 首同步 120s 转后台 | TASK-040R；本地模式改为服务端后台索引 + 进度上报（TASK-034） |

## 3. 已知技术债（Phase 2 一并处理或明确记录）

| # | 债务 | 归属 |
|---|---|---|
| R26 | 分支切换后索引陈旧无告警（`files.branch` 未使用） | TASK-034（本地模式懒重扫）；TASK-040R（远端：client 上报 branch） |
| R27 | 非 git 父目录聚合多仓库 → 身份退化为绝对路径、子仓被并入 | 明确不支持；TASK-034 在 attach 响应里如实提示，CLI/文档加提示 |
| R28 | 同步耗时构成（进程启动 2.0s vs 扫描 0.63s）；mtime 快路径未实现 | TASK-034（服务端常驻，进程启动只付一次；重扫间隔冷却） |
| — | `DirectorySource` 未落地 `.gitignore` 解析（影响索引范围与负例判定） | TASK-034 记录缺口；实现归 TASK-040R 或另立卡 |
| — | 首同步 17 分钟（aibox 规模）体验问题 | TASK-034（后台索引 + 进度）+ TASK-062 |

## 4. M1 成果小结（进 Phase 2 的起点）

```text
zace-core：11.5k 行代码 / 9.9k 行测试 / 501 passed
真实仓库验证：aibox 434 文件 / 5760 chunks / 1004s 全量索引
检索质量基线（60 条 smoke 集，R29 定位）：e2e recall@5 0.593 / r@10 0.704 / MRR 0.465
已知未修（等真实数据）：R21 装填平衡 / R24 排序判别力 / R31 answerable 脆弱点
```
