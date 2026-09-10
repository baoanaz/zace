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

| 卡 | 内容 | 依赖 | 备注 |
|---|---|---|---|
| TASK-030 | service 骨架：FastAPI 应用 + 路由分组 + 配置 + `/healthz` + 结构化日志 | — | 实现 CF-05 的路径骨架，鉴权先留占位 |
| TASK-031 | core 接入：`ContextEngine` 进程内挂载 + per-project 打开/缓存 + 数据根配置 | TASK-030 | 引擎已是纯库（D-34），这里是"薄壳" |
| TASK-032 | 查询 API：`/api/query/search`（+ `/ask` 降级返回） | TASK-031 | 渲染在服务端（D-21） |
| TASK-033 | 同步 API：`batch-upload` / `checkpoint` / `deletions` / `sync/status` | TASK-031 | 幂等语义已在 CF-05 冻结 |
| TASK-034 | 本地单用户模式（**demo 关键**）：免鉴权 + 单 project + 一键起服务 | TASK-030 | 让"本机自己用"不需要注册/token |
| TASK-040 | client 骨架：Rust 二进制 + MCP stdio（工具 schema 照 CF-06） | TASK-032 | 协议纯净（stdout 只出 JSON-RPC） |
| TASK-041 | client 同步：scan + 三层 ignore + content hash 对账 + 增量上传 | TASK-040 | D-27/D-28；`.gitignore` 真实解析在此落地 |
| TASK-042 | client 懒同步 + checkpoint 自愈 + 分层超时矩阵 | TASK-041 | D-27/D-31/D-32；"tool call 自动保证新鲜" |
| TASK-043 | client 交付形态：`npx zace` 分发 + `zace mcp` 输出编辑器配置 | TASK-042 | 你的 demo 要"配置 MCP"这一步 |

**M2a 验收（就是你要的 demo）**：

```text
1. 本机起 service（TASK-034 的一键命令）
2. 在 Claude Code / Cursor 里配置 MCP（TASK-043 输出的 JSON）
3. 问一个真实问题 → AI 自动调 search_context → 拿到带行号与缺失说明的上下文
4. （可选）问一个需要综合的问题 → ask_project → 得到 grounded answer
```

### 里程碑 M2b — 质量数据与优化（基于真实使用）

| 卡 | 内容 | 依赖 |
|---|---|---|
| TASK-023 | 真实场景用例采集（埋点 + 反馈信号 + 用例生成） | TASK-031 |
| TASK-050 | 质量调优（R21 装填配额 / R24 排序判别力 / TASK-015-B rerank 校准） | TASK-023 数据 |
| TASK-015A | embedding bake-off（**只做模型选型**，回归不调参） | 可并行 |

### 里程碑 M2c — 多用户与部署（如果你要分享给朋友）

| 卡 | 内容 | 依赖 |
|---|---|---|
| TASK-060 | 鉴权：API token + session（argon2id） | TASK-030 |
| TASK-061 | 租户双层：token→user→owns project + per-project 物理隔离 | TASK-060 |
| TASK-062 | 索引 job：进程内 worker + 进度上报 + 首同步后台化（D-31） | TASK-031 |
| TASK-063 | 部署：docker compose + Caddy TLS + 备份脚本 | TASK-060 |

**顺序说明**：M2a → 你的 demo 可用 → 用一段时间收集真实数据（TASK-023）→ M2b 调优 →
如果确实要给朋友用，再做 M2c（多用户）。**不要颠倒**：多用户是产品化需求，不是 demo 需求。

## 2. 关键设计点（Phase 2 必须遵守的既有决策）

| 决策 | 说明 | 影响 |
|---|---|---|
| D-34 core 纯库 | service 只做"薄壳"，不含检索逻辑 | TASK-030/031 必须保持 CI 依赖方向检查通过 |
| D-21 渲染在服务端 | ContextPack → Markdown 由 service 返回，client 只透传 | TASK-032/040 不要各自实现渲染 |
| D-27 懒同步 | 无常驻 watcher；tool call 时对账 | TASK-042 的核心行为 |
| D-28 三层 ignore | `.zaceignore` > `.gitignore`（真实解析）> 内置默认 | TASK-041；当前 core 的 DirectorySource 只做了内置默认 |
| D-30 freshness 语义 | 上传完成 ≠ 索引完成，如实报告 `indexingFiles` | TASK-032 响应字段 |
| 分层超时矩阵 | upload 30s / search 15s / ask 90s / 首同步 120s 转后台 | TASK-042 |

## 3. 已知技术债（Phase 2 一并处理或明确记录）

| # | 债务 | 归属 |
|---|---|---|
| R26 | 分支切换后索引陈旧无告警（`files.branch` 未使用） | TASK-042 |
| R27 | 非 git 父目录聚合多仓库 → 身份退化为绝对路径、子仓被并入 | 明确不支持，CLI/文档加提示 |
| R28 | 同步耗时构成（进程启动 2.0s vs 扫描 0.63s）；mtime 快路径未实现 | TASK-041 |
| — | `DirectorySource` 未落地 `.gitignore` 解析（影响索引范围与负例判定） | TASK-041 |
| — | 首同步 17 分钟（aibox 规模）体验问题 | TASK-062 + TASK-041 优化 |

## 4. M1 成果小结（进 Phase 2 的起点）

```text
zace-core：11.5k 行代码 / 9.9k 行测试 / 501 passed
真实仓库验证：aibox 434 文件 / 5760 chunks / 1004s 全量索引
检索质量基线（60 条 smoke 集，R29 定位）：e2e recall@5 0.593 / r@10 0.704 / MRR 0.465
已知未修（等真实数据）：R21 装填平衡 / R24 排序判别力 / R31 answerable 脆弱点
```
