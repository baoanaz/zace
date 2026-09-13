# TASK-084：查询审计接线（`/api/usage/**` 目前恒为空）

> 状态：pending ｜ 阶段：Phase 3（M2c）｜ 硬依赖：TASK-060（已合并）｜ soft 依赖：TASK-061（租户，可后接）
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

（实施 AI 在此填写。）
