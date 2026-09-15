# TASK-099：调用链埋点与用户级 LLM 配置

> 状态：review ｜ 阶段：Phase 4（M4）｜ 硬依赖：无 ｜ soft 依赖：TASK-100（前端已就绪，等待本卡的数据）
> 建议分支：`feature/task-099-callid-llm-config_<你的缩写><MMDD>`
>
> 交付物所有权：
> - `client/src/remote.rs`、`client/src/tools.rs`、`client/src/main.rs`（若需新增参数）
> - `service/zace_service/metadb.py`（迁移）
> - `service/zace_service/routers/{sync,query,ops,auth}.py`
> - `service/zace_service/runtime.py`、`service/zace_service/mcp.py`
> - `service/zace_service/llmconfig.py`（新建）、`service/zace_service/config.py`
> - `service/tests/`、`client/tests/`
> - **不改** `core/zace_core/**`（本卡纯服务端 + 客户端）
>
> 清单外文件不得改。**不新增 REST 路径**（复用现有端点加字段），见 §D 的契约说明。

## 背景

TASK-100 已完成前端改造（控制台「工具调用」卡 + 历史记录合并表 + 详情弹窗）。前端如实
标注了两处数据缺口，本卡负责补上：

| 前端现状（TASK-100 的诚实标注） | 本卡补什么 |
|---|---|
| 历史弹窗的「输出」只有证据概览，**没有 LLM 答案** | §A：落库 answer 正文 |
| 控制台「工具调用」无法区分"一次调用的 N 次初始化 + 1 次检索" | §B：callId 关联 |
| 设置页的 LLM 表单是 `disabled`（无写入端点） | §C：用户级 LLM 配置 |

用户 2026-09-14 的原始需求：

> "用户一次请求，可能包含几个仓库初始化的请求，和一个检索的请求，用户就知道初始化用了多长
> 时间，检索多长时间。"
>
> "设置页面，其中 LLM 修改成自定义的配置方式，模型名、URL、Key。目的是给用户自定义 LLM 的
> 选择……这个自定义是和用户绑定的，如果涉及到 ASK 工具调用，并且用户配置了的话，就用用户的
> 定义。"

## §A 落库 LLM 答案正文

**现状**：`query_audit` 表存了 `query`（输入全文）与 `evidence_json`（证据元数据），
但**不存 answer**（LLM 生成的答案正文）。前端弹窗因此只能展示"输入 + 证据清单"。

**要做的**：

1. `metadb.py` 的 `_AUDIT_MIGRATIONS` 追加两列（**必须走 ALTER 迁移路径**，不能改
   `CREATE TABLE`——旧库升级会因列不存在而失败，这是 TASK-094 §C 实测踩过的坑）：
   - `answer_text TEXT`——LLM 答案正文；未走 LLM（`answerable=false` 短路）时为 `NULL`
   - `answer_status TEXT`——`answered` / `insufficient_evidence` / `degraded`
2. `record_query()` 追加对应参数（**带默认值**，向后兼容既有调用方与测试）
3. `QueryAuditRecord.to_json()` 输出 `answerText` / `answerStatus`
4. `routers/query.py` 的审计写库点传入这两个值（`ctx` 里已有 status 与 answer）
5. **隐私与体积纪律**：
   - `answer_text` **不受** `redact_text` 影响（它是 LLM 输出，不含用户 key）；但**长度上限
     必须卡**——超过 `ANSWER_STORE_MAX_CHARS`（建议 20000）截断并追加 `…（已截断）`，
     防止单条记录撑爆库
   - 答案里的证据引用标记（`[E3]` 等）原样保留——前端要展示它

**为什么落库而不是只靠 `evidence_json` 反推**：LLM 输出不可重算（同样的输入可能给出不同答案，
且 provider 可能已换），"事后补算"是幻觉。要能回看就必须落库。

## §B callId：把 N 次初始化 + 1 次检索串起来

### §B-1 问题

```
客户端（一次 Agent 调用）              服务端看到的
────────────────────────────────────────────────────────
扫描仓库
POST /api/sync/batch-upload   ────→  一次独立请求 → 一条 index_runs
POST /api/sync/batch-upload   ────→  一次独立请求 → 一条 index_runs
POST /api/sync/batch-upload   ────→  一次独立请求 → 一条 index_runs
POST /api/query/search        ────→  一次独立请求 → 一条 query_audit
```

服务端**不知道**这几条属于同一次调用。

### §B-2 方案（用户 2026-09-14 拍板：客户端传 callId）

> **实施前已核验的事实**（编排者 2026-09-14 读代码确认，本卡据此设计）：
>
> - `service/zace_service/app.py` 的 `_request_context` 中间件**已经支持客户端传入**
>   `X-Request-Id`：`request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]`
>   （第 163 行），并把同值写回响应头。
> - `query_audit.request_id` 已落库（TASK-094 §C），但 **`index_runs` 没有任何请求关联列**。
> - 客户端（`client/src/*.rs`）目前**不发** `X-Request-Id`。
>
> 因此**不需要新增请求头**——直接复用 `X-Request-Id` 承载 callId，
> 省掉一个契约面（§B-4 的 L2 疑虑随之消失）。

1. **客户端**：每次 `search_context` / `ask_project` 调用开始时生成一个 **callId**
   （建议：`{unix_millis}-{8位随机十六进制}`；实现随机部分时可复用已有依赖，
   **不新增 crate**），该次调用的**所有** HTTP 请求（batch-upload / deletions /
   checkpoint / query）都带上请求头 `X-Request-Id: <callId>`。
2. **服务端**：
   - `index_runs` 加 `call_id TEXT` 列（走 ALTER 迁移，**不能改 CREATE TABLE**）
   - `record_index_run()` 追加 `call_id` 参数（默认 `None`，向后兼容）
   - 索引路径把**当前请求的 requestId** 写进去（从 contextvar 取；
     `runtime.py` 的 `_record_ingest_run` 在请求线程内，能拿到）
   - 新增 `GET /api/calls/{callId}` 返回该次调用的**完整时间线**（初始化 + 检索，按时间排序）
3. **前端**（本卡可只做数据层，UI 收尾另开小卡）：

   历史页按 `callId` 分组，把"一次调用"折叠成一行，展开看到 N 次初始化 + 1 次检索；
   控制台的"平均耗时"可按调用维度计算（`总耗时 = Σ初始化 + 检索`）。

### §B-3 设计裁定：callId 存在哪个字段

`query_audit.request_id` 语义是"**本次 HTTP 请求**的 trace id"（与响应头 `X-Request-Id` 同源，
TASK-090 的 `/api/request-log/{id}` 依赖它）。本卡**不新引入 callId 字段**，而是：

| 字段 | 语义 | 谁生成 | 用途 |
|---|---|---|---|
| `query_audit.request_id` | 本次检索请求的 trace id | 客户端（可选）或服务端 | 日志查询（TASK-090）+ **本卡的分组键** |
| `index_runs.call_id` | **同一次 Tool 调用**的 id | 客户端（复用 `X-Request-Id` 头） | 本卡的分组键 |

**关键点**：客户端在同一次 Tool 调用里发**同一个** `X-Request-Id`，于是：

- 服务端的 `query_audit.request_id` = 该 callId（客户端传的）
- 服务端的 `index_runs.call_id` = 同一个 callId
- 两者天然相等，**不需要额外的字段与映射**

代价（必须写进报告）：同一次调用的 N 个 HTTP 请求共享一个 requestId，
因此 **TASK-090 的日志查询会把这 N 条日志归为同一条**——实际上这正是需要的
（用户报错时给的就是 callId，要看到完整链路）。但要注意：

> **命名不一致的代价**：`index_runs` 叫 `call_id`、`query_audit` 叫 `request_id`，
> 两者语义已经统一（都是 callId）。若你（实施 AI）认为应当**统一列名**，
> 可改为给 `query_audit` 也加 `call_id` 列（保留 `request_id` 不动）——
> 二选一，**在报告里说明你的选择与理由**。

> **兼容性**：旧客户端不发 `X-Request-Id` → 服务端自造一个（现有行为），
> `index_runs.call_id` 为该值或 `NULL`。前端按"无关联就每行独立展示"降级。

### §B-4 请求头是否属于契约冻结范围

**已核验**（编排者 2026-09-14）：`docs/contracts/openapi.yaml` 里 grep `headers` / `Authorization`
**无匹配**——CF-05 定义的是 body 与响应字段集，请求头**不在冻结范围**。
`X-Request-Id` 已是既有实现（`app.py:44`），本卡只是让客户端开始发它。

因此本卡对 `X-Request-Id` 的改动**不需要 L2 申请**，但报告里要如实说明"客户端开始发送
该头，且同一次调用内 N 个请求共享同值"这一语义变化。

## §C 用户级 LLM 配置

### §C-1 需求

用户在设置页填**模型名 / 接口地址 / API Key**，绑定到**自己的账户**；调用 `ask_project` 时，
若该用户配了 LLM 就用用户的，否则回落服务端默认（环境变量）。

### §C-2 存储

新建 `service/zace_service/llmconfig.py` + 迁移一张表：

```sql
CREATE TABLE IF NOT EXISTS user_llm_config (
  user_id     TEXT PRIMARY KEY,
  model       TEXT NOT NULL,
  base_url    TEXT NOT NULL,
  api_key     TEXT NOT NULL,      -- 明文存储（见下方裁定）
  created_at  INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL
);
```

**API Key 明文存储的裁定**（必须写进卡内执行记录与设计文档）：

- 本服务**单用户自部署**是主场景（`ZACE_LOCAL_MODE`），环境变量里的 `ANSWER_API_KEY`
  本身就是明文；DB 文件与 `.env` 在同一台机器、同一个信任域内，加密存储**不增加实际安全性**
  （密钥仍要放在某处，且进程必须能解密）；
- 但**必须做到**：① 任何 API 响应**绝不返回 key 的任何部分**（含长度、前缀）；
  ② 日志与错误信息走 `redact_text`；③ 卡内如实说明"明文存储"而不是暗示已加密。
- 若将来要支持多租户，**再开卡**做加密（那时需要引入密钥管理，属独立议题）。

### §C-3 端点

**不新增路径**——扩展现有端点（与 TASK-088 §F 的同一思路，零契约改动）：

| 端点 | 扩展 |
|---|---|
| `GET /api/meta` | `config.llm` 追加 `source: "user" \| "server"`（当前生效的是哪一份） |
| `PUT /api/auth/llm-config` | **新增**（这是本卡唯一的新路径，见下） |

> 为什么 `PUT /api/auth/llm-config` 是新路径：它承载**写操作**，语义与 `/api/auth/*` 的
> "账户自身设置"一致（同组的 `POST/DELETE /api/auth/tokens` 已是账户级写操作）。
> 它会进 CF-05 的路由白名单 → **属 L2 契约申请**，按 §D 流程走。

#### §C-3-1 新路径必须同步两处（**实测踩过的坑**）

`service/tests/test_skeleton.py:56` 的 `test_openapi_paths_match_cf05_contract` 会对比
**应用实际暴露的路径集**与**契约集合 ∪ 扩展白名单**，多一个就失败：

```python
TASK_EXTENSION_PATHS: frozenset[str] = frozenset({
    "/api/projects/attach", ..., "/api/request-log/{requestId}",
})
expected = set(contract_paths) | set(TASK_EXTENSION_PATHS)
assert set(app.openapi()["paths"]) == expected
```

因此新增两个路径时**必须同时改三处**（否则测试一定红）：

1. `docs/contracts/openapi.yaml`（契约，**需编排者批准后才改**，见 §D）；
2. `service/tests/test_skeleton.py` 的 `TASK_EXTENSION_PATHS`（注释里要写哪张卡授权）；
3. `service/zace_service/routers/*.py`（实际路由）。

> **实施顺序建议**：先在报告里提交 L2 申请 + 把两处改动写好（含测试），
> 等编排者回复后再提交。若你判断可以先行实施，则**必须**在报告里明确列出
> "我已同时修改契约文件与白名单，待编排者确认"，不得静默改动。

**请求体**：`{model, baseUrl, apiKey}`（三者必填；`apiKey` 传空串表示保持不变）
**响应**：`{model, baseUrl, apiKeyConfigured: true, source: "user"}`
**删除**：`DELETE /api/auth/llm-config` → 回落服务端默认

### §C-4 生效链路

`ask_project` 与 `POST /api/query/ask` 都要用同一份解析逻辑：

```
resolve_llm_config(user_id, settings) -> LlmConfig
    user 配置存在 → 用它
    否则        → settings 的 ANSWER_* （环境变量）
```

**MCP 侧的用户身份**：`mcp.py` 已有 `_user` contextvar（TASK-089 §A/B 引入，承载已认证用户）。
若 MCP 请求无用户（本地模式）→ 用服务端默认。

> **MCP 面的配额快照问题**（TASK-094 的已知限制）：MCP provider 在 `build_mcp` 时构造，
> 改配置需重启。本卡**不修**这个问题（它涉及 provider 生命周期重构，属独立议题），
> 但要在设置页文案与报告里如实说明。

### §C-5 前端

TASK-100 已把表单结构写好（`web/src/pages/SettingsPage.tsx`，三个字段 + 保存/清除按钮，
当前 `disabled`）。本卡只需把 `CAN_SAVE_USER_LLM` 改为 `true` 并接上端点——
**前端改动应在 5 行以内**，若发现需要大改，说明接口设计与前端预期不符，**先报告再动手**。

## §D 契约影响与申请

本卡会触及 CF-05。**注意 §C-3-1 的路径冻结测试**：新路径必须同时更新契约文件、
`TASK_EXTENSION_PATHS` 白名单与实际路由，否则 `test_skeleton.py` 必红。

| 变更 | 是否改 `docs/contracts/**` | 流程 |
|---|---|---|
| `query_audit` 加 `answer_text` / `answer_status` | 否（**响应字段**新增） | 直接做，报告里列出 |
| `index_runs` 加 `call_id` | 否（**表结构**，非 CF-05 响应面） | 直接做 |
| `GET /api/meta` 的 `config.llm` 加 `source` | 否（响应字段新增） | 直接做 |
| `GET /api/calls/{callId}` | **是**（新路径） | **L2 申请** |
| `PUT/DELETE /api/auth/llm-config` | **是**（新路径） | **L2 申请** |
| 客户端开始发 `X-Request-Id` | 否（请求头不在冻结范围，见 §B-4） | 直接做，报告说明语义变化 |

**L2 申请格式**（写在报告「契约影响」节，由编排者审定后再改契约文件）：

```
## L2 契约申请
- 变更：新增 GET /api/calls/{callId}、PUT/DELETE /api/auth/llm-config
- 动机：（本卡 §B/§C 的用户需求）
- 影响面：CF-05 路由白名单、web 端调用
- 替代方案：能否不加路径？（说明为何复用现有端点不可行）
```

> **实施 AI 不得直接改 `docs/contracts/**`**——只提交申请，等编排者裁定。

## §E 测试要求

- **迁移必须可重复执行**：旧库（无新列）升级 → 数据保留 → 新列 `NULL`；再次打开不报错。
  写一个用真实旧 schema 建库再打开的用例（照 TASK-094 §C 的做法）。
- **callId 关联**：发 3 次 batch-upload + 1 次 search（都带同一 header）→
  `GET /api/calls/{id}` 返回 4 条且按时间排序；**不带** header 时各记录 `call_id` 为
  `NULL` 且端点返回 404/空（按你的设计如实选一个）。
- **LLM 配置隔离**：用户 A 配了 LLM、用户 B 没配 → B 调用 `ask_project` 时用服务端默认；
  A 的 key **不出现在**任何响应里（含 `/api/meta`、日志、错误栈）。**这条必须有专门的断言。**
- **answer 落库**：`answerable=false`（短路，不调 LLM）时 `answer_text` 为 `NULL`，
  但 `answer_status="insufficient_evidence"`——**不把"没调 LLM"记成"调了但空答案"**。
- 客户端：cargo test 覆盖 callId 生成与请求头注入（可用 wiremock/mockito，按现有测试风格）。

## §F 验收命令

```bash
# 服务端
cd /path/to/zace
env -u EMBED_MODE uv run pytest -o addopts="" -q          # 全量（基线 983 passed, 2 skipped）
cd client && cargo test                                    # 客户端
uv run ruff check .
uv run python scripts/check_dependency_direction.py

# 前端（若改了 web/）
cd web && npm run lint && npx tsc --noEmit && npm test && npm run build
```

## §G 真实场景验证（**必须**）

用 `~/.zace/cockpit-agents` 索引 + `cockpit-agents-py` 仓库跑一次真实调用：

1. 客户端发起一次 `search_context` → 抓取实际发出的 HTTP 请求，确认**所有请求都带同一个
   `X-Zace-Call-Id`**（贴出请求头日志）；
2. 服务端查库确认 `index_runs` 与 `query_audit` 的 `call_id` 一致；
3. `GET /api/calls/{callId}` 返回完整时间线（贴出响应）；
4. 设置用户 LLM → 调 `ask_project` → 确认用的是用户配置（贴出实际模型名）；
5. 删除用户配置 → 再调 → 确认回落服务端默认。

**不允许**只用 mock 单测交付——本卡的核心价值是"真实链路能串起来"。

## 明确不做

- **不做** embedding 的用户级配置（用户 2026-09-14 拍板只做 LLM）；
- **不做** MCP provider 的热重载（已知限制，如实记录）；
- **不改** `request_id` 的既有语义（见 §B-3）；
- **不做**前端的历史页按 callId 分组 UI（本卡交付数据层与端点；UI 若时间允许可做，
  但要单独说明并在报告中给出截图）；
- **不加密** API Key（见 §C-2 的裁定与理由）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板，并**必须包含**：

- §A/§B/§C 三部分的实际实现与**迁移前后证据**（旧库升级的查库输出）；
- §B-4 与 §D 的契约核验结论（请求头是否在冻结范围）与 L2 申请；
- §G 的真实场景验证全部 5 项（含抓取的请求头）；
- LLM key 隔离的**具体断言代码**与运行输出；
- 与设计偏差、未决问题（尤其：明文存储的评价、MCP 快照限制的实际影响）。

## 执行记录

### 2026-09-14 ｜ 泳道 A ｜ 分支 `feature/task-099-callid-llm-config_xwz0914` ｜ 状态 review

**一句话**：三个缺口（答案落库 / callId 关联 / 用户级 LLM 配置）全部实现，并在真机真实链路
（`~/.zace/cockpit-agents` 索引 + `cockpit-agents-py` 仓库 + 真实 LLM）验证通过。

#### 验收命令与结果

| 命令 | 结果 |
|---|---|
| `env -u EMBED_MODE uv run pytest -o addopts="" -q` | **1014 passed, 2 skipped**（基线 983+2；本卡新增 31 条） |
| `uv run ruff check .` | All checks passed |
| `uv run python scripts/check_dependency_direction.py` | 依赖方向检查通过 |
| `cd client && cargo test` | **56 passed**（基线 50；新增 6 条） |
| `cd web && npm run lint && npx tsc --noEmit && npm test` | 全绿，**66 passed**（基线 63；新增 3 条，改写 1 条） |

#### §A 答案落库（迁移前后证据）

- `query_audit` 新增 `answer_text TEXT` / `answer_status TEXT`，**走 ALTER 路径**（`_AUDIT_COLUMNS`），
  未改 `CREATE TABLE`；`record_query()` 追加同名参数（带默认值，向后兼容）。
- 旧库升级实测（用真实旧 schema 建库后打开）：

```
BEFORE runs: ['id','project_id','state','started_at','finished_at','duration_ms',
              'files_total','files_processed','chunks','errors','error_text']
BEFORE audit: answer_text 存在? False
AFTER runs call_id: True
old run:  {'runId':1,'state':'done','durationMs':4000,'callId':None}      ← 旧行 NULL，不编造
old audit:{'queryId':1,'query':'旧查询','answerText':None,'answerStatus':None}
idempotent reopen OK    count: 1
```

- 真实 LLM 落库（3 条走 LLM + 1 条短路；`answer_text` 长度单位为字符）：

```
id  mode  answer_status          chars  head
1   fast                                                       ← search 不落正文（设计如此）
2   deep  insufficient_evidence                                ← 正文 NULL
3   deep  answered               1346   ## Answer / 依据现有证据，CapabilityRegistry 的注册方式是：**先实例化…
4   deep  answered               1579   ## Answer / 依据现有证据，`CapabilityRegistry` 的注册方式是：实例化后调用…
5   deep  answered               1105   ## Answer / 依据现有证据，CapabilityRegistry 被定位为**启动阶段的能力注册所有者…
```

- 长度上限 `ANSWER_STORE_MAX_CHARS = 20000`（+ `…（已截断）` 标记），有单测钉住。
- **`search`（fast）不落正文**：它的输出是含源码的渲染包，落库会破 Module/04 §8 的“不存源码内容”。

#### §B callId 关联

**列名选择与理由（卡内 §B-3 二选一）**：采用 **`index_runs.call_id` + 复用 `query_audit.request_id`**，
不为 `query_audit` 新加 `call_id` 列。理由：两者语义已经统一（都是 callId），同一值由客户端同一个
`X-Request-Id` 头承载；再加一列会产生“同一事实两个字段”，需要决定谁是权威、何时同步，
而收益只是名字好看。代价（已写入报告）：命名不齐会让人误以为它们无关——已在 `_INDEX_RUN_COLUMNS`、
`record_index_run`、`routers/ops.py` 三处注释里交叉指明，并在文档字符串里说明“天然相等”。

**抓取的真实请求头（§G-1，真机客户端 → 真机服务）**：一次 `search_context` 共 6 个请求，全带同一 callId：

```
POST /api/projects/resolve   X-Request-Id=1789383613328-8bd08eeaec028787
POST /api/sync/batch-upload  X-Request-Id=1789383613328-8bd08eeaec028787
POST /api/sync/batch-upload  X-Request-Id=1789383613328-8bd08eeaec028787
POST /api/sync/batch-upload  X-Request-Id=1789383613328-8bd08eeaec028787
POST /api/sync/checkpoint    X-Request-Id=1789383613328-8bd08eeaec028787
POST /api/query/search       X-Request-Id=1789383613328-8bd08eeaec028787
```

**查库证据（§G-2）**：两表关联字段同值（SQL 断言输出 `MATCH: 两张表的调用关联字段同值 = …`）：

```
id  project_id        state  call_id                         duration_ms  files_total  chunks
1   8e69da62f37e5783  done   1789383613328-8bd08eeaec028787  3000         113          3416
2   8e69da62f37e5783  done   1789383613328-8bd08eeaec028787  2000         119          3416
3   8e69da62f37e5783  done   1789383613328-8bd08eeaec028787  2000         55           3416

id  mode  request_id                      answerable  answer_status
1   fast  1789383613328-8bd08eeaec028787  1
```

**`GET /api/calls/{callId}` 真实响应（§G-3）**：4 条 entry（3 index + 1 query）按时间排序，
`totals = {indexDurationMs: 7000, queryLatencyMs: 845, totalMs: 7845, indexRuns: 3, queries: 1}`，
`withoutCallId: 0`。

#### §C 用户级 LLM 配置

- 新建 `llmconfig.py`：`resolve_llm_config(settings, user_id, db)` 是 REST/MCP **共用的唯一解析入口**；
  用户配置优先，否则回落 `ANSWER_*`；`ResolvedLlmConfig.to_public_json()` 是唯一允许出网的形态。
- 端点：`PUT /api/auth/llm-config`（`{model, baseUrl, apiKey}`；**`apiKey` 空串 = 保持不变**）、
  `DELETE /api/auth/llm-config`（幂等 204）；`GET /api/meta` 的 `config.llm` 追加
  `source: "user" | "server"` 与 `missingKeys`。
- **key 隔离的专门断言**（`test_key_is_never_echoed_by_any_endpoint`）：

```python
secret = "sk-zace-t099-SECRET-abcdefghijklmnop"
env.client.put("/api/auth/llm-config", json={"model": "secretive-model",
    "baseUrl": "https://llm.internal.example/v1", "apiKey": secret})
assert secret not in saved.text
for endpoint in ("/api/meta", "/api/auth/me", "/api/usage/summary", "/api/account/overview"):
    assert secret not in env.client.get(endpoint).text          # 全绿
    assert secret[:12] not in env.client.get(endpoint).text     # 前缀也不给
assert str(len(secret)) not in saved.text                        # 长度也是信息
assert env.db.get_llm_config("local").api_key == secret          # 库里仍是明文（本卡裁定）
```

另有三条同类断言：保存**之后**的 `/api/meta`、400 错误响应、以及日志面（`caplog`）均不含 key；
同时断言日志确实记了这次变更（防“靠什么都不记来作弊”）。

#### §C-3-1 契约路径三处改动清单

| 处 | 文件 | 状态 |
|---|---|---|
| ① 契约 | `docs/contracts/openapi.yaml` | **未改**（实施 AI 不得改，待编排者按 §D 申请裁定） |
| ② 白名单 | `service/tests/test_skeleton.py::TASK_EXTENSION_PATHS` | **已改**（+`/api/calls/{callId}`、`/api/auth/llm-config`，注释写明 TASK-099 §B/§C 授权） |
| ③ 实际路由 | `service/zace_service/routers/{ops,auth}.py` | **已改**（`/api/calls/{callId}` GET；`/api/auth/llm-config` PUT+DELETE） |

→ **我已同时修改“白名单 + 实际路由”，契约文件保持未改（符合契约纪律）**，等编排者把这两个路径写入
`docs/contracts/openapi.yaml`。路径冻结测试 `test_openapi_paths_match_cf05_contract` 当前为绿。

#### §D L2 契约申请（等编排者裁定）

```
## L2 契约申请
- 变更：新增 GET /api/calls/{callId}、PUT/DELETE /api/auth/llm-config
- 动机：
  · GET /api/calls/{callId}：用户 2026-09-14 要“一次 Tool 调用的完整视图”（N 次仓库初始化 + 1 次检索
    的耗时归总）；服务端此前无法把这几条记录串起来。客户端现在用 X-Request-Id 承载 callId，
    该端点把 index_runs.call_id 与 query_audit.request_id 合并成一条按时间排序的时间线。
  · PUT/DELETE /api/auth/llm-config：用户要“设置页自定义 LLM（模型名/URL/Key），与用户绑定，
    ASK 工具调用用用户配置”。此前没有任何配置写入端点，表单只能 disabled。
- 影响面：CF-05 路由白名单（两个新路径）、web 端调用（SettingsPage + api/client.ts）、
  TASK-090 的日志查询语义（同一次调用的 N 个请求共享一个 requestId，因此“按 trace 查日志”
  会把它们归到同一条——这正是需要的：用户报错时给的就是 callId）。
- 替代方案：
  · 时间线能否不加路径？不能。现有端点都是单项目维度（/api/projects/{id}/index-runs），
    而一次调用可能同时初始化多个仓库、且必须与检索审计合并——跨项目归总是新语义。
  · LLM 配置能否复用现有端点？不能。POST /api/auth/tokens 是“凭证”语义，字段与生命周期都不同；
    /api/meta 是只读公开端点。唯一合理位置就是 /api/auth/*（与 tokens 同级的“账户自身设置”）。
```

#### §B-4 请求头是否在契约冻结范围（重复核验）

已核验并写成测试 `test_request_header_is_not_part_of_the_frozen_contract`：
`docs/contracts/openapi.yaml` 中 `x-request-id` / `headers:` / `authorization` **全部无匹配**
→ 请求头**不在** CF-05 冻结范围，客户端开始发送该头**不需要 L2 申请**。
语义变化（如实说明）：客户端在**同一次 Tool 调用**里给所有请求发**同一个**值，
因此服务端会把这一串请求视为同一次调用（TASK-090 的日志查询随之把它们归为一条）。

#### §G 真实场景 5 项验证

| # | 验证项 | 结果 |
|---|---|---|
| 1 | 客户端发起 `search_context` → 抓取实际请求头 | ✅ 6 个请求（1 resolve + 3 batch-upload + 1 checkpoint + 1 search）全带同一 callId（见上方原文） |
| 2 | 查库确认两表关联字段一致 | ✅ SQL 断言输出 `MATCH`；真实数据见上方两张表 |
| 3 | `GET /api/calls/{callId}` 完整时间线 | ✅ 4 条 entry、按时间排序、totals 正确（见 §B 节） |
| 4 | 设置用户 LLM → `ask` 用用户配置 | ✅ 真实 LLM 返回 `status=answered`、**`meta.llmModel = deepseek-v4-flash`**（用户配置值，服务端默认是 `deepseek/deepseek-v4.1-flash`） |
| 5 | 删除用户配置 → 回落服务端默认 | ✅ `DELETE` → 204；再调 `meta.llmModel = deepseek/deepseek-v4.1-flash` |

真实素材：`~/.zace/cockpit-agents` 索引（287 files / 3416 chunks / 16176 edges）+ `cockpit-agents-py` 仓库
+ `ANSWER_*` 指向的真机 LLM（`http://154.12.34.214:8080/v1`）。服务用 `zace-service local`
（MetaDB 已 attach）起在 19011/19012，客户端用 `client/target/release/zace-client` 走 stdio。

**为验证 §A 的“没调 LLM 就不是空答案”**，真实跑出一条 `answerable=false`：
`status=insufficient_evidence`、`llmModel=None`、库里 `answer_text IS NULL` 且 `answer_status='insufficient_evidence'`。

#### 与设计偏差

1. **`audit.py` 越出交付物清单**（清单只列 `routers/query.py`）。原因：真正调
   `db.record_query()` 的是 `audit.py`，不碰它就无法把 `answer_text` 传到库。改动是**最小**的：
   新增两个可选 kwarg（`answer_text` / `answer_status`）+ 透传 + 一个 `truncate_answer()`。
   已在用户确认下实施。
2. **`web/` 越出交付物清单**。§C-5 明确要求把 `CAN_SAVE_USER_LLM` 置 true 并接端点，清单却未列 `web/`。
   已在用户确认下实施；改动集中在 `SettingsPage.tsx` + `api/client.ts`（类型与两个 API 函数）+ 对应测试。
3. **本地模式允许保存用户级 LLM 配置**（与 `tokens` / `register` 的 403 `local_mode` 先例不同）。
   理由与实现见下一条及 `routers/auth.py` 模块 docstring。已在用户确认下实施。
4. **`meta.llmModel` 为新增的响应字段**（不在卡内 §C-4 枚举里）。理由：让 §G-4/§G-5 与设置页
   能**直接看到实际生效的模型名**，而不是靠“配过就相信它生效了”；模型名不是 secret。

#### 未决问题

1. **本地模式为何与 `tokens` 不同**：`_require_remote` 在 `tokens`/`register` 上返回 403 `local_mode`，
   而本卡的 `llm-config` 在本地模式可用。裁定依据（`auth.llm_owner`）：本地单用户自部署是主场景，
   用户要的正是“配自己的 LLM”；强行要求开户+登录是把实现约束当产品约束。
   实现上仍是同一套归属逻辑（本地模式的隐式账户提供稳定 `user_id="local"`，`user_llm_config` 表无外键）。
   **若编排者认为应与 tokens 保持一致，改动点只有 `routers/auth.py` 的两处 `_require_remote` 调用。**
2. **明文存储 §C-2 裁定的评价**：本卡照裁定实施（明文 `api_key`），并且做到了“不出网 + 不进日志”。
   但**建议后续改进**：① `.env` 的 `ANSWER_API_KEY` 与 DB 明文属同一信任域的说法成立，
   然而 DB 会被**备份/复制**（本次验证就 `cp` 过一份），而 `.env` 通常在 `.gitignore` 之外另行保管；
   ② 若将来支持多租户或托管部署，明文必须改为加密（需引入密钥管理，独立议题）。
3. **MCP 快照限制的实际影响**：`build_mcp` 在 `create_app` 时把 `Settings` 包进闭包，
   但本卡把 provider 解析推迟到**每次 tool 调用**（`_provider_resolver` → `provider_for_request`），
   并按 `(settings, user_id, 配置 updated_at)` 失效缓存，因此**用户 LLM 配置变更在 MCP 面也无需重启**。
   仍存在的限制：`Settings` 本身（超时/max_tokens/温度）与存储配额快照需重启才变——与 TASK-094 同源，
   不属本卡范围。
4. **`query_audit` 未落模型名**：`meta.llmModel` 只在响应里，历史表看不到“这条是哪个模型答的”。
   加列属表结构扩展，需单独评估（卡内未要求）。
5. **同一次调用共享 requestId 对 TASK-090 的影响**：`/api/request-log/{requestId}` 会把该次调用的
   6 条日志全部返回（`relatedLogs` 上限 `MAX_RELATED_LOGS`）。实测该上限足够覆盖本次的 6 条；
   若将来一次调用请求数超过上限，日志会被截断——需要时再评估上限。
6. **图（flows）未在本次检索结果中出现**：`### Flow` 节的产出条件是
   `build_flows` 能沿 `callees` 走出 ≥2 节点，而本次真实查询命中的 seed 是类定义、
   且同一次输出如实报了 `unresolved_refs status=failed`（59 个未解析引用）——
   图扩展因此容易在第一步就断链。这**不是本卡引入的问题**，但用户关心，
   建议单开一张卡验证并改进（例如对类符号补 `__init__` 出边种子）。

#### 建议复核点

1. `service/tests/test_chain_and_llm_config.py` 的 31 条用例（尤其迁移、key 隔离、§G 断言）；
2. `git diff` 的 `metadb.py` 迁移段：确认只加列、未改既有 DDL 语义；
3. `routers/auth.py` 的 `llm-config` 两个端点（尤其 `apiKey` 空串语义与 400 分支）；
4. `llmconfig.py` 的 `provider_for_request` 缓存键与测试接缝（`app.state.answer_provider`）；
5. 契约文件写入这两个路径后，`test_skeleton.py` 的白名单应与之一致（互不冲突）。
