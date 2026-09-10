# TASK-034：本地单用户模式（attach 本地仓库 / 一键起 / 后台索引进度 / 懒重扫）

> 状态：pending ｜ 阶段：Phase 2（M2a-2）｜ 硬依赖：TASK-035 ｜ soft 依赖：无
> 建议分支：`feature/task-034_<你的缩写><MMDD>`
> 交付物所有权：
> - `service/zace_service/runtime.py`（追加 attach / 后台索引 / 重扫；既有引擎方法语义不改）
> - `service/zace_service/{config,__main__}.py`（追加本地模式参数与启动流程）
> - `service/zace_service/routers/{projects,ops}.py`（attach 端点、healthz 进度字段）
> - `service/zace_service/indexer.py`（新建：单项目后台索引 worker）
> - `service/tests/test_local_mode.py`（新建）
>
> 清单外文件不得改。

## 目标

让"本机自己用"这件事真正成立（demo 的最后一段地基）：

```text
zace-service local --repo /path/to/repo        # 一条命令：绑定仓库 + 后台索引 + 起服务
→ 索引期间 /api/sync/status 如实报告进度（D-30：不许假装已就绪）
→ 索引完成后编辑器（TASK-040 的 MCP 端点）立即可用
```

**为什么需要后台索引**：TASK-033 实测 aibox 规模全量索引 ~17 分钟，同步阻塞会让服务在启动时不可用，
且用户看不到任何进展（Module/05 §3.5 的 D-31 就是为解决这个——本卡是它的**本地模式简化版**）。

## 输入文档（按序读，只读所需章节）

1. `docs/design/Module/05-MCP与同步.md` §3.5（首同步与进度反馈）、§3.6（freshness 语义）、§4（超时矩阵）
2. `docs/design/Module/06-服务化与部署.md` §2.4（索引 job：**本卡只做单项目后台线程，不做 job 表/worker 池**）、§4B（本地形态）
3. `docs/plan/contracts.md` §3.8（R34 本地模式免鉴权、R35 状态落文件、R36 source 参数、R37 projectId 可省略）
4. `core/zace_core/engine.py`（`resolve_repo` / `ingest_repo` / `sync_status`：**attach 的既有能力已存在**）
5. `core/zace_core/pipeline/indexer.py::IngestReport`（progress 字段来源）

## 冻结接口（本卡不得变更）

- **消费**：CF-05（新增路径见下，属**扩展**）、CF-07、`IngestReport` 字段。
- **产出**（TASK-040 依赖）：
  - `EngineManager.attach_local(root, *, display_name="", index=True) -> AttachResult`
  - `EngineManager.index_progress(project_id) -> IndexProgress`（`state: idle|running|failed|done`、`started_at`、`finished_at`、`processed_files`、`total_files`、`error`）
  - `EngineManager.rescan_if_due(project_id, *, min_interval_s: float) -> bool`（本地模式懒重扫）
  - `GET /api/projects` 列表项增加 `attachedRoot`（本地模式）与 `indexProgress`

## §A 路径与语义（新增，属 CF-05 扩展，登记在卡内即可）

| 方法 | 路径 | 语义 |
|---|---|---|
| POST | `/api/projects/attach` | body `{root, displayName?}` → `{projectId, created, root, indexProgress}`；**仅本地模式**（非本地 → 403 `local_mode_required`） |
| POST | `/api/projects/{id}/rescan` | 手动触发增量重扫 → 202 `{indexProgress}`（已在跑 → 409 `index_running`） |
| GET | `/api/projects/{id}` | 追加 `attachedRoot` / `indexProgress`（既有字段不动） |

路径校验：`root` 必须是存在的**目录**；不存在 → 400 `invalid_root`。
**不做** git 仓库校验（Module/01 §6-1 说"一 project 一 repo"，但本地模式下允许指向任意目录，
按 core 既有 identity 规则（D-29）解析——非 git 目录会退化为绝对路径 hash，**在响应里如实提示**（R27））。

## §B 后台索引 worker（`indexer.py`）

- 每 project **最多一个**在跑的索引任务；重复触发返回 409/忽略（不要排队堆积）。
- 用 `threading.Thread(daemon=True)`，内部调 `Engine.ingest_repo(project_id, root)`（**已存在，不要重写**）；
  完成后刷新进度、记录 `IngestReport` 摘要。
- **进度语义**：core 的 `ingest_repo` 是全同步的、不回调 → `processed_files` 用**扫描阶段**的已知总数
  （`plan_scan` 的规模）+ `IngestReport.files_parsed` 作为终值；**索引期间 `state="running"` 但
  `processed_files` 允许为 0**——**不许伪造进度百分比**（D-30 诚实性；宁可只说"进行中"）。
  若要更细粒度，走 TASK-062，不在本卡。
- 失败：`state="failed"` + `error`（脱敏）写进进度；**不得**把异常吞掉或让线程静默死掉。
- 与 `EngineManager` 的锁：索引线程持 per-project 锁，`delete_project` 必须能安全中断（删除后不复活目录）。

## §C 懒重扫（本地模式的 D-27）

- 语义：本地模式下 service 与代码在同一文件系统 → **不需要客户端上传**；改为服务端在检索前做增量重扫。
- `rescan_if_due(project_id, min_interval_s)`：距上次扫描 < `min_interval_s` 则跳过；否则在检索前同步执行
  增量 `ingest_repo`（**不是全量**，只处理变化的文件）。
- 触发点：`routers/query.py` 在 search/ask 前调用（**只在本地模式**；远端模式走客户端上传，不适用）。
- 默认间隔由 `Settings.local_rescan_interval_s`（默认 2.0，可用 `ZACE_LOCAL_RESCAN_INTERVAL` 覆盖）；
  **设为 0 表示禁用**（用于测试与"只读演示"）。
- **纪律**：重扫失败**不得**让检索失败——记日志、把失败写进 `meta.freshness`（作为 `stale_files` 的补充信号），
  照常返回既有索引的检索结果（D-30：如实报告，不阻断）。

## §D 一键起（`__main__.py`）

```text
zace-service local --repo /path/to/repo [--data-root ~/.zace] [--port 8787]
  1. 强制 local_mode=True（忽略 ZACE_LOCAL_MODE=false 并告警）
  2. resolve_repo → projectId（D-29 身份）
  3. 起后台索引（§B），立刻开始监听（不等索引完成）
  4. 打印人类可读的就绪信息：projectId / dataRoot / 索引进度提示 / 下一步（MCP 配置片段，TASK-040 后补全）
  5. 另保留 zace-service serve（不带 --repo，纯服务模式）
```

- `/healthz` 追加：`projects: [{projectId, attachedRoot, indexProgress}]`（**不加载模型**，不得因索引中而变慢）。
- 索引进行中 `GET /healthz` 仍 200（服务是活的）；**只有** search/ask 在目标 project 未就绪时按 TASK-032 的
  409 `index_in_progress` 返回，且 message 里带**当前状态与已处理文件数**。

## 验收标准（DoD）

- [ ] attach：小仓库（temp 目录，含 py + md）→ 立即返回 + 后台索引；轮询 `GET /api/projects/{id}` 直到 `state="done"`；随后 `search` 命中（**异步索引也要有确定性测试**：轮询 + 超时上限，不用 sleep 猜时间）。
- [ ] 重入：索引中再 attach/rescan → 409 `index_running`，且**不产生第二个 worker**（断言线程数或进度未被重置）。
- [ ] 非本地模式 `POST /api/projects/attach` → 403 `local_mode_required`。
- [ ] 失败路径：`root=/nonexistent` → 400 `invalid_root`；索引中途制造失败（如临时把 provider 打坏）→ `state="failed"` + `error` 非空 + **服务仍 200 存活**。
- [ ] 懒重扫：`local_rescan_interval_s=0` → 不发扫描（断言 mtime 调用或目录未被重读）；>0 时改一个文件后 search 能命中新内容；**重扫失败时 search 仍返回结果**（monkeypatch 让 `ingest_repo` 抛异常，断言 200 + `freshness` 有提示）。
- [ ] 一键起：`uv run zace-service local --repo <temp repo> --port 8792` 真实进程跑通；贴出启动输出 + `curl /healthz` + 索引完成后的 `search`。
- [ ] 真实仓库自举（**必做**）：用 `--repo /home/xuwenzheng/0_project/main/linux-mtk-mw-cameraservice --data-root /tmp/zace-034-cam` 起服务，贴出索引进度变化与至少一条检索结果（**这一步验证"能在真仓库跑通"，比单测更有价值**）。
- [ ] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest`
- [ ] 任务卡"执行记录"已回填；任务板对应行状态改 `review`。

## 明确不做

- 不做 job 表 / worker 池 / 多项目排队 / 进度百分比（TASK-062）。
- 不做 `.gitignore` 解析（**已知缺口**：`DirectorySource` 只有内置跳过规则；本地模式下这会让索引包含
  `cmake-build-*/`、`.claude/skills/**` 等噪声。本卡**记录**该缺口，修不修由编排者定——不要顺手实现）。
- 不做客户端上传路径的任何改动（TASK-033 语义不变；远端模式仍走 blobs）。
- 不做鉴权（M2c）。
- 不改 core 的 `ingest_repo` / `plan_scan` 行为。

## 参考源码锚点（只读）

- `core/zace_core/engine.py`：`resolve_repo`（identity 绑定）、`ingest_repo`（增量扫描+索引）、`read_manifest`/`write_manifest`
- `service/zace_service/runtime.py`（TASK-031 的 `EngineManager` 与 per-project 锁）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写；**必须包含真实仓库的索引进度时间线**。

## 执行记录

（实施 AI 在此填写。）
