# TASK-064：查询审计与用量端点（`/api/usage/**`）

> 状态：pending ｜ 阶段：Phase 3（M2c）｜ 硬依赖：TASK-060（要归属用户）｜ soft 依赖：TASK-061、TASK-062
> 建议分支：`feature/task-064_<你的缩写><MMDD>`
> 交付物所有权：
> - `service/zace_service/metadb.py`（追加 `query_audit` 表与聚合查询）
> - `service/zace_service/audit.py`（**新建**：审计写入与保留策略）
> - `service/zace_service/routers/{query,ops}.py`（写入点接入 + 把 501 占位换成实现）
> - `service/tests/test_usage_api.py`（**新建**）
>
> 清单外文件不得改。

## 目标

`GET /api/usage/projects/{id}` 目前是 **501 占位**（`routers/ops.py`）。设计里它是
**04 §8 审计存档的读取口**，也是把运营数据变成检索质量改进燃料的闭环（`docs/design/Module/04-AI总结.md` §8）：

```text
{ query, mode, confidence, citationCoverage, llmLatencyMs,
  evidence: [{id, path, lines, tier, score}], answerTokens, createdAt }
```

本卡交付"如实记录 + 聚合读取"，供 TASK-070 的用量页消费。

## 输入文档（按序读，只读所需章节）

1. `docs/design/Module/04-AI总结.md` §8（**审计存档字段表与保留策略是唯一依据**）、§5（citationCoverage 定义）
2. `docs/design/Module/06-服务化与部署.md` §2.4（审计归 service 入库）
3. `docs/contracts/openapi.yaml`（`GET /api/usage/projects/{id}`：现只有 `200 OK` 描述，需补响应形状）
4. `service/zace_service/packmeta.py`（`meta` 里已有 `confidence` / `answerable` / `budget` 等，勿重复造）
5. `service/zace_service/routers/query.py`（`search` / `ask` 的返回与两个写入点）

## 冻结接口（本卡不得变更）

- 消费：`packmeta.meta` 的既有字段集（**不得改 meta 字段**，它是 TASK-040R 的客户端契约）。
- 产出：
  - `audit.record_query(project_id, *, mode, query, meta, latency_ms, user_id) -> None`（**绝不让检索因审计失败而失败**）
  - `audit.usage_summary(project_id, *, days: int = 30) -> UsageSummary`
  - `UsageSummary = { total, succeeded, failed, insufficient, avgLatencyMs, p95LatencyMs,
                     confidenceDistribution, citationCoverageAvg, topQueries, recent }`
  - 端点见 §A

## §A 端点（CF-05 扩展，登记在卡内）

| 方法 | 路径 | 语义 |
|---|---|---|
| GET | `/api/usage/projects/{id}` | 单项目用量聚合（**替换 501 占位**）；`?days=` ≤ 365，默认 30 |
| GET | `/api/usage/projects/{id}/queries` | 最近查询明细（`?limit=` ≤ 200） |
| GET | `/api/usage/summary` | 跨项目汇总（当前用户） |

```json
// GET /api/usage/projects/{id}
{ "projectId": "e6fe…", "days": 30,
  "total": 431, "succeeded": 402, "insufficient": 24, "failed": 5,
  "avgLatencyMs": 137, "p95LatencyMs": 420,
  "confidenceDistribution": { "high": 120, "medium": 240, "low": 40, "unknown": 31 },
  "citationCoverageAvg": null,        // ask 未接 LLM 前恒为 null（不许填 0）
  "topQueries": [ { "query": "token 过期", "count": 12 } ],
  "recent": [ { "queryId": …, "mode": "fast", "query": "…", "answerable": true,
                "confidence": "medium", "latencyMs": 130, "evidenceCount": 6,
                "createdAt": 1789096917 } ] }
```

**`citationCoverageAvg` 必须为 `null` 而不是 0**：Phase 3 之前 `ask` 走降级包（D-26），
根本没有 citation 可言。填 0 会被读成"引用质量极差"，与"尚未测量"是两件事（诚实性纪律）。

## §B 数据模型（追加到 `zace-meta.db`）

```sql
CREATE TABLE IF NOT EXISTS query_audit (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id     TEXT NOT NULL,
  user_id        TEXT,
  mode           TEXT NOT NULL,        -- fast | deep
  query          TEXT NOT NULL,        -- 原始查询（**用户输入，非源码内容**）
  answerable     INTEGER,
  confidence     TEXT,
  degraded       INTEGER NOT NULL DEFAULT 0,
  latency_ms     INTEGER NOT NULL,
  evidence_count INTEGER NOT NULL DEFAULT 0,
  docs_count     INTEGER NOT NULL DEFAULT 0,
  used_tokens    INTEGER NOT NULL DEFAULT 0,
  citation_coverage REAL,              -- NULL = 未测量（见 §A）
  evidence_json  TEXT NOT NULL DEFAULT '[]',  -- [{id,path,lines,tier,score}]，**不含代码内容**
  created_at     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_project ON query_audit(project_id, created_at DESC);
```

保留：每项目最近 1000 条（04 §8 冻结值）。裁剪在写入路径内完成（插入后按 `created_at` 删多余行）。

## §C 写入纪律（三条硬约束）

1. **脱敏**：只存 evidence 的元数据（`id/path/lines/tier/score`），**绝不存代码片段或答案正文**
   ——04 §8 冻结"不含源码内容"。用测试钉住：写入一条含敏感串的 evidence，断言库里查不到该串。
2. **审计失败不得影响检索**：`record_query` 内部 try/except，失败只记 WARN 日志（含 `redact_text`）。
   理由是审计是旁路；但**必须有单测证明**：让 metadb 抛异常，断言 `/api/query/search` 仍返回 200。
3. **写入位置**：`routers/query.py` 的 `search` 与 `ask` 各一处，在 `return` 之前；
   延迟用 `time.perf_counter()` 包住 `manager.search(...)` 那一段（**不含**懒重扫与渲染，
   在报告里写清口径，否则延迟数字不可比）。

## §D 与 TASK-062 的边界

- 本卡管**查询**审计（`query_audit`）；TASK-062 管**索引** run 记录（`index_runs`）。
- 两张表都在 `zace-meta.db`，但**字段、保留策略、端点互不重叠**；同时开卡时以 `metadb.py` 为
  冲突点，**必须串行**（本卡建议排在 TASK-062 之后）。

## 验收标准（DoD）

- [ ] `uv run pytest service/tests/test_usage_api.py -q` 全绿，**必须覆盖**：
  - [ ] 检索一次 → `total=1`，`avgLatencyMs ≥ 0`，`recent` 有该条；
  - [ ] `ask` 的条目 `citationCoverage` 为 **null**（不是 0）；
  - [ ] `insufficient`（`answerable=false`）与 `failed`（异常）分开计数；
  - [ ] **不存源码**：断言库中 `evidence_json` 无代码片段字段；
  - [ ] **审计故障不影响检索**：metadb 注入异常 → `search` 仍 200；
  - [ ] 超过 1000 条自动裁剪；
  - [ ] `days` 过滤生效（构造一条 40 天前的记录，`?days=30` 不包含它）；
  - [ ] 跨用户不可见（与 TASK-061 联动）。
- [ ] 行为验收（贴真实输出）：对真实仓库连跑 5 次不同查询 → 展示 `usage` 响应，
      并给出"平均耗时"与索引统计耗时的差异解释。
- [ ] 基线三条命令全绿。
- [ ] 任务卡"执行记录"已回填；任务板对应行状态改 `review`。

## 明确不做

- 不做实时图表/流式用量（web 拉快照即可）
- 不做费用/账单（embedding 与 LLM 的 token 成本模型另议）
- 不做用户行为分析、不做导出 CSV（V2 候选）
- 不做 `ask` 的 LLM 接入本身（Phase 3 另有卡；本卡只留 `citation_coverage` 字段）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写，**必须写明延迟测量口径与保留策略的实测填充量**。

## 执行记录

（实施 AI 在此填写。）
