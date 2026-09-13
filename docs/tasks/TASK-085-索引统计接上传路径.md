# TASK-085：索引统计接上客户端上传路径（Agent 接入后面板恒为 0）

> 状态：pending ｜ 阶段：Phase 3（M2c）｜ 硬依赖：TASK-060/062（已合并）｜ soft 依赖：TASK-084（同改统计，不冲突）
> 建议分支：`feature/task-085-index-stats-sync_<你的缩写><MMDD>`
> 交付物所有权：
> - `service/zace_service/runtime.py`（在 `ingest` 路径补记 run 记录）
> - `service/tests/test_index_stats.py`（**新建**，TASK-062 卡原本要求但不存在）
> - `docs/tasks/TASK-062-索引job与统计.md`（追加"补做记录"段；**不要**改卡片的规格部分）
>
> 清单外文件不得改。**特别提醒：`metadb.py::record_index_run` 已实现（约 516 行），本卡不需要改它。
> `service/zace_service/routers/sync.py` 也**不要**改（记录点放在 `runtime.ingest` 更内聚，
> 且能同时覆盖未来的其它调用方）。**

## 背景（编排者实测发现，2026-09-13）

**现象**：用真实 `npx zace-client` 走完"上传 → 索引 → 查询"后，
`GET /api/index-stats` 与 `/api/account/overview` 的索引统计**仍全为 0**：

```json
{"total":0,"succeeded":0,"failed":0,"avgDurationMs":null,"minDurationMs":null,
 "maxDurationMs":null,"lastRunAt":null,"lastState":null,"recent":[],"diskBytes":0}
```

**根因**（已定位）：`_record_index_run` 只挂在**本地后台索引器**的 `on_finish` 上：

```python
# service/zace_service/runtime.py  (_indexer_for → ProjectIndexer(on_finish=...))
on_finish=(lambda progress, pid=project_id: self._record_index_run(pid, progress)),
```

而**客户端上传路径**是另一条：

```python
# service/zace_service/routers/sync.py  (batch_upload)
report = manager.ingest(project_id, ChangeSet(...))   # ← 直接调 manager.ingest，不经过 ProjectIndexer
```

`EngineManager.ingest()`（`runtime.py:240`）在结束时**不写任何 run 记录**，因此：

| 使用方式 | 索引统计 |
|---|---|
| `zace-service local --repo …`（本地 attach） | ✅ 有记录 |
| **`npx zace-client` 上传（Agent 实际用的路径）** | ❌ **恒为 0** |

**影响**：用户按接入指南配好 Agent、提问成功后，打开 WebUI 会发现
"索引成功/失败次数、平均耗时、最近索引记录"**全是 0**，误以为系统没工作。
这是**用户跑真实场景时会直接看到的问题**。

## 目标

让 `EngineManager.ingest()` 的每次索引都落一条 run 记录，
使客户端上传路径与本地 attach 路径的统计口径**一致**。

## 输入文档（按序读）

1. `docs/tasks/TASK-062-索引job与统计.md`（**本卡是它的补做**；§C 记录时机、§D avgDurationMs 口径、
   保留策略 500 条，都是本卡的规格依据）
2. `service/zace_service/runtime.py`（`ingest` / `_record_index_run` / `attach_meta_db`）
3. `service/zace_service/metadb.py`（`record_index_run` 签名与 `index_runs` 表结构）

## 本卡必须做到的

### §A 在 `ingest` 路径补记录

- 在 `EngineManager.ingest()` 拿到 `IngestReport` 后，写一条 run 记录；
- **成功与失败都落**（TASK-062 §C 原文：「只写成功会让"失败次数恒为 0"」）；
- 耗时用真实测量（`time.perf_counter()` 前后差），**不是估算**；
- `state="done"` 且 `report.errors` 非空 → **仍算 succeeded**，但 `errors` 字段如实记条数
  （与既有 `_record_index_run` 口径**保持一致**，不要另立一套）；
- 失败（抛异常）时也要落记录，`error_text` 走脱敏；
- **记录失败绝不能让索引本身失败**：与 `_record_index_run` 的既有纪律一致
  （`_notify_finish` 已吞回调异常；本路径请同样处理，并写一条测试证明）。

### §B 口径统一（重要）

`ingest` 路径与本地 `ProjectIndexer` 路径的**字段语义必须一致**——
同一个项目既可能被客户端上传、也可能被本地 attach 索引，两条路径的统计不该有两套解释。

- `files_total` / `files_processed`：`IngestReport` 里能拿到什么就如实记什么
  （**若 `IngestReport` 没有 total，就记 0 或按已有字段推导，并在报告里写清口径**）；
- `avgDurationMs` 只统计成功 run（TASK-062 §D），本卡不要破坏这个语义。

### §C 补 `test_index_stats.py`

TASK-062 卡的 DoD 列了必须覆盖的场景，**逐条落实**。至少覆盖：

- [ ] **客户端上传路径**：`batch-upload` → `GET /api/index-stats` 的 `total>=1`（**本卡的核心回归点**）；
- [ ] 一次成功 → `succeeded=1`，`durationMs` 约为 `finished-start`；
- [ ] 一次失败（注入解析异常/embedding 不可用）→ `failed=1`，`error_text` **不含** key/base_url（脱敏断言）；
- [ ] `errors>0` 但正常 → 计入 `succeeded`，`errors` 如实；
- [ ] `avgDurationMs` **不含**失败 run（构造一个极快的失败 run，断言平均值不受影响）；
- [ ] 超过 500 条裁剪最旧的；
- [ ] 服务重启后统计仍在（落库证明）。

## 验收标准（DoD）

- [ ] `uv run pytest service/tests/test_index_stats.py -q` 全绿。
- [ ] **端到端行为验收（贴真实输出，本卡的核心凭证）**：
      起云端模式服务 → bootstrap → 建 token → **用真实 `npx zace-client` 走 MCP 上传**（或 curl 走
      `/api/projects/resolve` + `/api/sync/batch-upload`）→ 然后 `curl /api/index-stats`
      **必须看到 `total>=1`**。把改动前后对比贴进执行记录。
- [ ] `/api/account/overview` 的 `index` 段同步有值（`succeeded` / `avgDurationMs` 不再是 0/null）。
- [ ] 两条路径口径一致性：本地 attach 一次 + 客户端上传一次 → `total=2`，
      且两条记录的字段形态可对比（贴出来）。
- [ ] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest -o addopts="" -q`
- [ ] 任务卡"执行记录"已回填；任务板 TASK-062 那行状态改为 `review`（**本卡是 TASK-062 的补做**）。

## 明确不做

- 不改 `MetaDB.record_index_run` 的表结构或字段语义；
- 不改 `routers/sync.py`（记录点放在 `runtime.ingest` 更内聚）；
- 不改 `ProjectIndexer`（本地路径已工作，别动它）；
- 不做 TASK-061 的租户过滤（记录带 project_id 即可）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板。**必须包含**：
`/api/index-stats` 改动前 vs 改动后的真实响应对比 + 两条路径口径对照。

## 执行记录

（实施 AI 在此填写。）
