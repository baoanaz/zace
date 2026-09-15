# TASK-051：云端 MCP 就绪度盘点与远端身份预研（TASK-040R 的前置卡）

> 状态：review ｜ 阶段：Phase 2（M2c 前置，与 M2b 并行无冲突） ｜ 硬依赖：无（只读代码 + 文档） ｜ soft 依赖：TASK-040 / TASK-033（已 done）
> 建议分支：`feature/task-051_<你的缩写><MMDD>`
> 交付物所有权：
> - `docs/evidence/task-051-cloud-mcp-readiness.md`（**新建**：差距清单 + 远端身份预研 + 契约影响分级）
> - `docs/tasks/TASK-051-云端MCP就绪度与远端身份预研.md`（本卡）
>
> 清单外文件**一律不得修改**。**特别提示：本卡不改任何代码**——预研发现的问题以文档形式提交，
> 由编排者裁决后另开实现卡（预期为 TASK-040R 及其切片）。

## 目标

用户已拍板（2026-09-13）：**不妥协，直奔最终版本**——MCP 的最终形态是 `docs/design/Background/01-notace-tool-rs.md`
所述的 **本地 Rust client**（stdio 对编辑器 + HTTPS 对远端 service），本地 MCP（service 直出 Streamable HTTP）
只作短期验证。因此 TASK-040R（Rust client）不再是"视情况"，而是必经之路。

本卡是 TASK-040R 的**前置**：在写 Rust 之前，把"云端形态下现有代码到底哪里不成立"**查清、写成清单、定出方案**，
避免 Rust client 写完才发现契约缺失或服务端行为不匹配（那是最贵的返工）。

**产出被谁消费**：编排者据此裁定契约变更级别（L2/L3）并拆 TASK-040R 系列卡；实施 AI 按清单逐项实现。

## 输入文档（按序读，只读所需章节）

1. `docs/design/Background/01-notace-tool-rs.md`（**必读全文**：最终形态的参考实现报告）
2. `docs/design/Module/05-MCP与同步.md` §2（MCP 适配层）/ §3（同步客户端：忽略/BLOB/缓存/协议/checkpoint/超时）
3. `docs/contracts/openapi.yaml`（CF-05：resolve / attach / batch-upload / checkpoint / deletions / query）
4. `docs/contracts/mcp-tools.json`（CF-06：两个工具的 schema——`project_root` 是冻结参数名）
5. `docs/plan/phase2-roadmap.md` §M2c（TASK-040R 的原定范围）
6. 代码锚点（**只读**）：`service/zace_service/mcp.py`、`service/zace_service/runtime.py`、
   `service/zace_service/routers/{projects,sync,query,ops,auth}.py`、`core/zace_core/engine.py`（`repo_identity`）

## 冻结接口（本卡不得变更）

- 本卡**不产出代码**，因此不触碰任何冻结接口；预研中发现的契约缺口**只登记、不修改**。
- 契约变更必须走 `docs/plan/orchestration.md` §4：L2（新增字段/端点）或 L3（推翻决策）。

## 交付物（文件所有权）

| 路径 | 内容 |
|---|---|
| `docs/evidence/task-051-cloud-mcp-readiness.md` | 唯一交付源码：差距清单（每项含实测证据与复现命令）+ 远端身份三方案对比与推荐 + 契约影响分级 + 未决问题 |
| `docs/tasks/TASK-051-*.md` | 本卡（状态与执行记录回填） |

## 验收标准（DoD）

- [ ] `docs/evidence/task-051-cloud-mcp-readiness.md` 落盘，且**每条差距都带可复现证据**（命令 + 真实输出片段 +
      代码行号锚点），不得只有论断；
- [ ] 覆盖以下已确认的差距（编排者 2026-09-13 实测，实施 AI 须**独立复现**并在报告中给出自己的输出）：
  1. **A1 非本地模式下无任何鉴权**（最高优先级，安全）：实测服务在 `ZACE_LOCAL_MODE=false` 下
     不带任何 token/凭据调用 `POST /api/query/search` 与 MCP `tools/call` **均成功返回检索结果**，
     而 `/healthz` 却自报 `"auth": "enabled"`；
  2. **A2 云端 MCP 无可用 projectId 入口**：CF-06 的 `project_root` 是冻结参数名，远端服务端没有该目录
     （`repo_identity` 退化为 `sha256(绝对路径)`）；实测"非 git 路径 + 未 resolve"返回可操作的 isError，
     但**已 resolve 的项目仍无法通过 MCP 访问**；
  3. **A3 D-29 身份未归一化**：同一仓库 `git@github.com:acme/tool.git` 与 `https://github.com/acme/tool.git`
     得到**不同** identityKey（实测两值），与 D-29"跨机器同 repo 共享索引"的承诺冲突；
  4. **A4 宿主白名单**：验证 `mount()` 的 SDK Origin/DNS-rebinding 防护在云端（非 127.0.0.1 绑定）下行为，
     明确"是否需要 TransportSecuritySettings"；
  5. **A5 新鲜度**：远端模式下 `_rescan_if_due` 静默无效（`rescan_if_due` 要求已绑定本地 root，
     且 `attach`/`rescan` 在非本地模式 403），确认"新鲜度必须由 client 上传保证"这一结论并写出时序；
  6. **A6 不做能力层**：现状 `/api/query/ask` 是代码内固定文案的降级包，与 CF-05 声明的
     `status: [answered|insufficient_evidence|degraded]` 不等价——**必须明确"云端 MCP 的 V1 范围是否含 LLM 总结"**；
  7. **A7 README 自相矛盾**：`/healthz` 按 `local_mode` 固定返回 `auth: enabled/disabled(local)`，
     与真实鉴权状态无关——属"诚实性"缺陷，登记即可；
  8. **A8 checkpoint 不持久**：`SyncState` 把 checkpoints 落盘，但检索侧只是**透传记录、完全不消费**
     （`packmeta.py`），确认 checkpoint 的最终语义（是否要做 scope 过滤）并给出结论；
  9. **A9 首同步体验**：确认第 1 次 tool call 的行为（同步阻塞 or 进度反馈），对齐 D-31/D-32 的超时矩阵；
  10. **A10 现成资产**：列出可直接复用的实现（上传/删除/checkpoint/status 端点、`blob_hash` 契约、
      端到端测试），避免 Rust client 重复造轮子。
- [ ] 远端身份**三方案对比表**（含"是否改 CF-06 / 客户端复杂度 / 服务端是否需理解路径"三维度）+ **明确推荐**：
  - 方案甲：CF-06 增加 `projectToken` / `projectId`（L2 契约扩展，`project_root` 保留兼容）；
  - 方案乙：客户端本地算 `identityKey` → `resolve` → 传 `projectId`（**无契约变更**，Rust client 做解析）；
  - 方案丙：双模式并存，按传输自动判定（`service/HARNESS_LABEL` 文档写明差异）。
- [ ] 全仓基线保持绿（本卡不改代码，基线应与提交前一致）：
      `uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest`
- [ ] 任务卡"执行记录"已回填；任务板 `docs/tasks/README.md` 对应行状态改 `review`。

## 复现命令（编排者实测用过的；实施 AI 须独立复现并保留自己的输出）

```bash
# 1) 以"云端形态"起服务（非本地模式；不带任何 token）
export NO_PROXY=127.0.0.1,localhost
ZACE_LOCAL_MODE=false ZACE_DATA_ROOT=/tmp/zace-remote/data EMBED_MODE=local \
  uv run zace-service serve --host 127.0.0.1 --port 8899

# 2) healthz 自报 auth；随后不带凭据直接检索（A1）
curl -s http://127.0.0.1:8899/healthz
curl -s -X POST http://127.0.0.1:8899/api/query/search \
  -H 'Content-Type: application/json' -d '{"projectId":"<id>","query":"..."}'

# 3) 身份归一化（A3）：同一仓库切 remote 协议形式后比较 identityKey
uv run python -c "from zace_core.engine import repo_identity; print(repo_identity('<repo>').identity_key)"
```

## 参考实现锚点（Rust client 最终形态，只读）

- `docs/design/Background/01-notace-tool-rs.md` §3（blob 模型 / verified cache hit / 扫描忽略 / 批量上传 /
  scope 与 checkpoint 三条自愈路径 / 会话管理）/ §4（MCP 协议实现与错误三分类）/ §5（分层超时）/
  §6（值得借鉴）/ §7（zace 应改进：cache 不放工作区、`ignore` crate、rename、sync status 可见、gzip+并发）。
- **参考源码 `../source/` 在本机不存在**（见 `docs/plan/phase2-m2b-w6.md` §2.1）：本卡按报告 §7 的
  改进建议理解，不复制参考实现（Demo.md §1 纪律）。

## 明确不做

- **不写任何代码**（含 Rust、Python、配置）；不新建 `client/` 下的工程；不改 `docs/contracts/**`、
  `docs/design/**`、`core/zace_core/{types,interfaces,hashing}.py`。
- 不做 Rust client 的实现（那是 TASK-040R）；不实现鉴权/租户（TASK-060/061）。
- 不评估检索质量（R30 纪律：质量调优归 TASK-023 → TASK-050）。
- 不把"本地 MCP 已可用"当作本卡成果——本卡只诊断云端形态的差距。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写：分支 / 验收命令与结果 / 契约影响（分级列明）/
与设计偏差 / 未决问题（**须逐条给出建议裁定**，供编排者直接拍板）。

## 执行记录

### 2026-09-13 · 实施 AI · 分支 `feature/task-051_xwz0913`（从 `main` @ `42587cf` 开出）

**本卡无代码改动**（纪律：预研只出文档）。交付两个文件：

| 文件 | 内容 |
|---|---|
| `docs/evidence/task-051-cloud-mcp-readiness.md`（新建） | 云端 MCP 差距清单 A1–A10（含实测输出与行号锚点）+ 远端身份三方案对比与推荐 + 契约分级 + Q1–Q6 待裁定 |
| `docs/tasks/TASK-051-…md`（新建） | 本卡 |
| `docs/tasks/README.md`（**公共文件，按 orchestration §7 申请**） | 追加 TASK-051 行 + 波次说明 |

**验收命令与结果**

```text
$ uv run ruff check .
All checks passed!
$ uv run python scripts/check_dependency_direction.py
依赖方向检查通过（core 纯库 / service 不上探）。
$ uv run pytest -o addopts="" -q
727 passed, 2 skipped, 4 warnings in 13.76s        # 与 main 基线一致（本卡不改代码）
```

环境备注：新建的 `zace-lane-d` worktree 需先 `uv sync --all-packages --all-extras`（dev 组含 pytest/ruff；
只跑 `--all-packages` 会缺 CLI 可执行文件）。

**关键发现（编排者实测已复现，细节见报告）**

1. **A1（阻断 · 安全）**：`ZACE_LOCAL_MODE=false` 下**无任何鉴权**——不带 `Authorization`、乃至带
   **无效** token 调 `POST /api/query/search` 与 MCP `tools/call` 均返回 200/成功；
   而 `/healthz` 自报 `"auth": "enabled"`（`ops.py:43` 硬编码）。当前绑 `127.0.0.1` 尚不构成漏洩，
   **上云即完全开放**。
2. **A2（阻断 · 功能）**：CF-06 冻结的 `project_root` 在云端算不出正确 projectId
   （服务端无该目录 → `repo_identity` 退化为 `sha256(绝对路径)`）。**同机复现会掩盖此问题**（服务端恰好能读到路径）。
   已有零契约变更解法（方案乙：client 本地 resolve → MCP 传 `projectId`）。
3. **A3（L3）**：同一仓库 `git@github.com:acme/tool.git` 与 `https://…` 得到**不同** identityKey——
   与 D-29「跨机器同 repo 共享索引」的承诺冲突。
4. **A5（结论）**：远端新鲜度必须由 client 上传保证（服务端 `rescan_if_due` 无绑定即静默 `False`，
   `attach`/`rescan` 非本地模式 403）——与设计一致，非缺陷，但需在 client 侧实现完整时序。
5. **A8**：checkpoint 目前只写不读（`packmeta.py:24` 注释明确「值不参与检索」）——传输优化，非 scope 过滤。
6. **A10（好消息）**：同步面（resolve / batch-upload / deletions / checkpoint / status）**全部可用且有端到端测试**，
   伪云端全流程实测跑通（2 文件 → 5 chunks → 检索命中），Rust client 的工作量集中在本地侧。

**契约影响（分级，详见报告 §11）**

- **无契约变更**：A2 方案乙（推荐）可直接进 TASK-040R；
- **L1**：A1 的 `/healthz` 自述改诚实值；
- **L2**：A1' 云端鉴权（CF-05 已声明 bearer/cookie，仅需实现，归 TASK-060/061）；A4 若需显式
  `TransportSecuritySettings`；
- **L3**：A3（D-29 URL 归一化，会改变既有索引 identityKey）、A6（V1 是否含 LLM 总结）、A8（checkpoint 语义澄清）。

**与设计偏差**：无（本卡不改代码；报告中登记的是「实现与云端形态要求的差距」，非「实现偏离设计」）。

**未决问题（Q1–Q6，均附建议，见报告 §12）**

- Q1 云端鉴权是否作为 TASK-040R **硬依赖**？→ 建议「是」（否则 client 接的是裸服务）；
- Q2 采方案乙？→ 建议「是」；
- Q3 A3 是否现在做 URL 归一化？→ 建议做，但需接受既有索引 key 变化（L3）；
- Q4 `ask_project` V1 是否保留？→ 建议保留但如实标注降级；
- Q5 checkpoint 是否做 scope 过滤？→ 建议暂不做；
- Q6 A4 宿主白名单是否需新配置项？→ **需先实测**（列为 TASK-040R 第一验证动作）。

**建议复核点**：报告 §2 的方案乙推论链（是否接受「零契约变更」的判断）、§11 的 L2/L3 分级是否与编排者口径一致。

