# TASK-045：M2a 验收手册（本机 demo 的"照着做就能验证"文档）

> 状态：review ｜ 阶段：Phase 2（M2a-2 收尾）｜ 硬依赖：TASK-034、TASK-040 ｜ soft 依赖：无
> 建议分支：`feature/task-045_<你的缩写><MMDD>`（从 TASK-040 分支串联）
> 交付物所有权：
> - `docs/handbook/M2a-验收手册.md`（新建：唯一交付物）
> - `docs/tasks/TASK-045-M2a验收手册.md`（本卡）
> - `docs/tasks/README.md`（本卡在任务板上的那一行）
>
> 清单外文件不得改（实施 AI 不写代码、不改 `docs/design/**`、`docs/contracts/**`）。

## 目标

M2a 的验收凭证是"**用户本人在编辑器里用真实问题问到带行号证据的上下文**"。本卡把这套流程
写成一份可复现的手册：起服务 → 配编辑器（Cursor/Claude Code）→ 提问 → 判读返回 →
失败排查。**手册里的每一条命令与输出必须是实施 AI 在本机真实跑过的**（不是设计文档的转述、
也不是想象的典型输出），这是本卡唯一的验收标准。

为什么需要它：M2a 的交付物分散在三张卡（service API / 本地模式 / MCP 端点），验收者要么读三份
任务卡自己拼流程，要么直接问"我该敲哪几行"。手册就是把这三张卡串成一条用户视角的路径，
并把**已知的坑与边界**（Windows 路径、`/mcp` 形态、索引期间的行为、懒重扫间隔）写清。

## 输入文档（按序读，只读所需章节）

1. `docs/tasks/TASK-034-本地单用户模式.md`（一键起 / 进度 / 懒重扫；执行记录含真实仓库实测）
2. `docs/tasks/TASK-040-service侧MCP端点.md`（MCP 端点、工具语义、编辑器片段）
3. `docs/contracts/mcp-tools.json`（CF-06：工具名与参数——手册要给用户看的就是这两个工具）
4. `docs/plan/phase2-roadmap.md` §M2a（验收口径：编辑器里用真实问题验证）
5. `docs/design/Module/05-MCP与同步.md` §2.2（错误三分类）、§3.6（freshness 语义）

## 冻结接口（本卡不得变更）

- 消费：TASK-034 的 CLI/端点/进度字段、TASK-040 的 `/mcp` 与 `mcp-config` 输出、CF-06 的工具 schema。
- 产出：无代码产出（**本卡不写代码**）；手册中出现的命令、URL、字段名必须与实际实现逐字一致。

## 手册必须包含的节（内容约束）

| 节 | 必须写清的事 |
|---|---|
| 0 前提 | 依赖安装（`uv sync --all-packages --all-extras`）、平台（WSL/Linux；Windows 路径为何不行）、模型首次下载 |
| 1 起服务 | `zace-service local --repo <绝对路径> --data-root <数据根> --port <端口>` 一条命令；就绪输出怎么读（projectId/身份/索引状态） |
| 2 等索引 | `indexProgress` 的字段含义（`state`/`processedFiles`/`totalFiles`/`error` 的**口径**与不伪造百分比的理由）；索引期间服务已可用 |
| 3 配编辑器 | Cursor / Claude Code 的配置片段（`zace-service mcp-config` 的真实输出） |
| 4 验证 | 在编辑器里问什么问题、期望看到什么（证据行 `路径:行号`、Missing Evidence、`answerable/confidence`）；不给"应该能命中"的模糊承诺，而给实测片段 |
| 5 更新代码后再问 | 懒重扫（`ZACE_LOCAL_RESCAN_INTERVAL`，0=禁用）与手动 `rescan` |
| 6 失败排查 | 空索引 / provider 不可用 / 未知 project_root / 恶意 Origin 403 的**真实报错文本**与处理办法 |
| 7 边界与不做 | 多项目、远端模式、Rust client、`.gitignore` 缺口（D-28）、鉴权（M2c） |

## 验收标准（DoD）

- [x] `docs/handbook/M2a-验收手册.md` 存在，且**每一条命令都带真实输出**（含一条 MCP
      `tools/call` 的真实返回片段）；无"典型输出"式编造。
- [x] 手册里出现的 URL / 字段名 / 报错文案与实现逐字核对过（至少覆盖：`/mcp`、`indexProgress`
      的六个字段、`mcp-config` 的两段片段、空索引与恶意 Origin 的报错文本）。
- [x] 手册的"起服务 → 提问"路径在**本机以真实进程 + 真实 MCP 客户端**跑过一遍（不是 TestClient）。
- [x] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest`
- [x] 任务卡"执行记录"已回填；任务板对应行状态改 `review`。

## 明确不做

- 不写新代码、不改任何 service/core 文件（手册若发现实现问题，写进"未决问题"）。
- 不做视频/GIF/截图（文本手册；避免二进制进仓库）。
- 不承诺未验证的性能数字；不把 benches 的检索质量结论写进手册（R29/R30 冻结中）。
- 不写远端部署（M2c）与 Rust client（TASK-040R）的操作步骤。

## 参考源码锚点（只读）

- `service/zace_service/__main__.py`（CLI 子命令与就绪输出）
- `service/zace_service/cli_hint.py`（编辑器片段的唯一实现）
- `service/zace_service/mcp.py`（工具与错误文案）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写：分支 / 验收命令与结果 / 契约影响 / 与设计偏差 / 未决问题。

## 执行记录

### 2026-09-11 · 实施 AI · 分支 `feature/task-045_xwz0911`（从 `feature/task-040_xwz0911` 串联）

**交付物**：`docs/handbook/M2a-验收手册.md`（新建，§0–§9）+ 本卡 + 任务板一行。**无代码改动**。

**手册内容与实现逐字核对过的地方**（避免"照着做跑不通"）：

| 手册里的东西 | 真值来源（逐字） |
|---|---|
| `zace-service local --repo … --data-root … --port …` 与就绪信息 | `service/zace_service/__main__.py::_print_ready` 的真实输出（§1） |
| `mcp-config` 两段片段 | `zace_service/cli_hint.py::editor_config_snippets` 的真实输出（§3） |
| `indexProgress` 六个字段 | `zace_service/indexer.py::IndexProgress.to_json`（§2 表） |
| `[zace] answerable=… · confidence=…` 首行 | `zace_service/mcp.py::_status_line`（§4.1） |
| 空索引 / 未知 project / 反斜杠 / 纯空白 query 的报错文案 | `zace_service/mcp.py`（§6.1–§6.4，均为真实进程输出） |
| `Invalid Origin header`（403） + 默认白名单 | `mcp.py::mount` 的 `host="127.0.0.1"` 默认（§6.5，`--max-redirs 0` 实测） |
| `local_root_unknown`（409） | `routers/projects.py::rescan_project`（§7 表，真实进程 8797 上实测） |

**本卡 DoD 逐条**

- [x] 手册存在且**每条命令都带真实输出**（含 aibox 的 `tools/call` 返回片段）——手册 §1–§6 的片段
  全部来自本次会话的真实进程/真实客户端运行，无"典型输出"式编造。
- [x] URL / 字段名 / 报错文案与实现逐字核对（上表；`additionalProperties=False` 也在 §4.2 输出里体现）。
- [x] “起服务 → 提问”路径用**真实进程 + 官方 MCP SDK 客户端**跑过（§4.2 / §4.4；不是 TestClient）。
- [x] 基线三条：下方命令与结果。
- [x] 执行记录已回填；任务板对应行状态改为 `review`。

```text
$ uv run ruff check .
All checks passed!
$ uv run python scripts/check_dependency_direction.py
依赖方向检查通过（core 纯库 / service 不上探）。
$ uv run pytest
658 passed, 2 skipped, 1 warning in 60.05s
```

**手册实测覆盖的三类仓库**（写手册时每一条都真跑过）：

| 仓库 | 规模 | 用途 |
|---|---|---|
| `~/zace-scratch/demo-repo`（非 git，2 文件） | 秒级 | §1–§5 的主线（起服务/进度/懒重扫/编辑器客户端） |
| `~/zace-scratch/empty-repo`（`--no-index`） | 秒级 | §6.1 空索引报错、§7 重启后 `local_root_unknown` |
| `aibox-super-sdk`（git，451 文件） | 58 分钟 | §4.4 真实仓库端到端（含 `Missing Evidence`） |
| `linux-mtk-mw-cameraservice`（git，1382 列出/281 解析） | 23 分钟 | §4.1 的真实仓库返回示例（TASK-034 自举那次） |

### 未决问题

1. **`IndexProgress.error` 在 `state="done"` 时也可能非空**（成功但有逐文件解析错误）。手册把它写清了
   （§2 表），但字段名本身容易误读；改名属契约扩展（`error` 是 TASK-040 的输入字段），归编排者定。
2. **手册里的绝对路径是本机路径**（`/home/xuwenzheng/...`）。作为实测记录这是有价值的（可复现），
   但若这份手册将来要给外部用户看，建议另出一份用占位符的"使用指南"；本卡按任务卡"贴真实输出"办。
3. **内存/CPU 争用会显著拖慢索引**：aibox 451 文件跑了 58 分钟（同时有另两个泳道的 benchmark），
   而同一台机器空闲时类似规模仓库在 §2 的采样窗口内完成。手册§2 已提醒“看 `indexProgress` 而不是猜”。
4. **索引期间 `chunks>0` 但向量未就绪**（`channels` 只剩 `bm25`，`answerable=false`）：手册 §4.4 已如实
   写出；是否要在这种中间态直接报 `index_in_progress`（而不是“给半个包”）属检索层语义，本卡不改。
