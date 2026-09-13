# TASK-061：租户双层（token → user → owns project）

> 状态：pending ｜ 阶段：Phase 3（M2c）｜ 硬依赖：TASK-060、**TASK-085（已合并 `735bfc3`）** ｜ soft 依赖：无
> 建议分支：`feature/task-061-tenancy_<你的缩写><MMDD>`（**从 `main` 开，已含 TASK-085**）
> 交付物所有权：
> - `service/zace_service/metadb.py`（追加 `projects` 归属表与查询）
> - `service/zace_service/deps.py`（`require_project_id` 增加归属校验）
> - `service/zace_service/routers/{projects,sync,query,ops}.py`（归属校验接入点）
> - `service/tests/test_tenancy.py`（**新建**）
>
> 清单外文件不得改。

## 目标

把 D-36 的**逻辑授权层**落地：每个请求强制校验 `projectId` 归属当前用户。
当前 `deps.py::require_project_id` 只做"项目是否存在"，**任何登录用户可以访问任何 projectId**——
在单用户本地模式下无所谓，上云即越权读取他人源码。

```text
service 层（本卡）：token → user → owns project?   每个请求强制校验
core 层（已有）    ：project_id → {data_root}/projects/{id}/   物理隔离（D-03）
```

## 输入文档（按序读，只读所需章节）

1. `docs/design/Module/06-服务化与部署.md` §2.3（租户隔离双层，含"只有逻辑层 → SQL 漏写 WHERE 即泄露"的教训）
2. `docs/design/Index.md` §3 的 D-36（两层缺一不可）
3. `docs/contracts/openapi.yaml`（所有带 `projectId` 的端点）
4. `service/zace_service/deps.py`（`require_project_id` 现状）
5. `TASK-060` 的任务卡（User / metadb 形态）

## 冻结接口（本卡不得变更）

- 消费：TASK-060 产出的 `require_user` / `metadb`。
- 产出：
  - `zace_service.metadb.owns_project(user_id, project_id) -> bool`
  - `zace_service.metadb.list_projects(user_id) -> list[str]`
  - `zace_service.metadb.claim_project(user_id, project_id, display_name)`（幂等）
  - `require_project_id(request, raw)`：**签名不变**，语义扩展为"存在 + 归属当前用户"

## §A 数据模型（追加到 `zace-meta.db`）

```sql
CREATE TABLE IF NOT EXISTS projects (
  project_id   TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  display_name TEXT NOT NULL DEFAULT '',
  created_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
```

## §A0 当前基线（2026-09-23 编排者核实，**先读**）

TASK-085 已合并（`735bfc3`），它**已经把本卡的一部分做掉了**，你要接着做剩余部分：

| 已有（TASK-085 做的，**不要重做**） | 剩余（**本卡要做的**） |
|---|---|
| `metadb.claim_project/owns_project/list_projects` 已实现（TASK-060 产出） | `require_project_id` 的**归属校验**（§C） |
| `POST /api/projects/resolve` 已补 `_claim_project`（写归属行） | `POST /api/projects/attach` 的 claim（§B 第二行） |
| `_claim_project` 的边界口径已定：**已被他人 claim 时不报错**（理由见下） | `batch-upload` 未归属 → 403（§B 第三行） |
| `GET /api/projects` 已被 `ops.py` 按 `list_projects(user_id)` 过滤 | `routers/{projects,sync,query,ops}.py` 的**逐端点**归属校验（§C 穷举） |
| — | `service/tests/test_tenancy.py`（新建） |

> **重要：TASK-085 已改过 `routers/projects.py`**，你从它的分支串联即可，不要重写 `_claim_project`。

### 已被裁定的一件事（不要推翻）

TASK-085 在 `resolve` 处**刻意不实现** §B 的「已被他人 claim → 403 `project_owned_by_other`」，
理由是：`require_project_id` 当时没有归属校验，报错会把"多人共用同一仓库的第二人"直接卡死（回归）。

**本卡的任务就是把那个前提补上**：一旦归属校验（§C）落地，共用仓库的第二人本来就会在检索时拿到 404，
此时是否要在 `resolve` 处报 403 就变成了一个**产品选择**——两种口径都自洽：

- **口径 A（保守，推荐）**：`resolve` 保持 TASK-085 的行为（不报错），越权一律由 §C 的 404 拦；
- **口径 B（严格，按卡内 §B 原文）**：`resolve` 报 403，让"抢注"在第一时间被拒。

**你必须在报告里明确写了哪个口径及理由**，并在 "未决问题" 里把另一口径的成本写清楚，交编排者复核。

## §B 归属的产生（谁"认领"一个 projectId）

三个入口，**全部改为 claim 语义**（幂等）：

| 入口 | 行为 |
|---|---|
| `POST /api/projects/resolve` | resolve 出 projectId 后 claim 给当前用户；**若已被他人 claim → 403 `project_owned_by_other`** |
| `POST /api/projects/attach`（本地模式） | claim 给本地用户（TASK-060 的 `is_local=1`） |
| `POST /api/sync/batch-upload` | **不得**隐式 claim（避免"知道 id 就能抢"）：projectId 未归属当前用户 → 403 |

`projectId` 是 `sha256(identity)`（D-29），**可被同仓库的其他人算出**。因此"谁是第一个 claim 的人"
决定了归属——这是 V1 的既定简化（Module/06 §2.3 表留 `org_id` 列，V2 才做共享）。
**本卡必须在报告中明确写出这个简化及其含义**（跨用户共享同一 repo 时第二人会被拒），供编排者判定是否接受。

## §C 校验接入点（穷举，漏一个就是越权）

所有消费 `projectId` 的端点改为经 `require_project_id`：

- `GET /api/projects` → 只返回当前用户的项目（**不是** `EngineManager.list_projects()` 的全量）
- `GET /api/projects/{id}` / `DELETE /api/projects/{id}`
- `GET /api/sync/status/{projectId}`、`POST /api/sync/{batch-upload,checkpoint,deletions}`
- `POST /api/query/{search,ask}`
- `GET /api/usage/projects/{id}`（TASK-064 实现时会用）
- `service/zace_service/mcp.py` 的 `_project_id_for`：MCP 面同样要过归属校验

**越权响应用 404 还是 403**：卡内定 **404 `project_not_found`**——403 会泄露"该 projectId 存在"。
（与 Module/06 §2.2 "不给探测面"一致。）

## §D 与本地模式的相容

`local_mode=True` 时：TASK-060 的隐式本地用户自动 claim 一切，行为与今天逐字一致（R34）。
**所有既有测试必须原样通过**，这是本卡的第一验收项。

## 验收标准（DoD）

- [ ] `uv run pytest service/tests/test_tenancy.py -q` 全绿，**必须覆盖**：
  - [ ] 用户 A 创建的项目，用户 B 用该 projectId 访问 `search`/`projects/{id}`/`sync/status`/`batch-upload`/MCP → **全部 404**（逐端点断言，不许只测一个）；
  - [ ] 用户 B 的 `GET /api/projects` 看不到 A 的项目；
  - [ ] resolve 已被他人 claim 的 identityKey → 403 `project_owned_by_other`；
  - [ ] `batch-upload` 到未归属 projectId → 403（**不得**隐式 claim）；
  - [ ] 同一用户重复 resolve 同一 identityKey → 幂等（不产生第二行、不报错）；
  - [ ] 本地模式：既有全部测试通过（回归保护）。
- [ ] 行为验收（两个真实用户、同一服务实例端到端，贴输出）：
      A 建项目并索引 → B 登录 → B 检索 A 的 projectId 得 404 → B 自己的项目正常。
- [ ] 基线三条命令全绿。
- [ ] 任务卡"执行记录"已回填；任务板对应行状态改 `review`。

## 明确不做

- 不做 org / 团队 / 共享（`org_id` 列 V1 恒 NULL，V2 预留）
- 不做项目转移/所有权变更
- 不做 per-user 配额与计费
- 不改 core（物理隔离已存在；core 字典里只有 project，D-34 不可破坏）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写，**必须逐条列出 §C 的每一个端点及其测试用例名**。

## 执行记录

（实施 AI 在此填写。） 
