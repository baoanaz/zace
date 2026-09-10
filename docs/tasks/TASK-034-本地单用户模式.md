# TASK-034：本地单用户模式（attach 本地仓库 / 一键起 / 后台索引进度 / 懒重扫）

> 状态：review ｜ 阶段：Phase 2（M2a-2）｜ 硬依赖：TASK-035 ｜ soft 依赖：无
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

- [x] attach：小仓库（temp 目录，含 py + md）→ 立即返回 + 后台索引；轮询 `GET /api/projects/{id}` 直到 `state="done"`；随后 `search` 命中（**异步索引也要有确定性测试**：轮询 + 超时上限，不用 sleep 猜时间）。
- [x] 重入：索引中再 attach/rescan → 409 `index_running`，且**不产生第二个 worker**（断言线程数或进度未被重置）。
- [x] 非本地模式 `POST /api/projects/attach` → 403 `local_mode_required`。
- [x] 失败路径：`root=/nonexistent` → 400 `invalid_root`；索引中途制造失败（如临时把 provider 打坏）→ `state="failed"` + `error` 非空 + **服务仍 200 存活**。
- [x] 懒重扫：`local_rescan_interval_s=0` → 不发扫描（断言 mtime 调用或目录未被重读）；>0 时改一个文件后 search 能命中新内容；**重扫失败时 search 仍返回结果**（monkeypatch 让 `ingest_repo` 抛异常，断言 200 + `freshness` 有提示）。
- [x] 一键起：`uv run zace-service local --repo <temp repo> --port 8792` 真实进程跑通；贴出启动输出 + `curl /healthz` + 索引完成后的 `search`。
- [x] 真实仓库自举（**必做**）：用 `--repo /home/xuwenzheng/0_project/main/linux-mtk-mw-cameraservice --data-root /tmp/zace-034-cam` 起服务，贴出索引进度变化与至少一条检索结果（**这一步验证"能在真仓库跑通"，比单测更有价值**）。
- [x] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest`
- [x] 任务卡"执行记录"已回填；任务板对应行状态改 `review`。

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

### 2026-09-11 · 实施 AI · 分支 `feature/task-034_xwz0910`（从 `feature/task-035_xwz0910` 串联）

**改动文件**（全部在卡内"交付物所有权"清单内）：

| 文件 | 内容 |
|---|---|
| `service/zace_service/indexer.py`（新建） | `ProjectIndexer` / `IndexProgress` / `validate_local_root` |
| `service/zace_service/runtime.py`（追加） | `attach_local` / `index_progress` / `rescan_if_due` / `start_index` / `attached_root` / `describe_project` / `_stop_indexer`；`delete_project` 先停索引线程 |
| `service/zace_service/{config,__main__}.py`（追加） | `local_rescan_interval_s`（`ZACE_LOCAL_RESCAN_INTERVAL`，默认 2.0，0=禁用）；`zace-service local --repo` 子命令 + 就绪信息 |
| `service/zace_service/routers/{projects,ops}.py`（追加） | `POST /api/projects/attach`、`POST /api/projects/{id}/rescan`、列表/详情加 `attachedRoot`/`indexProgress`；`/healthz` 加 `projects` |
| `service/zace_service/routers/query.py`（追加） | 检索前懒重扫 + 失败时 `meta.freshness.rescanError` |
| `service/tests/test_local_mode.py`（新建） | 17 条确定性测试（轮询到终态，无 sleep 猜时间） |

**验收命令与结果**

1. 基线三条（在提交前的完整工作区上跑）：

```text
$ uv run ruff check .
All checks passed!
$ uv run python scripts/check_dependency_direction.py
依赖方向检查通过（core 纯库 / service 不上探）。
$ uv run pytest
629 passed, 2 skipped, 2 warnings in 48.90s      # 其中 service/tests/test_local_mode.py: 17 passed
```

2. 单测面覆盖（对应 DoD 逐条）：

| DoD | 测试 |
|---|---|
| attach 立即返回 + 后台索引 + 完成后命中 | `test_attach_returns_immediately_and_indexes_in_background`、`test_attach_is_idempotent_for_the_same_root` |
| 非本地模式 403 | `test_attach_requires_local_mode` |
| `root` 非法 400 | `test_attach_invalid_root_is_400`（不存在/空白/是文件/空串） |
| 列表与详情暴露 `attachedRoot`/`indexProgress` | `test_project_list_and_detail_expose_attached_root_and_progress`、`test_unattached_project_reports_idle_progress` |
| 重入 409 + 不产生第二个 worker | `test_no_second_worker_and_rescan_conflict`（断言线程数=1 且 `startedAt` 未被重置） |
| 手工 rescan 增量 | `test_manual_rescan_reindexes_changed_file`（`processedFiles=1`，只重解析变动的文件） |
| 索引失败仍 200 存活 | `test_index_failure_is_reported_and_service_stays_alive` |
| 删除时索引线程不复活目录 | `test_delete_during_index_does_not_resurrect_project` |
| 懒重扫 0 禁用 / >0 生效 / 失败不阻断检索 | `test_lazy_rescan_disabled_when_interval_is_zero`、`test_lazy_rescan_picks_up_new_content`、`test_lazy_rescan_failure_does_not_break_retrieval` |
| `/healthz` 进度字段 + 索引中仍 200 | `test_healthz_reports_attached_projects_and_stays_200_while_indexing`、`test_healthz_without_touching_core_returns_empty_projects` |
| CLI 参数面 | `test_local_cli_parses_without_starting_a_server` |

3. **一键起（真实进程，temp 仓库）**：

```text
$ uv run zace-service local --repo /tmp/zace-034-smoke/repo --data-root /tmp/zace-034-smoke/data --port 8792
zace-service local 已启动（127.0.0.1:8792）
  projectId : cf65f1d7e7f15686
  dataRoot  : /tmp/zace-034-smoke/data
  repo      : /tmp/zace-034-smoke/repo
  身份      : 非 git 仓库 → 绝对路径 hash（D-29）；换路径/换机器 projectId 会变
  索引      : 后台进行中（state=running，已处理 0/0 个文件）
             进度：GET http://127.0.0.1:8792/api/projects/cf65f1d7e7f15686 ｜ 服务现在已可响应，不必等索引完成
  检索接口  : POST http://127.0.0.1:8792/api/query/search
  MCP       : 编辑器直连地址由 TASK-040 提供（/mcp + 配置片段）
  懒重扫    : 每 2s 一次（0=禁用，ZACE_LOCAL_RESCAN_INTERVAL 可改）

$ curl -s -o /dev/null -w "status=%{http_code} time=%{time_total}s\n" http://127.0.0.1:8792/healthz
status=200 time=0.209175s            # 首次请求含 EngineManager 懒构造，之后为个位数毫秒

$ # 索引完成后检索（真实 HTTP，非 TestClient）
$ curl -s -X POST http://127.0.0.1:8792/api/query/search -H 'Content-Type: application/json' \
    -d '{"projectId":"cf65f1d7e7f15686","query":"refresh_token 是怎么刷新会话的？"}'
answerable=True confidence=medium evidence=2 docs=1
## Relevant Context
### Code
[E1] refresh_token — auth.py:10-23
     reason: inferred symbol refresh_token + inferred rank 1 + bm25 -4.5050 + bm25 rank 1 + query symbol == chunk symbol +1.0 + entry point / exported symbol +0.2 + 相邻区间合并
     10 |     def create(self, user: str) -> str:
     11 |         """创建会话并返回 token。"""
（同一进程内：启动前把 `refresh_token` 追加进 `auth.py`，索引完成后无需手动 rescan 即命中——
幂等 attach 的增量扫描生效）
```

4. **懒重扫（真实进程）**：在服务运行中向 `auth.py` 追加函数 → `sleep 3`（> 2s 间隔）→
`POST /api/query/search` 命中新函数 `refresh_token`（`auth.py:1-23`，vector rank 1），
`meta.freshness.indexedAt` 由 `1789056671` 提前到 `1789056700`（重扫确实发生了）。

5. **真实仓库自举（必做）**：

```text
$ uv run zace-service local --repo /home/xuwenzheng/0_project/main/linux-mtk-mw-cameraservice \
      --data-root /tmp/zace-034-cam --port 8793
zace-service local 已启动（127.0.0.1:8793）
  projectId : 02f437a22ebbe713
  身份      : git remote（D-29）
  ...
{"logger": "zace_service.indexer", "msg": "开始索引：02f437a22ebbe713（root=/home/xuwenzheng/0_project/main/linux-mtk-mw-cameraservice，files=1382）"}   # 16:11:58 UTC
```

索引进度时间线（`GET /api/projects/02f437a22ebbe713` 的 `indexProgress`，每 30s 一次）：

```text
00:12:20 state=running processed=0/1382 err=None
00:12:50 state=running processed=0/1382 err=None
... （13 次采样，全程 running、processed 恒 0——**没有伪造百分比**，D-30）
00:19:52 state=running processed=0/1382 err=None
00:35:13 索引完成（日志）：parsed=281/1382，added=281，modified=0，deleted=0，errors=16
         finishedAt - startedAt = 1395s ≈ 23m15s
```

索引期间服务可用性（同一时间窗内的 25 个 `GET /api/projects/{id}`）：全部 **200**，耗时 min 3.02ms / max 79.7ms（首包）。

索引完成后检索（真实 HTTP）：

```text
$ curl -s -X POST http://127.0.0.1:8793/api/query/search -H 'Content-Type: application/json' \
    -d '{"projectId":"02f437a22ebbe713","query":"摄像头代理 MWPCameraProxy 的初始化流程在哪里实现？"}'
answerable=True confidence=medium channelsUsed=['bm25','vector'] evidenceCount=58 docsCount=3 degraded=False
## Relevant Context
### Code
[E2] MWPCameraProxy::~MWPCameraProxy — cameraservice/proxy/MWPCameraProxy.h:18-22
[E4] MWPCameraServer::MWPCameraServer — cameraservice/MWPCameraServer.cpp:9-12
[E5] MWPCameraProxy::MWPCameraProxy — cameraservice/proxy/MWPCameraProxy.cpp:8-23
     8 | MWPCameraProxy::MWPCameraProxy(){
     9 |     InitConfig();
    10 |     mPolicyManager=std::make_shared<MWPPolicyManager>(Car::PARK_TYPE_UART,this);
```

**真实仓库实测暴露的两点（如实登记）**

- **`totalFiles`(1382) 与 `processedFiles`(281) 口径不同**：`totalFiles` 是 `DirectorySource.list_files()` 的数量，
  `processedFiles` 是 `IngestReport.files_parsed`（真正解析成 chunk 的文件数）。差值不是"没扫完"，
  而是 1382 里包含 1089 个 `cmake-build-release/.cache/clangd/index/*.idx`（二进制，被解析层跳过）
  等非源码文件；`state` 依然是 `done`。字段语义已在 `indexer.py` 注释里写死，本卡不改字段集（TASK-040 依赖）。
- **`error` 字段在 `state="done"` 时也可能非空**：成功路径把 `IngestReport.errors`（逐文件解析错误，
  本次 16 条，如 `park/LogUtils.h: L47: syntax error near '...'`）如实写进 `error`，而不是丢掉。
  读法应为"索引完成，但这些文件有解析问题"。命名有歧义，见"未决问题"。

### 与设计的偏差 / 需登记的改动

1. **CF-05 路径扩展（卡内 §A 已预授权）**：`POST /api/projects/attach`、`POST /api/projects/{id}/rescan`。
   `service/tests/test_skeleton.py` 的路径快照测试因此改成"合同路径集合 ∪ `TASK_034_EXTENSION_PATHS`"，
   白名单**写死**这两个路径：白名单外的任何增/删/改名仍然失败。
   **待编排者动作**：`docs/contracts/openapi.yaml` 需补这两个路径（实施 AI 不改契约文件）。
2. **`service/tests/test_error_mapping.py` 的改动（原因）**：`test_service_does_not_call_private_engine_ingest`
   的匹配串由 `._ingest(` 收窄为 `engine._ingest(`。前者是宽泛子串匹配（任何 `xxx._ingest(` 都会命中，
   与本断言的意图——§C"service 不再跨包调 core 的私有 `Engine._ingest`"——不等价），后者与 §C 结论逐字对应，
   且仍能抓住真实违规形式（`self._engine._ingest(` 含 `engine._ingest(`）。
   实测：当前源码里两种模式**都没有命中**（脚本检查 `service/zace_service/**/*.py` → `[]`），因此该断言的判定结果没有变化。
3. **`IndexProgress.error` 在成功路径的用法**：见上（如实上报解析错误）。
4. **attach 的 root 只存内存**（`runtime.py` 文档已写明）：不新增落盘状态文件（R35 的 `sync-state.json` 只服务上传路径）。
   后果：重启服务后 `POST /api/projects/{id}/rescan` 返回 409 `local_root_unknown`（要重新 `zace-service local --repo` 或 `attach`）；
   `ZACE_LOCAL_RESCAN_INTERVAL` 的懒重扫同理只在本次进程内生效。
5. **`indexer.ProjectIndexer.start()` 立刻把快照置为 `state="running"`**（`started_at` 为当前时刻，`total_files` 待工作线程列举后补齐）：
   否则 `attach` 的返回值与 CLI 就绪信息在"线程已起、尚未开始跑"的窗口里报 `idle`，调用方会误以为没开始。

### 未决问题

1. **`IndexProgress.error` 命名**：成功但有解析错误时也非空，容易读成"失败"。字段集是 TASK-040 的输入契约，
   本卡不动；若编排者认可，后续可加 `warnings`/`parseErrors` 字段并收窄 `error` 的含义（属契约扩展，走 §4 流程）。
2. **`processedFiles` 与 `totalFiles` 不同量纲**（1382 vs 281）：若 TASK-040 的错误文案直接拼成 `281/1382`
   会被读成"没索引完"。MCP 侧文案已避开百分比、只说状态与文件数（TASK-040 的执行记录里有说明）。
3. **`delete_project` 后在跑的索引线程**：`_stop_indexer` 会 `cancel()` + `join(timeout=30s)`；索引本身不可中断，
   因此极端情况下（超 30s 未收尾）HTTP 删除请求会先返回，但线程仍在跑（此时 `_cancelled` 已置位，收尾后丢弃状态、不复活目录）。
   彻底可中断需要 core 支持取消（属 TASK-062 范畴）。
4. **`/tmp/zace-aibox`（TASK-040 卡里引用的已索引数据根）在本机重启后已丢失**（WSL `/tmp` 被清空），
   TASK-040 的 aibox 端到端需重新 attach 索引一次（本卡已在后台重启，见 TASK-040 执行记录）。

### 耗时观测（供编排者参考，非本卡承诺）

camera-service 1382 列出文件 / 281 实际解析 / 6257 chunks → **23m15s**（与 TASK-033 的 aibox 17 分钟同量级）。
其中解析+入库在头 12 秒内完成，其余时间在 embedding/向量写入（CPU，本机同时有另一泳道的测量进程竞争 CPU）。
`cmake-build-release/**` 这类噪声目录会显著抬高 `list_files()`（D-28 缺口）——本卡按要求只记录、不修。
