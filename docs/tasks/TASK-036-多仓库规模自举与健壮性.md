# TASK-036：多仓库规模自举与索引健壮性

> 状态：pending ｜ 阶段：Phase 2（M2b，**可与 M2a/M2b 其它卡并行**）｜ 硬依赖：无（core 已可用）｜ soft 依赖：无
> 建议分支：`feature/task-036_<你的缩写><MMDD>`
> 交付物所有权：
> - `benches/results/robustness-scale.md`（新建，报告）
> - `core/zace_core/{parsing,chunking,pipeline}/**`（**仅**为修复本卡实测到的崩溃/数据损坏）
> - `core/zace_core/engine.py`（**仅** §D 的一致性自检）
> - `core/tests/{parsing,chunking,pipeline,integration}/**`（回归测试）
>
> 清单外文件不得改。**不得**改 `docs/contracts/**`、`core/zace_core/{types,interfaces,hashing}.py`、
> `pipeline/source.py`（那是 TASK-037 的范围）。

## 目标

把引擎推到**本项目从未测过的规模与异构程度**上，找出真实崩溃、静默数据损坏与不可接受的行为，
修掉能修的，把不能修的写成有复现步骤的报告。

**为什么值得做**：上次同类自举（TASK-013 → TASK-018）直接发现了阻断 M1 的崩溃
（`uv.lock` 形状文件导致 chunk id 冲突 + 兜底切分行号回跳）。那次的仓库只有 215 个文件，
本卡的靶场最大 4400+ 文件、含 300MB 二进制与 1600+ 个 C++ 文件。

## 靶场（本机已存在，全部只读）

| # | 仓库 | 规模（实测） | 考什么 |
|---|---|---|---|
| 1 | `/home/xuwenzheng/2_github/others/notace-tool-rs` | 8 个 `.rs` 文件 | **无 Rust 解析器** → 兜底路径；小仓库作对照 |
| 2 | `/home/xuwenzheng/2_github/others/Obsidian-XuWenzheng` | 181 `.md`（纯文档仓库，无代码） | 文档密集 + 无代码符号；spec 检索与 `answerable` 行为 |
| 3 | `/home/xuwenzheng/0_project/main/linux-mtk-hmi-framework` | 93 可索引 / 9 MB | 小 C++ 仓库 |
| 4 | `/home/xuwenzheng/0_project/main/linux-mtk-mw-systemservice` | 107 可索引 / 160 MB（**最大单文件 76 MB**） | **超大文件**（构建产物）|
| 5 | `/home/xuwenzheng/0_project/main/linux-mtk-hmi` | **1667 可索引 / 880 MB / 301 个 >200KB 文件** | **规模上限**：C++ 大批量 + 构建产物 + 二进制 |
| 6 | `/home/xuwenzheng/2_github/AI/Trellis` | 1040 可索引 / 132 MB（1391 md + 107 py） | 混合大仓库 |

（数字是编排者实测的"可索引文件数"= 扩展名在解析器注册表内且未被内置目录跳过的文件数。）

## §A 测量与报告（必做，先做）

对每个靶场跑 `uv run zace-core ingest --repo <路径> --data /tmp/zace-scale-<n>`，记录：

- 总耗时、`files_parsed`、`chunks`、`symbols`、`edges`、`skipped_files`（含数量与**原因分布**）、
  `errors`（**完整列出，不要只报条数**）、`orphan_files`、向量库体积、索引目录体积；
- **最慢/最大文件 Top 5**（路径 + 字节数 + 产生 chunk 数 + 耗时）——这是"什么在拖慢索引"的答案；
- 增量二次运行耗时（稳态对账成本）与检索冒烟（每个仓库 1-2 条查询，贴输出）。

**时间预算纪律**（重要，防止一夜只卡在一个仓库）：

- 单仓库 ingest 用 `timeout` 限制在 **90 分钟**；超时则记录"超时 + 已处理进度"并继续下一个靶场；
- 按上表顺序从小到大跑（先拿到基础事实，再上规模）；**先跑 §A 全部，再回头修 §B 的 bug**；
- 所有命令与输出落盘（`/tmp/zace-scale-<n>/` 与报告），便于复核。

## §B 崩溃与静默损坏（修，需最小复现 + 回归测试）

按严重度处理，每条都要有：最小复现（**优先用能提交进仓库的小 fixture**，不要依赖那些真实大仓库）、
根因、修复、回归测试。历史同类问题（TASK-018）的形态供参考：

- chunk id 冲突（`UNIQUE constraint failed`）→ 必须修（阻断级）；
- 行号回跳/错位 → 必须修（数据可信度）；
- 单文件失败导致整次 ingest 中止 → 必须修（隔离）；
- **静默**丢数据（文件被处理了但 chunk 数不对、或索引为空且无 error）→ 必须修（最危险）。

**若发现的问题根因在 `pipeline/source.py`（忽略规则/大小阈值），不要改**——那是 TASK-037 的范围，
在报告里给出证据与复现，交接给它。

## §C 不接受的行为（记录 + 判据）

有些行为不一定算 bug，但对产品不可接受。遇到就记录：现象、复现、量化影响、建议（不要自己动手改设计）：

- 单文件 >50MB 时的内存/耗时（当前 `_decode` 会先读全量字节）；
- 超大文件被切出成千上万 chunk 时的嵌入耗时（是否该有上限）；
- 二进制文件（`.a` / 图片）被读取与解码的代价；
- 构建产物目录（`cmake-build-*/`）被索引的规模占比——**这是 TASK-037 的输入，给它具体数字**。

## §D 索引一致性自检（R41 附注，实现）

`chunks > 0` 但向量数为 0 是 TASK-031 实测过的"静默清空"形态，目前**完全不可见**。
在 core 侧让它可见：

- `Engine.search_with_trace` 的 `degraded` 语义扩展：向量通道为空但 chunk 非空时，
  置 `degraded=True` 且 `degraded_reason` 说明"向量索引为空（可能未重建）"；
- 测试：构造该状态（删向量表内容 / 用 `Store` 直接改）断言 `degraded` 与 `answerable` 的表现；
- **不改** `ContextPack` / `SyncStatus` 等冻结类型的字段（CF-03/CF-04 不动；本项只用既有
  `degraded` / `degraded_reason` 字段）。

## 验收标准（DoD）

- [ ] 六个靶场全部跑过 §A（超时的也要有记录），报告 `benches/results/robustness-scale.md` 含 §A/§B/§C/§D 四部分。
- [ ] §B 发现的每个崩溃/损坏：有最小复现、根因、修复、回归测试（`uv run pytest <新增测试> -q` 全绿）。
- [ ] 若某问题判断为"不该在本卡修"：报告里给出证据与所属卡（不要静默跳过）。
- [ ] §D 实现并有测试。
- [ ] 自举实证（**必做**）：至少一个真实仓库（建议 systemservice 或 hmi-framework，规模适中）
      的 `ingest` 输出**完整贴进执行记录**（含耗时、chunks、errors 为空、skipped 统计）。
- [ ] 检索冒烟：Obsidian 仓库（纯文档）与 hmi（C++）各 ≥1 条查询，贴 `search` 输出摘要
      （证明"规模上去之后检索还能用"，而不只是"索引能跑完"）。
- [ ] 基线三条全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest`
- [ ] 任务卡"执行记录"已回填；任务板对应行状态改 `review`。

## 明确不做

- **不改忽略规则 / 大小阈值 / 二进制判定**（TASK-037）。
- 不调检索质量参数（R30 冻结）。
- 不为通过指标而抽掉大仓库（跑不动就如实报告，那本身就是结论）。
- 不引入新依赖。
- 不做性能优化工程（只测量与报告；优化归 TASK-062 与后续卡）。

## 参考源码锚点（只读）

- `core/zace_core/pipeline/indexer.py`（`_decode` / `skipped_files` / 失败隔离）
- `core/zace_core/parsing/fallback.py`（无解析器时的兜底切分）
- `core/tests/integration/test_m1_pipeline.py`（既有跨模块测试形态）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写；**必须包含六靶场汇总表与每条修复的复现**。

## 执行记录

（实施 AI 在此填写。）
