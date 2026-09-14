# TASK-094：项目内存可见性 + 存储配额告警 + 历史记录 trace id + 项目删除入口

> 状态：pending ｜ 阶段：Phase 5（上线前）｜ 硬依赖：~~TASK-090~~ ✅已合并、~~TASK-088~~ ✅已合并
> 建议分支：`feature/task-094-quota-trace_<你的缩写><MMDD>`
> 交付物所有权：
> - `service/zace_service/config.py`（新增配额配置项）
> - `service/zace_service/runtime.py`（项目内存统计、配额检查）
> - `service/zace_service/quota.py`（**新建**：配额判定与告警文案，若你判断需要独立模块）
> - `service/zace_service/metadb.py`（`query_audit` 加 `request_id` 列 + migration）
> - `service/zace_service/routers/{ops,query,sync}.py`（配额告警进 tool 返回、trace id 落库）
> - `service/zace_service/mcp.py`（把告警注入工具返回）
> - `web/src/pages/{DashboardPage,HistoryPage}.tsx`、`web/src/api/{client,types}.ts`
> - `web/src/components/ui.tsx`（如需新增确认弹窗组件）
> - `service/tests/test_quota.py`（**新建**）
>
> 清单外文件不得改。**前置已解除**：TASK-088/090 均已合并（`5aac030` / `7ca94ff`），
> 本卡现在可直接开工。

## ✅ 串行约束已解除（2026-09-14 更新）

本卡原列的冲突卡**均已合并**：

| 冲突卡 | 状态 | 对本卡的影响 |
|---|---|---|
| **TASK-090** | ✅ 已合并（`7ca94ff`） | 它选了**文件轮转**方案、**没有动 `metadb.py`** —— 所以本卡改 `metadb.py` 的冲突面**归零**。`X-Request-Id` 与查询端点（`GET /api/request-log/{requestId}`）已就绪 |
| **TASK-088** | ✅ 已合并（`5aac030`） | 设置页（`/settings`）已落地；本卡的配额配置项**应展示在那里**（用已有的 `getMeta()` 扩展，参考它的做法） |

**§C 的定位澄清**：原卡建议“把 §C 并入 TASK-090”——**已不需要**。
TASK-090 做的是「请求级日志（路径/状态/耗时/错误栈，可落盘）」；
本卡做的是「**审计记录与请求 id 关联**」（`query_audit` 加 `request_id` 列，
使历史页能看到每次查询的 trace id）。两者是**互补**而非重复，保持本卡实现。

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

**默认值已由用户拍板（2026-09-14）**：

| 环境变量 | 说明 | 默认值 |
|---|---|---|
| `ZACE_STORAGE_LIMIT_PER_PROJECT_BYTES` | **单项目**存储上限 | **500 MB**（`524288000`） |
| `ZACE_STORAGE_LIMIT_PER_USER_BYTES` | **单用户**存储总额上限 | **2 GB**（`2147483648`） |
| `ZACE_STORAGE_WARN_RATIO` | 告警阈值比例（相对上限） | `0.8` |

**默认值的实测依据**（编排者测量，写进执行记录）：

| 仓库 | 可索引文件 | chunks | 索引占用 | index.db | vectors |
|---|---|---|---|---|---|
| `cockpit-agents-py` | 287 | 3,416 | **29 MB** | 15 MB | 14 MB |
| `zace` 自身 | 399 | 4,931 | **52 MB** | — | — |

**换算率：约 10 KB / chunk**（含 SQLite 索引与向量）。

- 单项目 500 MB ≈ 50,000 chunks ≈ 大几千文件的项目 → **对中型项目（29MB）有 17 倍余量**；
- 单用户 2 GB ≈ 40G VPS 可容纳约 **20 个活跃用户**；
- **超限行为：告警不阻断**（用户拍板）——避免把人卡死，尤其 V1 刚刚才有删除入口。

> **诚实标注**：上述默认值**基于两个仓库的实测外推**，样本很少（非拟合优化，但也未经真实分布校准）。
> 实现时**不要**为了“让默认值更好看”而调它——真实分布要靠上线后观察（TASK-093 的数据）。
> 若你实测发现某类正常项目会被误伤，如实写进“未决问题”。

**注意**：若 TASK-088 已落地设置页，把这三项也展示上去（只读）。

### B2. 配额判定（`quota.py` 或 runtime）

- 计算**当前用户**已用存储（其所有项目的 `diskBytes` 之和）；
- 返回三态：`ok`（< warn 比例）/ `warning`（≥ warn 比例）/ `exceeded`（≥ 上限）；
- **同时判定单项目是否超限**（`per_project` 维度）；
- **两个上限都设为 `0` 时恒为 `ok`**（保留“不限”语义，便于本地开发与测试）。

### B3. **tool 内容里告警**（用户明确要求"在 tool 的内容中报警，提示 Agent 提醒用户"）

- `search_context` 与 `ask_project` 的**返回 Markdown** 里，在 `### Meta` 之后
  追加一节（**仅在 `warning`/`exceeded` 时出现**）：

  ```markdown
  ### Storage Warning
  - 当前用户索引数据已用 8.2 GB / 上限 10 GB（82%）。
  - 建议提醒用户：可在控制台查看各项目占用，删除不再需要的项目以释放空间。
  ```

- 文案要**可直接被 Agent 转述给用户**（用户要求“提示 Agent 提醒用户进行管理内存”）；
- **超限时不拒绝新索引上传**（用户拍板：**告警不阻断**）——避免把人突然卡死；
- 告警文案里要指引用户去**控制台删除不需要的项目**（配合 §D 的删除入口，形成闭环）。
- **不得**因为配额判定失败而让检索失败（旁路纪律，与 TASK-084 的审计一致）。

### B4. UI 侧（Dashboard）

- 顶部显示“已用 / 上限”与进度提示（未设上限时只显示已用）。

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

## §D 项目删除入口（需求 4，用户 2026-09-14 追加）

**背景**：用户问「是否支持 UI 那边删除项目，来完成用户对内存的管理」——
**后端已就绪，前端缺按钮**（编排者核实）。

| 层 | 状态 |
|---|---|
| **后端 API** | ✅ **已存在**：`DELETE /api/projects/{id}`（`routers/projects.py:206`），级联删除整个项目目录（含 `index.db` / `vectors` / `blobs` / 同步账本）；走了 `require_project_id`（**含 TASK-061 归属校验**） |
| **前端 UI** | ❌ **无**：`web/src/pages/DashboardPage.tsx` 的项目表格只展示（projectId / 文件数 / chunks / 状态），**无删除操作** |

**要做**：Dashboard 的「项目」表格加一列「操作」：

```
| 项目            | 文件数 | chunks | 状态  | 占用   | 操作   |
| cockpit-agents  | 287    | 3416   | fresh | 29 MB  | [删除] |
```

**交互要求**：

1. **二次确认**：删除是破坏性操作，必须先弹确认。文案要说清后果，例如：
   「将删除该项目的**全部索引数据**（含向量与同步账本）。源码文件不受影响；
   下次 Agent 提问时会重新上传并索引。」
2. **删除后刷新列表**（不要留残影）；
3. **失败要如实报错**（404 / 网络错误都提示，不要静默）；
4. **复用现有组件**（TASK-083 的 `EmptyState` / 既有 `Card` 等），风格与既有页面一致；
5. **不要**做批量删除（V1 按项目逐个删）。

**为什么这条重要**：它是用户「自己管理内存」闭环的最后一环——
「占用可见（§A）→ 告警提示（§B）→ 一键删除（§D）」三者合起来才成立。

**后端无需改动**（端点已存在且含归属校验）；若你发现需要新增端点或改契约，**先停下来报告**。

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
- [ ] **§D 删除入口**：
  - [ ] 删除按钮点击 → **弹出二次确认**（测试断言确认文案出现）；
  - [ ] 取消 → **不发请求**（断言无 `DELETE` 调用）；
  - [ ] 确认 → 调用 `DELETE /api/projects/{id}` → **列表刷新且该项目消失**；
  - [ ] 删除失败（构造 404）→ **显示错误、不静默吞掉**；
  - [ ] **归属隔离**：他人项目删除 → 后端返 404（TASK-061 已保证，前端如实展示）。
- [ ] 基线三条命令全绿（用 `-o addopts=""` 看数字）。
- [ ] 任务卡"执行记录"已回填；任务板状态改为 `review`。

## 明确不做

- **不做硬性配额拒绝**——用户已拍板「告警不阻断」；
- 不做批量删除项目（V1 按项目逐个删）；
- 不做删除后自动重新索引；
- 不做计费/套餐；
- 不改检索质量参数（R29/R30 冻结）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板。**必须包含**：
§B 的 tool 告警 Markdown 真实输出（warning/exceeded 各一份）、
migration 的前后证据、**§D 删除入口的前端验收证据**（确认弹窗 + 删除前后列表对照）、
以及 B1 默认值的实测验证（单项目 500M / 单用户 2G 是否合理）。

## 执行记录

（实施 AI 在此填写。）
