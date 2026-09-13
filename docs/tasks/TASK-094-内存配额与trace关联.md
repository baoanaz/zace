# TASK-094：项目内存可见性 + 存储配额告警 + 历史记录 trace id

> 状态：pending ｜ 阶段：Phase 5（上线前）｜ 硬依赖：TASK-090（trace id 基础设施）、TASK-061（已合并）
> 建议分支：`feature/task-094-quota-trace_<你的缩写><MMDD>`
> 交付物所有权：
> - `service/zace_service/config.py`（新增配额配置项）
> - `service/zace_service/runtime.py`（项目内存统计、配额检查）
> - `service/zace_service/quota.py`（**新建**：配额判定与告警文案，若你判断需要独立模块）
> - `service/zace_service/metadb.py`（`query_audit` 加 `request_id` 列 + migration）
> - `service/zace_service/routers/{ops,query,sync}.py`（配额告警进 tool 返回、trace id 落库）
> - `service/zace_service/mcp.py`（把告警注入工具返回）
> - `web/src/pages/{DashboardPage,HistoryPage}.tsx`、`web/src/api/{client,types}.ts`
> - `service/tests/test_quota.py`（**新建**）
>
> 清单外文件不得改。**特别提醒：本卡与 TASK-088/090 抢 `ops.py`/`metadb.py`/`types.ts`，
> 必须排在他们之后（见下方串行约束）。**

## ⚠️ 串行约束（重要）

本卡要改的文件与下列卡重叠，**必须等它们合并后再开**：

| 冲突卡 | 重叠文件 | 说明 |
|---|---|---|
| **TASK-090** | `metadb.py`、`config.py`、`ops.py` | 它的 `request_log` 表与本卡的 `request_id` 列**是同一件事的两半**，建议**合并考虑**（见 §C 注） |
| **TASK-088** | `ops.py`、`config.py`、`web/src/api/types.ts` | 它的设置页要展示配置；本卡的配额配置也应出现在那里 |

**建议**：若 TASK-090 尚未开工，把本卡 §C 的 trace id 部分**直接并入 TASK-090**（两者本是一件事），
本卡只保留 §A/§B（内存与配额）。**由编排者决定，实施 AI 不要自行合并。**

---

## 目标（用户 2026-09-14 三条补充需求）

用户原话：

> 1、项目栏，占用多少内存。
> 2、用户存在内存上限，需要在 tool 的内容中报警，提示 Agent 提醒用户进行管理内存。
> 3、历史记录加上 trace id，方便用户报错后，能在服务端回溯问题，优化架构

---

## §A 项目栏显示占用（需求 1）

**现状**（编排者核实）：

- ✅ **后端已有**：`runtime.py:645` 的 `diskBytes`（`dir_size_bytes(project_dir)`），
  且 `GET /api/index-stats`、`GET /api/account/overview` 都返回；
- ✅ **Dashboard 顶部已有**：`DashboardPage.tsx:78` 显示 `index.diskBytes`（汇总值）；
- ❌ **缺口**：「项目」表格（`DashboardPage.tsx` 约 143 行）**没有每项目的大小列**。

**要做**：

- `GET /api/projects` 的每个项目返回 `diskBytes`（走 `describe_project`，注意**性能**：
  目录遍历在大项目上有成本，若太慢可只返回已缓存值或加 `stats` 字段说明，报告里写清口径）；
- Dashboard「项目」表格加一列「占用」（复用 `formatBytes`，已存在）；
- **口径诚实**：未测量时显示 `—`（不填 0），hint 说明"索引数据磁盘占用"
  （沿用 TASK-083 的纪律：不把"未提供"伪装成 0）。

## §B 存储上限与 tool 内告警（需求 2，本卡的核心）

**现状**：**没有任何配额机制**（`grep quota|storage_limit` 零结果）。

**要做**：

### B1. 配额配置（`config.py`，走环境变量，不写死）

| 环境变量 | 说明 | 建议默认 |
|---|---|---|
| `ZACE_STORAGE_LIMIT_BYTES` | 单用户存储上限 | `0` = 不限（V1 默认不限，用户按需开） |
| `ZACE_STORAGE_WARN_RATIO` | 告警阈值比例（相对上限） | `0.8` |

**注意**：若 TASK-088 已落地设置页，把这两项也展示上去（只读）。

### B2. 配额判定（`quota.py` 或 runtime）

- 计算**当前用户**已用存储（其所有项目的 `diskBytes` 之和）；
- 返回三态：`ok`（< warn 比例）/ `warning`（≥ warn 比例）/ `exceeded`（≥ 上限）；
- **`limit=0` 时恒为 `ok`**（不限，不打扰用户）。

### B3. **tool 内容里告警**（用户明确要求"在 tool 的内容中报警，提示 Agent 提醒用户"）

- `search_context` 与 `ask_project` 的**返回 Markdown** 里，在 `### Meta` 之后
  追加一节（**仅在 `warning`/`exceeded` 时出现**）：

  ```markdown
  ### Storage Warning
  - 当前用户索引数据已用 8.2 GB / 上限 10 GB（82%）。
  - 建议提醒用户：可在控制台查看各项目占用，删除不再需要的项目以释放空间。
  ```

- 文案要**可直接被 Agent 转述给用户**（用户要求"提示 Agent 提醒用户进行管理内存"）；
- **`exceeded` 时是否拒绝新索引上传？** —— **你需评估并给出建议，但默认不要拒绝**
  （拒绝会导致用户突然无法工作，且 V1 无删除入口的话会把人卡死）。
  把"是否硬拒绝"作为一个**给用户决策的开放问题**写进报告。
- **不得**因为配额判定失败而让检索失败（旁路纪律，与 TASK-084 的审计一致）。

### B4. UI 侧（Dashboard）

- 顶部显示"已用 / 上限"与进度提示（未设上限时只显示已用）。

## §C 历史记录加 trace id（需求 3）

**现状**：`query_audit` 表**没有 request_id 列**；`X-Request-Id` 只在响应头里，**没有落库**。

**要做**：

- `query_audit` 加 `request_id TEXT` 列（**需要 migration**：既有库要能平滑升级，
  写一条 `ALTER TABLE ... ADD COLUMN` 的兼容逻辑，并在报告里说明对既有数据的处理）；
- `query_audit` 的写入路径带上当前 `requestId`（`logging.py` 的 `contextvars` 已有该值，
  直接取即可）；
- `/api/usage/summary` 与 `/api/usage/projects/{id}` 的 `recent[]` 返回 `requestId`；
- 历史页「使用记录」页签：每条记录显示 `requestId`（**可复制**，用现有 `CopyButton`），
  并加一行说明"出现问题时可把这个 id 报给管理员，用于服务端回溯"；
- **与 TASK-090 的关系**：TASK-090 做的是"请求级日志 + 按 id 查询端点"；
  本卡做的是"**审计记录与请求 id 关联**"。两者合起来才闭环：
  用户在历史页看到某次查询的 requestId → 拿它查 TASK-090 的日志端点 → 看到完整链路。

## 验收标准（DoD）

- [ ] `uv run pytest service/tests/test_quota.py -q` 全绿，**必须覆盖**：
  - [ ] `limit=0`（不限）→ 恒 `ok`，**tool 返回里不出现告警节**（不打扰）；
  - [ ] 已用 ≥ 80% → `warning`，**tool 返回里出现 `### Storage Warning`**；
  - [ ] 已用 ≥ 100% → `exceeded`，告警文案不同（且**默认仍放行**，见 §B3）；
  - [ ] **配额判定抛异常时检索仍成功**（旁路纪律，必须有此用例）；
  - [ ] 多用户隔离：A 的用量不计入 B 的额度。
- [ ] `request_id` 落库：查库断言一条 `query_audit` 记录的 `request_id` 等于响应头的
      `X-Request-Id`（**这条必须实测，是本卡与 TASK-090 的接缝**）。
- [ ] **migration 验证**：用**已有数据的旧库**启动新代码 → 表结构升级成功、旧数据不丢
      （贴出升级前后的查询结果）。
- [ ] 前端：`cd web && npm run lint && npm test && npm run build` 全绿；
      截图或 DOM 证据证明「项目」表格有占用列、历史页有 trace id 且可复制。
- [ ] 基线三条命令全绿（用 `-o addopts=""` 看数字）。
- [ ] 任务卡"执行记录"已回填；任务板状态改为 `review`。

## 明确不做

- 不做硬性配额拒绝（除非评估后给出理由并在报告中列为待用户拍板项）；
- 不做按项目的独立配额（V1 只做按用户）；
- 不做计费/套餐；
- 不改检索质量参数（R29/R30 冻结）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板。**必须包含**：
§B 的 tool 告警 Markdown 真实输出（warning/exceeded 各一份）、
migration 的前后证据、以及"是否要硬拒绝超配额"的评估建议。

## 执行记录

（实施 AI 在此填写。）
