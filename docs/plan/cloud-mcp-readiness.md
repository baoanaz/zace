# 云端 MCP 就绪度盘点与远端身份预研（TASK-051 交付物）

> 编制：实施 AI（TASK-051，分支 `feature/task-051_xwz0913`）｜ 日期：2026-09-13
> 性质：**只读诊断报告**，不含任何代码改动。所有结论均带实测证据与代码行号锚点。
> 被测版本：`main` @ `42587cf`（含 TASK-048）。
> 目标形态依据：`docs/design/Background/01-notace-tool-rs.md`（MCP 最终形态 = 本地 Rust client：
> stdio 对编辑器 + HTTPS 对远端 service；本地 MCP（service 直出 Streamable HTTP）仅作短期验证，R38）。
> 消费者：编排者（据此裁定契约级别、拆分 TASK-040R 系列卡）。

## 0. 一句话结论

**服务端的"同步面"已经为云端备好了（上传/删除/checkpoint/status 全部可用且有端到端测试），
但"检索面"与"接入面"各有一个阻断级缺口**：

1. **A1（安全，最高优先级）**：非本地模式下**没有任何鉴权**——不带凭据、甚至带**无效**凭据都能检索成功，
   而 `/healthz` 自报 `auth: enabled`；
2. **A2（功能阻断）**：CF-06 冻结的 `project_root` 在云端无法定位项目（服务端没有该目录），
   而 CF-05 已有可用的 `projectId` 通路——**MCP 面缺一个入口参数**。

**好消息**：A2 有一个**零契约变更**的解法（方案乙），TASK-040R 不必等契约流程即可开工。

---

## 1. A1：云端模式下无鉴权（阻断级 · 安全）

### 实测（`ZACE_LOCAL_MODE=false`，端口 8901）

```console
$ curl -s http://127.0.0.1:8901/healthz
localMode= False  auth= enabled              ← 自报"鉴权已启用"

$ # 不带任何 Authorization 头
$ curl -s -o noauth.json -w 'HTTP状态码=%{http_code}\n' \
    -X POST http://127.0.0.1:8901/api/query/search \
    -H 'Content-Type: application/json' \
    -d '{"projectId":"b2df0aa8248b6010","query":"刷新 token"}'
HTTP状态码=200
响应键= ['markdown', 'meta']
md前80字= '## Relevant Context\n### Code\n[E1] SessionStore.refresh_token — src/session.py:1-'

$ # 带一个明显无效的 Bearer token
$ curl -s -o /dev/null -w 'HTTP状态码=%{http_code}\n' \
    -X POST http://127.0.0.1:8901/api/query/search \
    -H 'Authorization: Bearer totally-invalid-token-xyz' \
    -H 'Content-Type: application/json' \
    -d '{"projectId":"b2df0aa8248b6010","query":"刷新 token"}'
HTTP状态码=200                             ← 无效凭据同样放行

$ # MCP 面
is_error = False （无凭据即调用成功）

$ curl -s -X POST http://127.0.0.1:8901/api/auth/login -d '{}'
HTTP状态码=501 {"error":{"code":"not_implemented", ...}}   ← 鉴权尚未实现（M2c）
```

### 代码锚点

| 位置 | 事实 |
|---|---|
| `service/zace_service/routers/ops.py:43` | `"auth": "disabled(local)" if settings.local_mode else "enabled"` —— **按模式字符串硬编码**，与真实鉴权状态无关 |
| `service/zace_service/deps.py` | 全文件无任何凭据校验；`require_project_id` 只做"项目是否存在" |
| `service/zace_service/routers/query.py:150` | `if not settings.local_mode: return None` —— 非本地模式**只是跳过懒重扫**，不是拒绝请求 |
| `service/zace_service/mcp.py:186` | Origin 防护"保持 SDK 默认" + 注释明确"本地单用户模式下这是唯一挡住浏览器访问本机服务的机制" |

### 风险判定

- **当前不算漏洞**：`serve` 默认绑 `127.0.0.1`（`config.py` `DEFAULT_HOST`），只监听本机；
  SDK 的 Origin 白名单也挡浏览器跨站请求。
- **一旦上云（VPS / 0.0.0.0 / 反向代理）就是完全开放**：任何人拿到 URL 即可检索他人源码。
- **`auth: enabled` 的自述是"诚实性"缺陷**：运维与 TASK-040R 的 client 都可能据此误判"服务已鉴权"，
  从而不带 token 上线。**建议在 A1 修复前，先让 `/healthz` 如实报告 `"auth": "not_implemented"`**。

### 处置建议（供编排者裁定）

1. **即刻（一行文档级）**：把 `/healthz` 的 `auth` 值改为诚实值，并写入部署前置条件（未鉴权前禁止非回环绑定）。
2. **M2c 前必须完成**：TASK-060（token+session）/ TASK-061（租户双层）**是云端 MCP 的硬前置**——
   建议把它们从"视情况"提升为"TASK-040R 的硬依赖"，否则 Rust client 接的是裸服务。

---

## 2. A2：云端 MCP 缺少可用的 projectId 入口（功能阻断）

### 实测

同机（"伪云端"）复现时，MCP 调用**能成功**——因为服务端恰好能读到那个路径：

```console
$ # 非本地模式，服务端却仍能 resolve 本地路径
=== 6) MCP tools/call search_context（传本地绝对路径 project_root）===
isError = False
[zace] answerable=true · confidence=medium · evidence=1 · docs=1 · mode=fast · channels=bm25,vector
[E2] SessionStore.refresh_token — src/session.py:1-9
```

这**掩盖**了真实云端的失效。真实云端（服务端没有该目录）的实际行为：

```console
$ uv run python -c "from zace_core.engine import repo_identity; print(repo_identity('/home/someuser/work/tool').identity_key)"
67913a4a187807df    remote=None  git_root=None    ← 退化为 sha256(绝对路径)
```

即：CF-06 的 `project_root` 在远端**必然算出一个与上传时不同的 projectId** → 项目不可达。

### 代码锚点

| 位置 | 事实 |
|---|---|
| `service/zace_service/mcp.py:367` `_project_id_for` | 用 `repo_identity(Path(project_root))` 反解 projectId（D-29），并注释"与 `POST /api/projects/resolve` 完全一致" |
| `core/zace_core/engine.py:185` `repo_identity` | 无 git → `sha256(str(absolute_path))`（`:205`）；有 git → `sha256(remote + 相对路径)` |
| `docs/contracts/mcp-tools.json` | `project_root` 是 `required` 参数，且 CF-06 声明"工具名/参数名/类型/默认值/上限冻结" |
| `docs/contracts/openapi.yaml` | CF-05 **已有** `/api/projects/resolve`（by `identityKey`）与全部 query 端点（by `projectId`） |

### 关键观察

**远端正解已经在 CF-05 里了**：client 在本地算 identityKey → `resolve` → 拿 `projectId` → 用 `projectId` 查询。
缺的只是"**让 MCP 面也说出 projectId**"这一个入口。因此这不是"服务端不懂远端"，而是"MCP 面参数没跟上"。

### 远端身份三方案对比

| 维度 | 方案甲：CF-06 加 `projectToken`/`projectId` | **方案乙（推荐）**：client 本地 resolve，MCP 传 `projectId` | 方案丙：双模式并存 |
|---|---|---|---|
| 具体做法 | 冻结 schema 增可选参数；服务端按 projectId 直取 | Rust client 扫描时算 identityKey（本地有 git）→ `POST /api/projects/resolve` → 缓存 projectId → MCP 传 projectId | `project_root` 与 `projectId` 都保留，按传输/模式判定 |
| 契约影响 | **L2**（改 CF-06） | **无**（CF-05 已支持；MCP 面为本地形态保留 `project_root`） | **L2**（同甲） |
| 客户端复杂度 | 低 | 中（需实现 D-29 身份算法：`sha256(remote+相对路径)`，**与 core 一致性是新的测试面**） | 中高 |
| 服务端复杂度 | 低 | **零** | 中（两条判定路径 = 两套测试） |
| 兼容本地 MCP | 需保留 `project_root` | 完全不受影响 | 需保留 |
| 主要风险 | 仍需保证 client 与服务端 identityKey 算法**逐字节一致**（否则 resolve 出两个项目） | 同上（但风险点被收敛到"一次 resolve"，可在 client 侧单测钉死） | 组合两者风险 |

**推荐：方案乙**。理由：

1. **零契约变更**，不阻塞 TASK-040R（用户要"直奔最终版本"，不该先卡在契约流程上）；
2. 身份算法**本来就必须在 client 侧存在**（Module/05 §3.4 明确 client 要 `resolve_project(root)`），
   不是为本方案额外新增的负担；
3. `project_root` 在本地 MCP 形态下仍然正确（服务端与代码同机），两种形态各说各话、互不干扰；
4. 真实 editor 场景（Claude Code / Cursor）与 `Background/01` 的参考实现**都是 client 自己 resolve**，
   口径一致。

**必须补的一致性保障（属 TASK-040R）**：identityKey 算法跨语言一致（Rust vs Python）。
建议在 TASK-040R 卡内要求一条"跨语言向量测试"：固定的 (remote_url, 相对路径) 组合集 → 期望 key 常量表，
两侧各自断言（比"人工核对"可靠）。

**需要编排者裁决的次要问题**：CF-06 的 `project_root` 描述里写的是"项目根绝对路径"，
但**从未明确"云端形态下 `project_root` 的语义"**（见 A3：service 接受父目录聚合）。建议在 Module/05 §2.1
补一句云端语义说明（L3 文档级，不改 schema）。

---

## 3. A3：D-29 身份未做协议形式归一化（跨机器共享的隐患）

### 实测

```console
场景1 同 remote 不同机器克隆
   machineA: 63e7c710719cfe66
   machineB: 63e7c710719cfe66   -> 一致 ✅

场景3 同一仓库不同协议形式
   git@  : 63e7c710719cfe66
   https: 7e2d89f0c46979b6      -> 不一致 ❌
```

场景 1 证明 D-29 的核心承诺成立（同 remote 不同克隆 → 同 key）。
场景 3 暴露：**同一物理仓库，只要 `origin` URL 的写法不同，就得到两个 projectId**。

### 影响面（比表面更大）

| 触发场景 | 后果 |
|---|---|
| 团队里有人用 HTTPS 克隆、有人用 SSH | **两边各自建一个项目，索引重复计算、互不共享** |
| 用户中途切换协议（如公司网络下临时改 HTTPS） | 同一仓库在两个 projectId 间反复切换，索引白建 |
| 同一仓库同时存在 `origin` 与 `upstream` | 只取 `origin`（`engine.py:170` `git_remote_url`），行为**未写入文档**，属隐式约定 |

### 处置建议（L3，需用户/编排者拍板）

**建议：在 `repo_identity` 的 material 中做 URL 规范化**，最小规则集（保守、可测）：

1. `scp` 形式 `git@host:path` → 展开为 `ssh://git@host/path`；
2. 主机名小写；
3. 统一去掉结尾 `.git`；
4. 保留用户名（自己 fork 与他人仓库必须区分）。

**归一化后 `git@github.com:acme/tool.git` 与 `https://github.com/acme/tool.git` 将归结为同一 key。**

**风险与纪律**：

- 这会**改变已有索引的 `identity_key`**（`project.json` 里存的是旧 key）→ 既有索引需重解析；
  当前是单人本地环境，代价可接受，但**必须在报告中显式声明**；
- 该改动会影响 `docs/design/Module/05-MCP与同步.md` §3.4 与 **D-29** 的表述 →
  **属 L3**，本卡不实现，只登记建议与理由。

---

## 4. A4：宿主白名单 / DNS-rebinding 在云端形态的行为

### 现状

`service/zace_service/mcp.py:186`（`mount` 的文档字符串）声明"Origin / DNS-rebinding 防护**保持 SDK 默认**
（`host="127.0.0.1"` → 自动放行 `127.0.0.1:*` / `localhost:*` / `[::1]:*`；其它 Origin 403）"。

但 `mount()` 自身（`:196` `mcp.streamable_http_app(streamable_http_path="/", json_response=...)`）
**并未传入任何 transport security 配置**——即白名单来源是 SDK 默认值，而非 zace 显式声明。

### 待验证（TASK-040R 开工前必须实测）

服务以 `0.0.0.0` 或域名反代暴露后：

1. 编辑器带 `Origin: https://zace.example.com` 的请求是否被 403？（若被拒 → 云端不可用）
2. 是否需要显式设置 `TransportSecuritySettings(allowed_hosts=[...])`？
3. 反代（Caddy/Nginx）透传的 `Host` 头会否触发 SDK 的 host 校验？

> 编排者未在本次盘点中完成实测（需要一个非回环绑定 + 反代环境）。
> **列为 TASK-040R 的第一个验证动作**，结论决定是否需要新增配置项（可能构成 L2 扩展）。

---

## 5. A5：新鲜度机制在远端静默失效（结论已明确）

### 证据链

| 位置 | 事实 |
|---|---|
| `service/zace_service/runtime.py:365` `rescan_if_due` | 要求 `_local_roots` 里有绑定（`:376`），远端上传路径**没有**绑定 → 直接返回 `False` |
| `service/zace_service/routers/query.py:150` | 非本地模式**根本不调用**重扫 |
| `service/zace_service/mcp.py:321` `_rescan_if_due` | MCP 面调用同一条 `rescan_if_due`；远端时静默无效（不报错、不提示） |
| `service/zace_service/routers/projects.py:76,98` | `attach` / `rescan` 在非本地模式返回 403 `local_mode_required`（**这是设计意图**，R34） |

### 结论

**与设计一致（D-27 有两种实现分支）**：远端模式的新鲜度**必须由 client 在每次 tool call 前保证**
（扫描 → 增量上传 → 重建 checkpoint），服务端不做任何重扫。
`_rescan_if_due` 在远端静默返回是"无操作"，不是 bug；但**建议**给 MCP 工具结果加一行 freshness 提示，
避免用户误以为服务端会自动更新（属可选增强，非阻断）。

**TASK-040R 需要实现的时序**（`Background/01` §3.3 的三条自愈路径 + §3.5/3.6 的 freshness 语义）：

```text
每次 tool call：
  ① scan（`ignore` crate：.zaceignore > .gitignore > 内置，D-28 / R42 语义对齐）
  ② 与本地缓存对账（mtime+size 快路径 → 仍重算 blob_hash 才算命中）
  ③ deleted  → POST /api/sync/deletions
  ④ added/modified → POST /api/sync/batch-upload（每批 ≤1MB；服务端返回 skipped 时本地剔除）
  ⑤ scope 变化 → POST /api/sync/checkpoint 重建 checkpointId
  ⑥ 检索：POST /api/query/search（带 projectId + checkpointId）
  自愈（各只重试一次）：invalid checkpoint → 作废重传全量 scope；stale blobs → forget → 重同步；scope_changed → 重建
```

---

## 6. A6：云端 MCP 的 V1 范围是否包含 LLM 总结（需拍板）

### 现状

`service/zace_service/routers/query.py` 的 `/api/query/ask` **不调用任何 LLM**，返回代码内固定的
`DEGRADED_NOTICE` 文案 + 检索结果：

```python
DEGRADED_NOTICE = "Deep 模式（LLM 总结）尚未接入（Phase 3）；以下为检索与组装结果，可直接作为上下文使用。"
```

而 CF-05 声明 `AskResponse.status: [answered, insufficient_evidence, degraded]`——即契约里
**留了 `answered` 的位置，实现永远不会产生它**。

### 影响

| 若 V1 不含 LLM | 若 V1 含 LLM |
|---|---|
| `ask_project` 在云端是 `search_context` 的同义词（只多一行降级说明）→ **可以不要这个工具**，或明确标注"暂等价于 search"；Rust client 可只实现 1 个工具 | 需要 AnswerProvider（Module/04，Phase 3）+ citation 回验（D-25）+ 降级（D-26）→ TASK-040R 范围显著变大 |

### 建议

**V1 云端 MCP 只保证 `search_context` 可用**，`ask_project` 如实返回降级包并在工具描述里标注
"当前返回检索包，LLM 总结未接入"；LLM 总结按 Phase 3 排期（与 D-26/Module/04 一致）。
**需编排者/用户确认**（这决定 TASK-040R 是否要等 Phase 3）。

---

## 7. A7：`/healthz` 的能力自述不诚实（登记项）

- `ops.py:43`：`auth` 按 `local_mode` 固定返回 `enabled` / `disabled(local)`，与真实鉴权状态无关（见 A1）。
- 同类风险面：`/healthz` 的 `projects` 只反映**本进程内存**里的进度，多副本部署下会各说各话（A8 相关）。
- **处置**：A1 修复时一并改为诚实值（`"not_implemented"`），并在 `/healthz` 增加"是否非回环绑定"提示。

---

## 8. A8：checkpoint 是"只记不用"（语义缺口）

### 证据

- 写入：`service/zace_service/routers/sync.py:123-130`（`create_checkpoint`）→ `state.record_checkpoint(...)` 正常落盘
  （`sync_state.py:236`，内容寻址 + LRU 保留 `MAX_CHECKPOINTS`）；
- 读取：`service/zace_service/packmeta.py:24` 明确注释
  **"``checkpointId`` 只做透传记录（值不参与检索，卡内明确）"**，`:85` 只是把它塞进 meta。

即：检索**完全不按 checkpoint 的 scope 过滤**——checkpoint 目前只是一张"客户端自证"的收据。

### 影响与建议

| 问题 | 说明 |
|---|---|
| 多客户端/多分支共用一个 project 时，A 分支的查询会检索到 B 分支的块 | 云端多用户（TASK-061）下这会变成**正确性**问题，而非优化 |
| `Background/01` §3.5 的设计意图 | checkpoint 的原始目的是**避免重传 2.5MB 全量名单**（传输优化），**不是** scope 过滤；两者不冲突 |

**建议**：明确记录"checkpoint = 传输优化，不是检索 scope 过滤"（写入 Module/05 §3.3 语义澄清）；
若将来需要多分支隔离，**应新开卡并评估**（属 L3，因为会影响 project 的物理布局）。

---

## 9. A9：首同步体验（D-31/D-32 对齐）

现状（本地 MCP 形态）：`attach` 立即返回、后台索引、`indexProgress` 轮询——已由 TASK-034 实现。
云端形态：**上传是同步阻塞的**（Rust client 逐批 POST，每批 ≤1MB，30s 超时），
服务端每次 `batch-upload` 会在请求内同步触发一次 `ingest`（`runtime.py:234` 的 `ingest` → `:237` `with self._lock_for(project_id)`，**同 project 串行、不是后台任务**）。

| 待 TASK-040R 处理 | 依据 |
|---|---|
| 首同步大仓库（数千文件）期间让首个 tool call **不无限阻塞**：返回进度 + 可重试 | D-31（120s 转后台）、D-32（upload 30s / search 15s / ask 90s） |
| 并发上传（`Background/01` §7-6 建议 gzip + 并发） | 优化项，可后置 |
| 上传后索引未完成时的如实报告（`indexingFiles`） | D-30 / CF-05 `SyncStatus` |

---

## 10. A10：可直接复用的现成资产（避免 Rust client 重造轮子）

实测确认（同机伪云端全流程 2 文件 / 5 chunks 跑通）：

| 资产 | 位置 | 状态 |
|---|---|---|
| `POST /api/projects/resolve`（by identityKey，幂等） | `routers/projects.py:55` | ✅ 实测 200 + `{projectId, created}` |
| `POST /api/sync/batch-upload`（幂等，返回 accepted/skipped + 索引报告） | `routers/sync.py:81` | ✅ 实测直接触发索引（`report.added=2, chunksNew=5`） |
| `POST /api/sync/deletions` | `routers/sync.py` | ✅ 有端到端测试（`test_delete_is_end_to_end_and_idempotent`） |
| `GET /api/sync/status/{id}` | `routers/sync.py` | ✅ 实测返回 `filesIndexed/chunks/symbols/branch/commit/blobs` |
| `POST /api/sync/checkpoint` | `routers/sync.py:123` | ✅ 内容寻址 + LRU（`test_checkpoint_is_content_addressed_and_lru_capped`）；**注意 A8：仅记录不参与检索** |
| `POST /api/query/search`（by projectId） | `routers/query.py` | ✅ 实测返回 Markdown + meta |
| `blob_hash` 契约（path+0x00+content 的 sha256） | `core/zace_core/hashing.py:23` | ✅ 冻结（CF-02），Rust 侧需逐字节复刻 |
| 端到端测试范式 | `service/tests/test_sync_api.py:176` (`test_upload_then_search_finds_the_new_file`) | ✅ 可直接作为 Rust client 集成测试的对照 |

**结论**：Rust client 的工作量集中在**本地侧**（扫描 / ignore 语义 / 缓存 / 分批上传 / checkpoint 自愈 / stdio 协议），
服务端**不需要为新形态做结构性改动**（除 A1 鉴权与 A2 的 MCP 入口）。

---

## 11. 契约与设计影响分级（给编排者）

| 编号 | 事项 | 级别 | 需要什么 |
|---|---|---|---|
| A1 | `/healthz` 的 `auth` 自述改为诚实值 | **L1**（实现层，不改契约字段） | 一张小卡或并入 TASK-060 |
| A1' | 云端鉴权（token + 租户） | **L2**（CF-05 已声明 bearer/cookie，仅需实现） | TASK-060 / TASK-061 提为 TASK-040R **硬依赖** |
| A2 | 云端 MCP 传 `projectId`（方案乙） | **无契约变更** | TASK-040R 可直接实施 |
| A2' | CF-06 `project_root` 的云端语义说明 | L3（文档级，不改 schema） | Module/05 §2.1 补一段 |
| A3 | D-29 身份 URL 归一化 | **L3**（改决策 D-29 表述 + 既有索引 identity_key 变化） | **用户/编排者拍板**；另开卡实现 |
| A4 | 云端宿主白名单 / TransportSecuritySettings | 待实测；若需新增配置项 → **L2** | TASK-040R 第一验证动作 |
| A6 | V1 是否含 LLM 总结 | **L3**（范围决策） | 用户拍板 |
| A8 | checkpoint 语义澄清 | L3（文档级澄清） | Module/05 §3.3 补一句 |

---

## 12. 未决问题（逐条附建议，便于直接拍板）

| # | 问题 | 建议裁定 |
|---|---|---|
| Q1 | 云端鉴权（TASK-060/061）是否作为 TASK-040R 的**硬依赖**？ | **是**。未鉴权的 Rust client 等于把源码索引暴露给任何拿到 URL 的人；建议至少先做 token（061 可随后） |
| Q2 | A2 采方案乙（client 本地 resolve，零契约变更）？ | **是**。理由见 §2；同时要求 TASK-040R 增加"跨语言 identityKey 一致性"测试 |
| Q3 | A3 是否现在做 URL 归一化？ | **建议做**，但要接受既有索引 identity_key 变化（当前单人环境，代价可控）；属 L3，需拍板 |
| Q4 | `ask_project` 在 V1 云端是否保留？ | **保留但如实标注**（返回降级包）；LLM 总结按 Phase 3，不阻塞 TASK-040R |
| Q5 | checkpoint 是否要做检索 scope 过滤？ | **暂不做**，明确为"传输优化"；多分支隔离另开卡评估 |
| Q6 | A4（宿主白名单）是否需要新配置项？ | **先实测**（TASK-040R 第一步），有结论再定级别 |

## 13. 建议的 TASK-040R 系列拆分（供编排者参考，不在本卡执行）

```text
TASK-040R（client 骨架）：cargo 工程 + stdio MCP 协议 + 两工具透传 + 配置（endpoint/token）
  ├── 040R-A（同步引擎）：ignore 三层语义 + blob_hash 复刻 + 缓存 + 增量对账 + 分批复传
  ├── 040R-B（checkpoint 与自愈）：scope 重建 + 三条自愈路径（各重试一次）
  ├── 040R-C（分布式与体验）：分层超时矩阵 + 首同步进度反馈 + 并发上传（gzip）
  └── 040R-D（跨语言一致性测试）：identityKey / blob_hash 常量表双向断言
前置：TASK-060（token）——排除后 Rust client 无法安全上云
```

## 14. 复现方式（本报告全部实测的完整脚本）

- 伪云端全流程（attach 403 → resolve → batch-upload → status → REST 检索 → MCP 检索）：
  `/tmp/zace-remote-repro/run.sh`
- A1 无鉴权五连探（healthz / 无凭据 / 无效凭据 / MCP / auth 501）：
  `/tmp/zace-a1-probe/run.sh`

> 两份脚本均在临时目录，未进仓库（不带 secret、不含绝对路径依赖）；
> 如需固化为回归测试，建议 TASK-060 落地时一并纳入 `service/tests/`。
