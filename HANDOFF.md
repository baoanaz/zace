# zace 项目交接说明（2026-09-14 晚更新）

> **给接手 AI 的第一份文档**。读完这一份，你就知道：项目是什么、做到哪了、下一步做什么、别踩哪些坑。
> 详细任务清单在 `docs/tasks/README.md`；协作流程在 `docs/plan/orchestration.md` 与 `docs/plan/multi-ai-worktrees.md`。
> **跑基准前先读 [`benches/README.md`](benches/README.md)「新会话从这里开始」**：三靶场（`leveldb`/`HelloAgents`/`langchain`）的索引已持久化在 `/root/.zace/bench/voyage-4-lite-d1024`，**复用即可、不要再 ingest**；
> 设备绑定纪律与报告索引见 `benches/results/README.md`。
>
> 当前基线：`main @ d5f7eb4` ｜ ruff ✅ ｜ 依赖方向 ✅ ｜ **878 passed, 2 skipped** ｜ web **41 passed** + build ✅
>
> **本轮更新（2026-09-14 晚）**：TASK-087/088/089/090 已合并并端到端验证（真实 LLM 调用、MCP 越权拦截、
> trace id 日志查询均实测通过）；环境事实已重核（见 §6，cargo/docker 现已可用）。

---

## 0. 一句话现状

**整条链路已端到端跑通**：网页登录 → 创建 API Key → `npx zace-client` 接入 Codex → 真实提问 → 返回带「文件:行号」的证据。
检索引擎、服务化外壳、Rust 客户端、WebUI 全部可用；**剩下的是上线前加固与质量打磨**。

---

## 1. 项目是什么

zace = 给 Coding Agent（Codex/Cursor/Claude Code/pi）提供**代码库上下文检索**的引擎。
Agent 通过 MCP 调 `search_context` / `ask_project`，拿到**带「文件:行号」证据**的上下文包。

**四个物理单元**（monorepo，依赖方向 `web, client → service → core`，CI 强制检查）：

| 目录 | 单元 | 职责 |
|---|---|---|
| `core/` | zace-core | 引擎纯库：切片/存储/四路召回/RRF/图扩展/装填/渲染。**零 HTTP、零用户概念** |
| `service/` | zace-service | 服务化外壳：FastAPI REST + MCP 端点 `/mcp` + 鉴权 + 租户 + 索引/审计 |
| `client/` | zace-client | 本地 MCP stdio 客户端（Rust）：扫描/哈希/上传 |
| `web/` | zace-web | SPA 管理面（React/Vite/TS） |

技术栈：Python 3.12（uv）+ Rust + React/Vite。

---

## 2. 已完成（均已合并 main 并独立验证）

### Phase 1–2：core 检索闭环 + service 外壳

| 项 | 状态 |
|---|---|
| core：切片/存储/FTS5/四路召回/RRF/图扩展/装填/渲染/CLI/eval | ✅ |
| service：REST（查询/同步/项目）+ MCP 端点 `/mcp`（Streamable HTTP） | ✅ |
| 本地单用户模式：`zace-service local --repo <路径>` 一键起 + 后台索引 + 懒重扫 | ✅ |
| embedding 架构：按模型配置化 + provider 解耦 + 并发 | ✅ |

### Phase 3–4：鉴权 + 租户 + 统计 + WebUI（最近一波，A–H）

| 卡 | 内容 | 验证证据 |
|---|---|---|
| TASK-060 | 鉴权（session + API token + bootstrap + metadb） | 实测 bootstrap 201 / token 鉴权 200 |
| TASK-061 | **租户双层**（token → user → owns project） | 实测双用户越权：10 端点全 404，无凭据 401 |
| TASK-062/085 | 索引 job 落库与统计 | 实测 `index-stats` 0 → **1** |
| TASK-064/084 | 查询审计与用量 | 实测 `usage/summary` 0 → **3** |
| TASK-070 | WebUI（登录/控制台/API Key/历史/接入指南） | 746→804 pytest + 38 vitest + build 全绿 |
| TASK-080 | 接入指南两卡牌（npm 下载 + Agent 配置带 `--token`） | 实测生成的配置可直接用 |
| TASK-081 | 密码下限 8 → 3 | 真服务 3 位密码 bootstrap 201 |
| TASK-082 | 删除 Playground 与项目管理页 | 死链 grep 0 命中 |
| TASK-083 | 空态/错误态统一 | `catch{return[]}` → 抛错，不再把故障显示成空数据 |
| TASK-086 | 导航重排（控制台/接入指南/API Key/历史）+ 网格背景 | 截图核验 |

### Phase 3 补强（**2026-09-14 晚，四卡已合并并端到端验证**）

| 卡 | 内容 | 实测证据（编排者亲测） |
|---|---|---|
| TASK-087 | `next_queries` 渲染进正文（`### Suggested Next Queries` 节）+ `answerable=false` 短路包 | 三个无关问题均返回 `insufficient_evidence` + 完整短路包 |
| TASK-088 | `ask_project` 接入 LLM（可配置 `ANSWER_*` + Grounded Prompt + Citation 回验 + 设置页） | **真实 LLM 回答 2804 字，citation_coverage=1.0，879ms**；改 env 即改模型已验证 |
| TASK-089 | MCP 面归属校验（上云前最后越权口已堵） | bob 越权两工具均 `project_not_found`，无探测面 |
| TASK-090 | 请求日志持久化（文件轮转 + 有界窗口）+ trace id 查询 | 失败请求 → 拿 `X-Request-Id` → 查到完整日志（路径/状态/耗时/用户/错误码） |

**合并后的 `ask` 分支顺序**（087 + 088 合并后的真实语义，**证据优先**）：

| 情况 | `status` | 返回 |
|---|---|---|
| `answerable=false` | `insufficient_evidence` | 短路包（不调 LLM，含 `bestEffortContext`/`missingEvidence`/`nextQueries`） |
| 未配置 `ANSWER_*` | `degraded` | 前置说明 ＋ 渲染包 |
| 已配置但调用失败/超时 | `degraded` | 故障说明 ＋ 渲染包 |
| 成功 | `answered` | LLM 答案（已回验引用） |

### 真实端到端验证（编排者亲自跑的，不是采信报告）

```
Codex 调 search_context → 898 文件... 实际 236 文件 / 2729 chunks 索引
Voyage 嵌入：POST https://api.voyageai.com/v1/embeddings "200 OK"
返回证据：hello_agents/core/streaming.py:74-82 等带行号的代码块
审计落库：query_audit 1 条（answerable=1, confidence=medium, latency_ms=322）
```

---

## 3. 下一步做什么（按用户拍板的顺序）

用户 2026-09-14 的明确路线：

> 明天我仔细打磨两个工具的返回内容，以及补全多个真实的问题，打磨 benchmark 的设计。
> 等架构稳定后，加上各个用户的请求 LOG 缓存窗口机制…等全部稳定后，补上 VPS 部署。
> 就可以基于 VPS 的 IP 公网发布了。做好 tool 和质量之后，就可以发布给其他人使用，进行压测了。

### 已开卡（可直接派活）

| 卡 | 标题 | 硬依赖 | 状态 |
|---|---|---|---|
| ~~TASK-087~~ | ContextPack 渲染补齐 | 无 | ✅ **已合并**（`2664f70`） |
| ~~TASK-088~~ | `ask_project` 接入 LLM | 无 | ✅ **已合并**（`5aac030`） |
| ~~TASK-089~~ | MCP 面归属校验 | TASK-061 ✅ | ✅ **已合并**（`77f76ca`） |
| ~~TASK-090~~ | 请求日志持久化 + trace id 查询 | TASK-084 ✅ | ✅ **已合并**（`7ca94ff`） |
| **TASK-091** | 评测靶场与 golden 集打磨（~75 条用例） | 无 | 🔄 **进行中**（lane-e） |
| **TASK-094** | 项目内存可见性 + **存储配额 tool 告警** + 历史记录 trace id | ~~TASK-090~~ ✅ | ✅ **可开工**（依赖已解除） |
| **TASK-092** | VPS 部署（docker 现已可用，可本地部分验证） | ~~TASK-089/090~~ ✅ | ✅ **可开工** |
| **TASK-093** | 真实使用数据闭环（TASK-023 落地，**不含调参**；**已定不合并 023**） | TASK-084 ✅ / TASK-091 | ⛔ 等 091 |

### 用户的人工任务（非 AI 卡）

1. **打磨两个工具的返回内容**（依赖 087/088 落地后）；
2. **补全真实问题 + 打磨 benchmark**（配合 091/093）；
3. 质量参数解冻（R29/R30）**需用户单独授权**——当前 `docs_ratio`/`rerank` 权重是 smoke 集拟合值，
   **TASK-050 暂不开卡**。

---

## 4. 两个工具的返回（接手前必须理解）

### `search_context` → 渲染好的 ContextPack Markdown

```markdown
## Relevant Context
### Code
[E3] StreamBuffer — hello_agents/core/streaming.py:74-82
     reason: bm25 -11.46 + bm25 rank 32 + vector 0.4632 + vector rank 3 + entry point +0.2
     74 | class StreamBuffer:
### Docs
### Missing Evidence
- [unresolved_reference] 70 个符号引用无法解析...
### Meta
confidence: medium | index: fresh | budget: 5.6K/6.0K
```

**三条特色**：`reason:` 行标明每条证据靠什么召回；`[E*]` 编号是引用回验的基础；
`Missing Evidence` 诚实报缺口（不假装找到了）。

### `ask_project` → **已接 LLM（TASK-088，2026-09-14 合并）**

```python
# service/zace_service/routers/query.py（四分支，证据优先）
if not pack.answerable:            return _insufficient_package(...)   # D-24 不调 LLM
if provider is None:               return _degraded_response(...)      # 未配置
# 调用失败/超时 → _degraded_response；成功 ↓
return {"status": "answered", "answer": outcome.answer, ...}
```

配置全部走环境变量（`.env` 里已配好）：`ANSWER_BASE_URL` / `ANSWER_API_KEY` / `ANSWER_MODEL`，
另有内置默认值 `ANSWER_TIMEOUT_S=60` / `ANSWER_MAX_TOKENS=3072` / `ANSWER_TEMPERATURE=0.2`。
设置页（`/settings`）展示 embedding 与 LLM 的当前生效配置，**不泄露 key 任何片段**。

**实测**（编排者亲跑，对 zace 自身索引）：问「next_queries 如何渲染？」→
`status=answered`、2804 字回答、带 `[E6]`/`[E13]` 等引用、`citation_coverage=1.0`、`latency_ms=879`。

~~**TASK-088 就是把它接上**~~ —— **已完成（2026-09-14）**：设计定稿在
`docs/design/Module/04-AI总结.md`，配置项 `ANSWER_BASE_URL/API_KEY/MODEL` 全走环境变量，
设置页（`/settings`）展示当前生效配置。

### 架构浪费的修复现状（TASK-087/088 已落地）

| ContextPack 产出 | Agent 能看到 |
|---|---|
| `evidence[]`/`docs[]`/`missing_evidence[]`/`confidence` | ✅ |
| `next_queries[]` | ✅ **已渲染**（`### Suggested Next Queries` 节，TASK-087） |
| `answerable` | ✅ **已用于分支**（false → 短路包，不调 LLM） |
| `flows[]`（调用链） | ⚠️ 需图扩展命中，实测常为空（未改善） |

---

## 5. 关键约束（别踩）

### 质量参数冻结（R29/R30）

`docs_ratio=0.10`、`CONSENSUS_SCORE_RATIO=2.15`、`rerank` 权重等是 **smoke 集上的拟合值**，
**未经真实数据校准**。**不得基于现有测试集调参**；真实优化要等 TASK-093 的数据。

### 契约变更走 L1/L2/L3 流程

- **实施 AI 永不直接改** `docs/contracts/**`、`docs/design/**`、`zace_core/{types,interfaces,hashing}.py`；
- 需要新增字段/改签名 → 在任务卡"执行记录"写**契约变更申请**，停下来等编排者；
- **CF-05**（REST 路径与错误信封）、**CF-06**（MCP 工具 schema）是冻结合同。

### 一个工作区一个会话

**一个 AI 会话 = 一个独占 worktree（`zace-lane-<x>`）= 一个分支**。
在**主工作区**（`/home/xuwenzheng/2_github/AI/ACE/zace`）改代码是禁止的（只用于集成）。

```bash
cd /home/xuwenzheng/2_github/AI/ACE/zace
bash scripts/lane-worktrees.sh status              # 看哪个 lane 空闲
bash scripts/lane-worktrees.sh claim <lane> TASK-xxx
cd /home/xuwenzheng/2_github/AI/ACE/zace-lane-<lane>
git switch -c feature/task-xxx_<缩写><MMDD> main
# 干完：基线三条绿 → 回填卡片 → commit（不 push）→ release
```

**教训**（真实发生过）：多个会话共用一个目录时，`git commit` 提交到哪个分支取决于
"谁最后切了 HEAD"，曾导致提交错位、工作被卷进别人的提交。**务必用独立 worktree。**

### lane worktree 可能是旧提交

新建的 lane 处于 `detached HEAD`，可能**落后于 main 很多**（实测出现过停在 21 个提交之前、
连任务卡文件都不存在的 lane）。**开工前先 `git log --oneline -1` 核对**，不对就从 `main` 开分支。

### 基线三条（每次提交前必须绿）

```bash
uv run ruff check .
uv run python scripts/check_dependency_direction.py
uv run pytest -o addopts="" -q      # 注意：不加 -o addopts="" 看不到汇总行
```

前端：`cd web && npm run lint && npm test && npm run build`

---

## 6. 当前环境的事实（2026-09-14 核实）

| 项 | 值 |
|---|---|
| **仓库根** | `/home/xuwenzheng/2_github/AI/ACE/zace`（**2026-09-14 晚核对**；旧文档里的 `~/github/ACE/zace` 已不存在） |
| **泳道工作区** | `/home/xuwenzheng/2_github/AI/ACE/zace-lane-{a..j}` |
| Python | 3.12（uv **0.9.9** 管理） |
| Node / npm | v22.23.2 / 10.9.8 |
| **cargo** | ✅ **1.97.1 可用** —— Rust client 可本地构建（`cd client && cargo build --release`，实测 1m57s） |
| **docker** | ✅ **29.1.3 可用，daemon 在跑** —— TASK-092 可本地部分验证 |
| **Playwright** | ✅ chromium 已装（`~/.cache/ms-playwright/chromium-1243`）；`--with-deps` 需 sudo |
| **http_proxy** | ⚠️ 已设（`http://127.0.0.1:7890`）—— **连本机服务必须 `NO_PROXY=127.0.0.1,localhost`**（`.env` 里已配） |
| **embedding key** | ✅ `.env`（仓库根与每个 lane 都有，**已被 gitignore**）：Voyage `voyage-4-lite` 主路径 + 硅基流动 `bge-m3` 备选；两者实测 200 |
| **LLM key** | ✅ `.env` 的 `ANSWER_*`（xiugou / deepseek-v4.1-flash），实测 200 |
| **靶场** | `/home/xuwenzheng/2_github/Agent开发/hello-agents/hello-agents` @ `4f7682c`（**只读**！不要在里面建文件） |
| 磁盘 | 820G 可用 |

**`.env` 用法**（每个工位已铺好）：

```bash
set -a; source .env; set +a     # Voyage/LLM key + NO_PROXY 一次到位
```

> **注**：`.env` 含真实 key，**永不提交**（`.gitignore` 已排除）。新工位若缺 `.env`，
> 从主仓库复制（`cp ~/2_github/AI/ACE/zace/.env ../zace-lane-x/.env`）。

---

## 7. 本地怎么跑起来（2 分钟）

```bash
cd /home/xuwenzheng/2_github/AI/ACE/zace
set -a; source .env; set +a      # Voyage/LLM key + NO_PROXY

# 后端（云端形态，可看到登录/API Key/统计）
ZACE_LOCAL_MODE=false ZACE_REGISTER_OPEN=true ZACE_DATA_ROOT=/tmp/zace-dev \
  uv run zace-service serve --host 0.0.0.0 --port 8896

# 前端（另一个终端）
cd web && ZACE_WEB_API=http://127.0.0.1:8896 npx vite --port 5174 --host 0.0.0.0
# 浏览器打开 http://localhost:5174/
```

> **端口选择注意**：WSL 会误报某些高位端口"address already in use"（实测 8898/8901/18897）。
> 建议直接用 **18898/18896** 这类实测可用的端口，或先 `ss -ltn` 确认。

**Agent 接入用的地址是后端**（`http://localhost:8896`），**不是**前端端口（5174 只服务浏览器请求）。

```toml
# ~/.codex/config.toml
[mcp_servers.zace]
command = "npx"
args = ["zace-client", "--base-url", "http://localhost:8896", "--token", "zace_你的Key"]
startup_timeout_ms = 60000
```

> **首次提问会等一会儿**（几分钟量级，取决于仓库大小）：客户端会先扫描本地仓库、
> 增量上传、服务端对文件做 embedding，然后才检索。**第二次起只传改动文件，通常 1-3 秒。**

---

## 8. 已知缺口与风险

| # | 缺口 | 严重度 | 处置 |
|---|---|---|---|
| 1 | ~~MCP 面仍未做归属校验~~ **已修复**（TASK-089 已合并，实测 bob 越权两工具均拦） | ✅ | done |
| 2 | `/healthz` 免鉴权且**列出全部 projectId**（枚举面） | 🟡 | **未处理**（TASK-089 登记为未决，改 `ops.py` 属 TASK-090 领地） |
| 3 | ~~日志只在 stdout，无持久化~~ **已修复**（TASK-090，文件轮转 + trace id 查询） | ✅ | done |
| 4 | ~~`ask_project` 未接 LLM~~ **已修复**（TASK-088，实测 citation_coverage=1.0） | ✅ | done |
| 5 | ~~`next_queries` 已生成但不渲染~~ **已修复**（TASK-087） | ✅ | done |
| 5b | **无任何存储配额机制**（`grep quota` 零结果），用户要求超限时在 tool 内容里告警 | 🟡 | TASK-094 |
| 6 | 无 CI 覆盖的 e2e（需起服务造数据） | 🟢 | 未开卡 |
| 7 | 历史页逐项目拉明细（N 次请求） | 🟢 | 未开卡 |
| 8 | 参数冻结未解（质量优化受阻） | 🟡 | TASK-093 数据充分后由用户授权 |
| 9 | 多人共用同一仓库 → 只有第一个认领者能用（V1 简化） | 🟡 | 设计已记录（`org_id` 留 V2） |
| 10 | 无域名时 Caddy 自动 TLS 不可用 → key 明文暴露风险 | 🟡 | TASK-092 需给方案 |
| 11 | 未认证请求（401）的日志无 owner → 用户报错时若只给未认证请求的 id，管理员查不到 | 🟡 | TASK-090 登记为未决（V1 无角色体系） |
| 12 | `docs/contracts/openapi.yaml` 第 167 行有 YAML 语法瑕疵（未闭合引号）——**既有问题，非本轮引入**；项目用按缩进解析故不影响测试 | 🟢 | 未开卡 |

---

## 9. 协作纪律速查

| 规则 | 说明 |
|---|---|
| 一张卡一个会话 | 不并行做多卡；不顺手重构其它模块 |
| 只管清单内文件 | 任务卡的"交付物所有权"是硬边界；改公共文件先申请 |
| 不 push / 不切 main / 不 force push | 评审与合并由编排者做 |
| 完成即回填 | 卡片"执行记录" + `docs/tasks/README.md` 对应行改 `review` |
| 有疑问就停 | 契约/设计冲突、需求不明 → 写进"未决问题"并停下，不要自行拍板 |
| 不夸大验证 | "跑过了"必须有真实输出；没跑的明确写"未验证" |

---

## 10. 交接时的当前现场

- **工作区**：主工作区在 `main @ d5f7eb4`，干净；lane-a..d 挂着已合并分支（可 `remove` 或复用），
  lane-e 正被 TASK-091 占用，lane-f..j 空闲；
- **运行中的服务**：无（编排者已验证后清理；`ss -ltn | grep -E '1889[0-9]|5174'` 可查）；
- **临时数据根**：`/tmp/zace-*` 下有多个验证用数据根，**可安全删除**（不影响仓库）；
- **未提交改动**：无。
- **靶场状态**：`hello-agents` 已 checkout 到 `4f7682c`（golden 要求的 commit），
  工作区有 2 个未提交的代码改动（`ReAct.py` / `tools.py`，非密钥）——出题时注意。
  **曾经的密钥泄露已处置**（`.env copy` 恢复为上游占位符，备份在 `/tmp/hello-agents-env-backup/`）。

---

## 11. 下一步建议（给接手 AI）

1. **先读**：本文件 → `docs/tasks/README.md` → `docs/plan/orchestration.md`（泳道模式、契约流程）；
2. **挑卡**：TASK-087 / 088 / 089 / 090 / 091 五张**互相不冲突**，可同时派五个会话；
3. **TASK-094 必须等 TASK-090**（两者抢 `metadb.py`/`ops.py`，且 `request_id` 落库与
   TASK-090 的请求日志是同一件事的两半 —— 若 090 未开工，可直接把 094 §C 并入 090）；
4. **注意**：TASK-092（部署）**必须等 089/090 合并**，否则等于把越权面发布到公网；
4. **用户的下一步人工任务**：打磨工具返回内容、补真实问题、打磨 benchmark
   —— 这些依赖 087/088/091 的产出，做完后需要用户参与评审。
