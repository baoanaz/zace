# TASK-084：查询审计接线（`/api/usage/**` 目前恒为空）

> 状态：**review** ｜ 阶段：Phase 3（M2c）｜ 硬依赖：TASK-060（已合并）｜ soft 依赖：TASK-061（租户，可后接）
> 建议分支：`feature/task-084-query-audit_<你的缩写><MMDD>`
> 交付物所有权：
> - `service/zace_service/audit.py`（**新建**，TASK-064 卡原本要求但我实测不存在）
> - `service/zace_service/routers/query.py`（在 search / ask 两处调用审计）
> - `service/tests/test_usage_api.py`（**新建**，TASK-064 卡原本要求但不存在）
>
> 清单外文件不得改。**特别提醒：`service/zace_service/metadb.py` 已有 `record_query()` 实现（约 626 行），
> 本卡**不需要**改它——若你判断必须改，先写进"未决问题"并说明理由。**

## 背景（编排者实测发现，2026-09-13）

**现象**：在云端模式服务上真实提问后，`GET /api/usage/summary` 仍返回全 0：

```json
{"total":0,"succeeded":0,"insufficient":0,"failed":0,"avgLatencyMs":null,
 "p95LatencyMs":null,"confidenceDistribution":{},"citationCoverageAvg":null,
 "topQueries":[],"recent":[],"days":7}
```

**根因**（已定位）：`MetaDB.record_query()` **写好了但全仓零调用**。

```console
$ grep -rn "record_query" --include="*.py" . | grep -v tests
./service/zace_service/metadb.py:626:    def record_query(     # ← 只有定义，没有任何调用点
```

同时 TASK-064 卡要求的 `service/zace_service/audit.py` **文件不存在**。

**影响**：WebUI「历史记录」页的"使用记录"页签永远为空；
`/api/account/overview` 的 `usage` 段永远为 0；Dashboard 的"使用次数/P95/引用覆盖率"永远显示 0/—。
这是**用户跑真实场景时会直接看到的问题**。

## 目标

把查询审计真正接上：每次 `/api/query/search` 与 `/api/query/ask` 结束后，
把这次查询落进 `query_audit` 表，使 `/api/usage/**` 与 `/api/account/overview` 有真实数据。

## 输入文档（按序读）

1. `docs/tasks/TASK-064-查询审计与用量.md`（**本卡是它的补做**；字段表、保留策略、DoD 全在里面）
2. `service/zace_service/metadb.py`（`record_query` 的签名与 `query_audit` 表结构）
3. `service/zace_service/routers/query.py`（两个端点，看 `meta`/`packmeta` 里有什么可落库的字段）
4. `docs/design/Module/04-AI总结.md` §8（审计字段与保留策略的**唯一依据**）

## 本卡必须做到的

### §A 新建 `audit.py`

按 TASK-064 卡的要求实现：

```python
audit.record_query(project_id, *, mode, query, meta, latency_ms, user_id) -> None
```

**关键纪律（卡片原文）**：

- **绝不让检索因审计失败而失败**：`record_query` 内部 try/except，失败只记 WARN 日志
  （日志里的文本走 `redact_text` 脱敏）；
- 审计是**旁路**：检索结果不受任何影响；
- `mode` 区分 `search` / `ask`。

### §B 在 `query.py` 两个端点接线

- 记录**耗时**（`latency_ms`，从进入处理到拿到结果）；
- 记录 `answerable` / `confidence` / citation 覆盖率等**从 `meta` 拿到的真实值**（不要编造）；
- 记录**当前用户**（`request.state.zace_user`；本地模式下为 `None`）；
- **异常路径也要记**（如 embedding 不可用返回 503 时）——否则"失败次数"恒为 0，
  这与 TASK-062 对索引统计的口径一致（成功与失败都落）。
  **若异常路径难以覆盖，至少要把"返回了非 2xx 的业务失败"记进去，并在报告里说明。**

### §C 补 `test_usage_api.py`

TASK-064 卡的 DoD 列了必须覆盖的场景，**逐条落实**。至少要覆盖：

- [ ] 一次成功 search → `usage.total=1, succeeded=1`；
- [ ] 一次证据不足（answerable=false）→ `insufficient=1`；
- [ ] **审计失败不影响检索**：让 metadb 抛异常 → `/api/query/search` **仍返回 200**（卡片要求，必须有）；
- [ ] `latencyMs` 是真实测量值（> 0，不是写死的）；
- [ ] 保留策略：超过上限时裁剪最旧的；
- [ ] 服务重启后统计仍在（落库而非内存）。

## 验收标准（DoD）

- [ ] `uv run pytest service/tests/test_usage_api.py -q` 全绿，覆盖上述场景。
- [ ] **端到端行为验收（贴真实输出，这是本卡的核心凭证）**：
      起云端模式服务 → bootstrap → 建 token → resolve 项目 → 上传一个文件 → 提问 →
      然后 `curl /api/usage/summary` **必须看到 `total>=1`**（改动前是 0）。
      把前后对比贴进执行记录。
- [ ] `/api/account/overview` 的 `usage` 段同步有值。
- [ ] 脱敏断言：审计落库的 `query` 文本与错误摘要里**不含** API key / base_url（用真实 key 形态构造用例）。
- [ ] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest -o addopts="" -q`
- [ ] 任务卡"执行记录"已回填；任务板 TASK-064 那行状态改为 `review`（**本卡是 TASK-064 的补做，
  不是新任务**；请在 TASK-064 卡内也追加一段"补做记录"，说明本卡的存在）。

## 明确不做

- 不改 `MetaDB.record_query` 的表结构或字段语义（已按 Module/04 §8 冻结）；
- 不实现 LLM 总结（Phase 3 未开）；
- 不碰 `service/zace_service/runtime.py`（那是 TASK-085 的领地）；
- 不做 TASK-061 的租户过滤（本卡落库带 `user_id` 即可，过滤由 TASK-061 负责）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板。**必须包含**：
`/api/usage/summary` 改动前 vs 改动后的真实响应对比。

## 执行记录

### 2026-09-23 ｜ 分支 `feature/task-084-audit_xwz0923` ｜ 状态：**review**

**完成报告**

- **冲突裁决（先问用户，已拍板）**：`mode` 口径取 `fast` / `deep`（`metadb.py` DDL 注释与 WebUI 的
  `fast | deep` 词汇），而非卡内 §A 写的「区分 search / ask」；两者的区分度不减（`ask` 另带 `degraded=true`）。
- **分支**：`feature/task-084-audit_xwz0923`（从 `main` @ `d1a87ba` 创建）
- **验收命令与结果**

```console
$ uv run pytest service/tests/test_usage_api.py -q
20 passed

$ uv run ruff check .
All checks passed!

$ uv run python scripts/check_dependency_direction.py
依赖方向检查通过（core 纯库 / service 不上探）。

$ uv run pytest -o addopts="" -q
766 passed, 2 skipped, 1 warning in 18.33s
```

- **关键产物**：`service/zace_service/audit.py`（新建）、`service/zace_service/routers/query.py`、
  `service/tests/test_usage_api.py`（新建，20 项）
- **契约影响**：无（未改任何契约文件；`meta` 字段集与 CF-05 不变）
- **与设计偏差**：无（`audit.py` 的签名按 TASK-064 冻结接口实现，仅多一个可选 `degraded` 参数）

#### 端到端验收（本卡核心凭证）：改动前 vs 改动后

真实服务（真实 embedding provider，非假 provider）：`uv run zace-service local --repo <tmp repo>`，
bootstrap → resolve → 上传 2 个文件 → 索引（chunks=6）→ 提问 3 次（1 次 search、1 次 ask、1 次证据不足）。

```console
# ===== 改动前（main @ d1a87ba）=====
$ curl -s localhost:8799/api/usage/summary
{"total":0,"succeeded":0,"insufficient":0,"failed":0,"avgLatencyMs":null,
 "p95LatencyMs":null,"confidenceDistribution":{},"citationCoverageAvg":null,
 "topQueries":[],"recent":[],"days":30}          # ← 提问 3 次之后仍然是全 0

$ curl -s localhost:8799/api/account/overview | jq .usage.total
0

# ===== 改动后（本分支）=====
$ curl -s localhost:8799/api/usage/summary
{"total":3,"succeeded":1,"insufficient":2,"failed":0,"avgLatencyMs":767,
 "p95LatencyMs":2245,"confidenceDistribution":{"low":2,"medium":1},
 "citationCoverageAvg":null,
 "topQueries":[{"query":"令牌过期后在哪里刷新","count":2},
               {"query":"zzzz qqqq 完全不相关的主题","count":1}],
 "recent":[{"queryId":3,"mode":"fast","answerable":false,"confidence":"low","latencyMs":45,...},
           {"queryId":2,"mode":"deep","answerable":true,"confidence":"medium","degraded":true,"latencyMs":63,...},
           {"queryId":1,"mode":"fast","answerable":true,"confidence":"medium","latencyMs":55,...}],
 "days":30}

$ curl -s localhost:8799/api/account/overview | jq .usage.total
3

$ curl -s localhost:8799/api/usage/projects/<id>
{"total":3,"succeeded":2,"insufficient":1,"failed":0,"avgLatencyMs":54,"p95LatencyMs":63,
 "citationCoverageAvg":null,"confidenceDistribution":{"medium":2,"low":1}}
```

云端模式补充取证（`local_mode=False`，bootstrap → token → resolve → 上传 → ask）：

```console
# 写库直证：query_audit 真有一行，且带 user_id
{'id': 1, 'project_id': 'bc17edcb30e2716e', 'user_id': 'ea42578813494a06c4dd5373013dc9e1',
 'mode': 'deep', 'query': '令牌过期后在哪里刷新', 'answerable': 1, 'latency_ms': 35}

# GET /api/usage/projects/{id} → total=1（读取口正常）
# 失败路径：空索引项目上检索 → 409 index_in_progress，该项目的 failed=1
# 重启后：MetaDB.open(同一 db 文件).usage_summary([pid]).total == 1（落库而非内存）
```

#### 延迟测量口径（卡内要求写明）

| 场景 | 窗口 | 说明 |
|---|---|---|
| 成功 | `_timed()` 包住 `_rescan_before_query` + `manager.search` | TASK-064 §C-3 口径：**不含**服务端渲染与响应装配 |
| 失败 | 从 handler 进入算起的整段（`finally` 里取值） | 检索段根本没跑完，用 0 会让失败耗时恒为 0（"写死"正是本卡要杜绝的） |

`latencyMs > 0` 由单测用**注入 200ms 延迟后断言增量**钉住（比 `> 0` 强：写死 `1` 也能过 `> 0`）。

#### 覆盖情况（TASK-084 §C 清单逐条）

| 要求 | 单测 |
|---|---|
| 成功 search → total=1, succeeded=1 | `test_successful_search_is_recorded_with_real_measurements` |
| 证据不足 → insufficient=1 | `test_insufficient_evidence_is_counted_separately` |
| **审计失败不影响检索（仍 200）** | `test_audit_failure_does_not_break_retrieval`、`test_ask_audit_failure_does_not_break_retrieval` |
| latencyMs 是真实测量值 | `test_latency_is_actually_measured_not_hardcoded` |
| 保留策略裁剪最旧 | `test_retention_keeps_only_the_newest_records` |
| 重启后统计仍在 | `test_stats_survive_a_restart` |
| 异常路径也记（业务失败） | `test_business_failure_is_recorded`、`test_validation_failure_is_recorded_even_without_project`、`test_unexpected_exception_is_recorded_and_still_500` |
| ask 的 citationCoverage 为 null | `test_ask_records_deep_mode_with_null_citation_coverage` |
| 不存源码内容 | `test_no_source_content_is_stored` |
| 脱敏（含裸 key） | `test_secrets_are_redacted_before_storage`、`test_redact_query_text_also_masks_bare_keys` |
| days 窗口过滤 | `test_days_window_filters_old_records` |
| 三个读取口一致 | `test_usage_and_overview_endpoints_agree` |

#### 超出卡内的必要改动（已在"未决问题"报备）

- **`logging.py` 的裸 key 脱敏**：实测 `redact_text` **不脱敏裸 key**（`sk-live-abc...` 原样保留，
  只有 `api_key=xxx` 这种键值形态才脱）。而查询文本要落库，用户把 key 粘进查询框就会留痕。
  本卡在 `audit.py` 内自建 `redact_query_text()`（`redact_text` + 裸 `zace_` / `sk-` 兜底）解决，
  **未改 `logging.py`**（清单外文件）——见未决问题 ①。
- **`app.py` / `__main__.py` 未改**：`app.py` 在 `auth_required=False`（本地模式）时 `meta_db` 恒为 `None`，
  而本地模式正是本卡验收的形态。实际启动路径 `zace-service local` 会显式注入
  `app.state.meta_db = MetaDB.open(...)`（`__main__.py:182-183`，TASK-034 落的），因此**生产路径本来就通**。
  单测夹具照生产路径同样显式注入，不改公共文件。

#### 未决问题

1. **`logging.py::redact_text` 不脱敏裸 key（向编排者提出，本卡未越界改）**：建议给 `redact_text`
   加一条裸 key 规则（`zace_` / `sk-` 前缀），使**全仓**的日志与错误响应都受益；否则每个消费点
   （audit、未来的响应文案）都得自己兜一遍。TASK-064 §C 只提到 `redact_text`，本卡已在其上加了
   `audit.redact_query_text` 兜底，功能不缺，缺的是**公共防线**。
2. **云端模式 `/api/usage/summary` 仍为 0（这是 TASK-061 的缺口，不是本卡的）**：
   `routers/ops.py::_visible_project_ids` 在鉴权模式下按 `projects` 归属表过滤，而 `claim_project`
   **全仓零调用**（`grep -rn claim_project --include=*.py service/` 只有定义）→ `projects` 表零行
   → 可见 projectId 集合为空 → summary 恒 0。本卡实测已附证据（云端写库正常、
   `GET /api/usage/projects/{id}` 正常，仅 summary 为空）。**需要 TASK-061 落地归属写入**；
   在此之前云端 WebUI 的「使用记录」页签（读 `/api/usage/summary`）仍会显示 0。
   本卡按"不改清单外文件"纪律**未**顺带 wiring。
3. `mode` 的 `fast` / `deep` 口径已按用户拍板落地；若编排者坚持回到 `search` / `ask`，
   改动点只有 `audit.py` 的两个常量与一处单测断言。

#### 建议复核点

- `_audited` contextmanager 的"异常记录后再抛"是否真的不改变响应语义（`test_unexpected_exception_is_recorded_and_still_500` 钉住 500 不变）；
- `audit.py` 的 `record_query` / `record_query_error` 是否**完全没有**向上抛异常的路径（除 `logger` 外的每一层都有 `except ... : pass`）；
- `evidence_meta()` 的字段裁剪是否足够严（`test_no_source_content_is_stored` 断言字段集 == 5 个且正文串不在库里）。

