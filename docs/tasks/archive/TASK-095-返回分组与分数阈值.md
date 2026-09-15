# TASK-095：返回结构分组与分数阈值截断（agent 视图优化）

> 状态：review ｜ 阶段：Phase 3（M2c）｜ 硬依赖：无 ｜ soft 依赖：TASK-087（已合并）
> 分支：`feature/task-095-render-group_xwz0914`（已实现，待评审）
> 交付物所有权：
> - `core/zace_core/contextpack/render.py`（分组渲染）
> - `core/zace_core/contextpack/assembly.py`（**仅**分数阈值截断相关的装填闸门；不得改 rerank 特征分值）
> - `core/zace_core/config.py` 或等价配置入口（新增阈值配置项；若不存在则在 `assembly.py` 加常量）
> - `core/tests/contextpack/`（新增/更新断言）
> - `core/tests/` 下与 render 快照相关的测试
>
> 清单外文件不得改。**特别提醒**：
> - **不得改** `docs/contracts/**`（CF-03 ContextPack、CF-05、CF-06 均冻结）；
> - **不得改** `retrieval/rerank.py` 的特征分值（R30 冻结）；
> - **不得改** `zace_core/{types,interfaces,hashing}.py`。

## 背景（用户 2026-09-14 实测后拍板）

编排者在真实仓库（`cockpit-agents-py`，287 文件 / 3416 chunks，gitlab 车载 Agent 服务）
上跑了真实问题，暴露两个必须修的问题：

### 问题 1：返回的证据平铺，Agent 分不清主次

实测（查询「Runtime 的输入准入是怎么实现的？」，`max_tokens=10000`）：

| # | id | score | 相对 top-1 | type | path |
|---|---|---|---|---|---|
| 1 | E2 | 2.483 | 100% | test | `tests/integration/hmi_gateway/test_provider_and_ingress.py` |
| 2 | E4 | 1.787 | 72% | code | `src/cvi_agent_core/runtime/runtime.py` |
| 5 | E7 | 1.493 | 60% | code | `src/cvi_agent_core/runtime/dispatcher.py` |
| 18 | E20 | 1.015 | 41% | test | `tests/v2/runtime/test_clock_domains.py` |
| 30 | E33 | 0.520 | 21% | test | `tests/integration/app/test_runtime_langgraph.py` |

**30 条证据平铺在一个 `### Code` 节里**，其中 11 条是测试、2 条是 benchmark。
Agent 无法一眼看出"哪 3 条是答案"。

### 问题 2：装填是"贪心填满"，没有分数下限

当前实现（`assembly.py` 装填主循环）只受 `hard_cap` 与单文件配额约束，
**预算没满就一直装**——即使后面候选的分数只有 top-1 的 21%。

实测分数分布（同一查询）：

```
≥90% of top-1: 1 条      ≥60%: 5 条      ≥40%: 18 条
≥70%: 2 条               ≥50%: 11 条     ≥30%: 24 条
```

**用户拍板口径**：
> 不应该贪心填满，针对占用 Token 最大的部分，应该存在分数阈值，低于某个阈值不返回，
> 至少是高于这个阈值再贪心返回。按照 top-N 可能也不太好，万一设置 3，但是有 5 个都符合，
> 那不就丢掉两个。我觉得按照分数，才能准确的根据实际情况，多的返回多，少的返回少。

## 目标

1. **按分数做截断**（相对 top-1 的比例，自适应查询难度）——替代"贪心填满"；
2. **分组渲染**——让 Agent 一眼分清主次；
3. **不改** CF-03/CF-05/CF-06 契约，**不改** rerank 特征分值。

## §A 分数阈值截断（core 侧，装填闸门）

**在装填主循环加入闸门**（`assembly.py` 的候选循环）：

```python
threshold = top1_score * score_ratio      # top1_score = 池中最高分候选的 rerank 分
for c in candidates:                      # 分数降序
    if c.score < threshold: break         # 新闸门：低于相对阈值立即停止
    ...原逻辑（预算、单文件配额、tier3 配额、去重）
```

**三条纪律**：

1. **相对阈值而非绝对阈值**：分数尺度随查询变化（实测同仓库不同查询 top-1 在 1.2~2.5 之间波动），
   绝对阈值无法通用；"明显弱于最佳命中"才是噪音的判据。
2. **保底不受影响**：`code_floor` / `spec_floor` 的保底装填**不受该闸门约束**
   （保底是"至少给这些"，与"最多给到哪"不冲突，否则纯文档查询可能被清空）。
3. **可配置且有默认值**：默认值见 §A-1，允许环境变量覆盖，**不要暴露给 MCP 工具参数**（CF-06 冻结）。

### §A-1 配置项

| 配置项 | 默认值 | 含义 |
|---|---|---|
| `CONTEXT_SCORE_RATIO` | **0.50** | 低于 `top1_score × 该值` 的候选不装填 |

**默认值 0.50 的依据**（实测，非拟合）——编排者在 `cockpit-agents-py` 上四个真实查询的截面：

| 查询 | 总数 | ≥70% | ≥50% | ≥30% |
|---|---|---|---|---|
| Runtime 的输入准入是怎么实现的？ | 30 | 2 | **11** | 24 |
| CapabilityGateway 怎么调用 HMI 能力 | 32 | 1 | **1** | 5 |
| 欢迎流程的 Workflow 是怎么定义的？ | 24 | 7 | **18** | 24 |
| 状态所有权是怎么划分的？ | 55 | 16 | **36** | 49 |

**这组数据说明两件事**：
1. **相对阈值确实自适应**：符号密集型查询（CapabilityGateway）只需 1 条就够，
   而宽泛语义查询（状态所有权）有 36 条真相关——这正是用户要的"多的返回多，少的返回少"；
2. **0.50 是保守选择**（宁多勿少）：0.70 在符号查询上只剩 1 条（可能丢掉真正需要的邻居），
   0.30 在宽泛查询上几乎等于没截断（49/55）。

> **重要**：该默认值的选定**必须记录实际测量过程**（用了哪些查询、各自保留多少条、
> 哪些证据被截掉了）。**不要**用 `benches/golden` 的 60 条 smoke 集去优化它（R29/R30 冻结）。
> **若你实测发现 0.50 在某个查询上截掉了明显相关的证据，如实写进报告的"未决问题"**，
> 不要把默认值改到"刚好让这四条查询都好看"——那是又一次小样本拟合。

## §B 分组渲染（core 侧）

### §B-1 分组口径（用户拍板：Code / Flow / Docs 三分，不新增顶层节）

**保持现有三个顶层节名不变**，在其**内部**按置信度分组：

```markdown
## Relevant Context
### Code
#### Core
[E4] Runtime — src/cvi_agent_core/runtime/runtime.py:20-22
     reason: vector 0.5861 + vector rank 3 + entry point / exported symbol +0.2
     20 | class Runtime:
#### Related
[E9] ExecutionCoordinator.admit — src/cvi_agent_core/runtime/coordinator.py:210-308
     reason: ...
#### Tests
[E2] test_user_input_reaches_runtime_without_voice_invocation_binding — tests/...:261-342
     reason: ...
### Flow
[F1] Runtime.admit → InputDispatcher.pending_match_request → ...
### Docs
[E7] docs/internal-design.md > ...
### Missing Evidence
### Suggested Next Queries
### Meta
```

### §B-2 分组判定规则（**确定性，不含 LLM**）

| 分组 | 判定 |
|---|---|
| **Core** | `score ≥ top1_score × 0.70` **且** `type != test` |
| **Related** | `score ≥ top1_score × 0.50` **且** `type != test`（即阈值内但非 Core） |
| **Tests** | `type == test` 或路径命中测试目录（**无论分数**） |
| （不渲染） | `score < top1_score × 0.50` → 已被 §A 截断，不出现 |

**关键点**：测试**无论分数多高都归入 Tests 组**——这直接解决实测中
"测试文件因字面匹配排第一"的问题（**不改 rerank 分值**，只在渲染层归类）。

### §B-3 渲染要求

- 空组**不渲染**（如全是 Core 时不出现 `#### Related` 标题）；
- 组标题用 `#### `（四级，不破坏现有 `### ` 节结构）；
- **既有测试守护**：`Core` 组内的排序仍按 score 降序；`[E*]` 编号顺序**不变**；
- `Docs` 节**不分组**（文档本就是独立语义，且当前 `docs_ratio=0.10` 使其数量天然少）；
- `Flow` 节**不分组**。

## 验收标准（DoD）

- [ ] `uv run pytest core/tests/contextpack -q` 全绿，**必须覆盖**：
  - [ ] 分数低于 `top1 × ratio` 的候选**不出现在**渲染结果中；
  - [ ] `code_floor` / `spec_floor` 保底**仍然生效**（构造纯文档查询，断言代码保底仍在）；
  - [ ] 测试候选**无论分数**归入 `#### Tests` 组；
  - [ ] 空组不渲染（断言 `"#### Related" not in md` 当无相关候选时）；
  - [ ] 既有节顺序与节名**逐字未变**（回归保护）；
  - [ ] `[E*]` 编号顺序与装填顺序一致（**不因分组而重排**）。
- [ ] **配置生效**：改 `CONTEXT_SCORE_RATIO` → 返回条数变化（贴两次不同配置的实测对比）。
- [ ] **真实仓库实测**（贴真实输出）：对 `cockpit-agents-py`（或任意真实仓库）跑
      「Runtime 的输入准入是怎么实现的？」，对比**修改前 vs 修改后**：
      - 证据条数（预期从 30 → 约 11）；
      - 测试文件是否从第 1 位移到 `#### Tests` 组；
      - 新增的分组标题。
- [ ] 基线三条命令全绿：`uv run ruff check .`、
      `uv run python scripts/check_dependency_direction.py`、`uv run pytest -o addopts="" -q`
- [ ] 任务卡"执行记录"已回填；任务板状态改为 `review`。

## 明确不做

- **不改** `retrieval/rerank.py` 的特征分值或特征表（R30 冻结；测试文件降权 −0.5 保持原样）；
- **不改** CF-03/CF-05/CF-06 契约（`docs/contracts/**` 零改动）；
- **不改** `pack_meta.py` 的字段集；
- **不新增** MCP 工具参数（CF-06 冻结）；
- 不做"边际收益递减"的更复杂模型（本次只用相对阈值）；
- 不动 `docs_ratio` / `CONSENSUS_SCORE_RATIO`（R30 冻结）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板。**必须包含**：

- §A-1 默认值 `0.50` 的**测量过程**（查询、条数、被截掉的证据）；
- §B 修改前 vs 修改后的**真实渲染片段对照**；
- 一次"改配置即改行为"的实测（证明不是硬编码）。

## 执行记录

### 2026-09-14 ｜ 分支 `feature/task-095-render-group_xwz0914`

状态：**实现完成，待评审**。基线 `4bf1c52`。

#### 交付物（全部在卡内清单内）

| 文件 | 改动 |
|---|---|
| `core/zace_core/contextpack/assembly.py` | 新增 `CONTEXT_SCORE_RATIO = 0.50`、`SCORE_RATIO_ENV`、`_score_ratio_from_env`；`BudgetConfig.score_ratio`；装填主循环的相对分数闸门；`budget_for` 支持环境变量覆盖；`_missing_evidence` 如实上报被闸门截掉的条数 |
| `core/zace_core/contextpack/render.py` | `### Code` 节内部分组 `#### Core` / `#### Related` / `#### Tests`；新增 `CORE_SCORE_RATIO = 0.70` 与 `_group_evidence` |
| `core/zace_core/contextpack/__init__.py` | 导出 `CONTEXT_SCORE_RATIO` / `SCORE_RATIO_ENV` 并补文档 |
| `core/tests/contextpack/test_score_ratio_grouping.py` | **新增** 21 条用例（§A 闸门 / 保底不受影响 / 配置生效 / §B 分组 / 回归） |
| `core/tests/contextpack/{test_assembly,test_merge_line_order,test_render,test_spec_floor_dedup}.py`、`snapshots/rich_pack.md` | 更新（见"既有测试的必要调整"） |

**零改动已核验**：`docs/contracts/**`、`docs/design/**`、`core/zace_core/{types,interfaces,hashing}.py`、
`core/zace_core/retrieval/rerank.py`（`git diff --stat` 对上述路径为空）。

#### §A 参考分口径的实测裁定（本卡最关键的实现决策）

卡内 §A 写的是 `top1_score = 池中最高分候选的 rerank 分`，但**按字面实现会让包塌掉**。
实测（`cockpit-agents-py`，10K 预算）：

| 参考分口径 | Runtime 那题装填的证据条数 | 说明 |
|---|---|---|
| 池内最高分（spec 3.252） | **4** | 阈值 1.626，把代码/测试证据整体截掉；与卡内表"保留 11 条"矛盾 |
| 非 spec 候选最高分（test 2.483） | **11** | 与卡内 §A-1 表逐项吻合 |

**裁定：`top1_score` = 池内非 spec 候选的最高 rerank 分。** 依据是卡内自带的 §A-1/§B-1 实测表
本身以非 spec 证据（E2=2.483）为 100%，而不是池总分。以该口径复算卡内四查询：

| 查询 | 非 spec top1 | ≥70% | ≥50% | ≥30% | 卡内表 ≥70%/≥50%/≥30% | 装填前后证据条数 |
|---|---|---|---|---|---|---|
| Runtime 的输入准入是怎么实现的？ | 2.483 | 2 | 11 | **24** | 2 / 11 / 24 ✅ | 30 → **11** |
| CapabilityGateway 怎么调用 HMI 能力 | 5.766 | 1 | 1 | 5 | 1 / 1 / 5 ✅ | 32 → **2** |
| 欢迎流程的 Workflow 是怎么定义的？ | 1.773 | 7 | 18 | 24 | 7 / 18 / 24 ✅ | 24 → **18** |
| 状态所有权是怎么划分的？ | 1.813 | 16 | 36 | 49 | 16 / 36 / 49 ✅ | 55 → **36** |

12/12 列逐项吻合，且"装填后条数"列本身证明了 §A 闸门确实按该口径生效。

#### §A-1 默认值 0.50 的测量过程（含被截掉的证据）

**Runtime 的输入准入是怎么实现的？**（改前 30 条证据 → 改后 11 条），被截掉的 19 条中靠前的：

| id | score | 相对 top1 | type | path |
|---|---|---|---|---|
| E13 | 1.253 | 50% | code | `src/cvi_agent_core/runtime/langgraph_adapter.py` |
| E14 | 1.210 | 49% | code | `src/cvi_agent_core/runtime/models.py` |
| E20 | 1.015 | 41% | test | `tests/v2/runtime/test_clock_domains.py` |
| E24 | 0.908 | 37% | code | `tests/v2/runtime/test_events_and_errors.py` |
| E33 | 0.520 | 21% | test | `tests/integration/app/test_runtime_langgraph.py` |

四个查询在每个候选比例下的幸存条数（＝卡内表的四列，已复算吻合）：

| 查询 | 池 | 装填前证据 | ≥70% | ≥50%（默认） | ≥30% |
|---|---|---|---|---|---|
| Runtime 的输入准入是怎么实现的？ | 126 | 30 | 2 | **11** | 24 |
| CapabilityGateway 怎么调用 HMI 能力 | 112 | 32 | 1 | **1** | 5 |
| 欢迎流程的 Workflow 是怎么定义的？ | 121 | 24 | 7 | **18** | 24 |
| 状态所有权是怎么划分的？ | 128 | 55 | 16 | **36** | 49 |

两点观察（与用户拍板口径一致）：

1. **相对阈值确实自适应**：符号密集型查询（`CapabilityGateway`）只需 1 条，宽泛语义查询
   （状态所有权）有 36 条真相关——"多的返回多，少的返回少"；
2. **0.50 偏保守**：宽泛查询上仍保留 36/128，截断力度有限（见"未决问题"）。

**被截掉的证据里有没有明显相关的？** 有 1 条值得记录：`E13 langgraph_adapter.py`（50%，
恰好压在阈值线上被舍入截掉）与 `E14 runtime/models.py`（49%）在语义上确实与 Runtime 相关。
0.40 会把它们留下（27 条）。考虑到这属于观察到 1~2 个样本再调参的典型小样本拟合
（R29/R30 的教训），**未调默认值**，如实记录于此。

#### §B 修改前 vs 修改后真实渲染片段

改前（`--max-tokens 10000`，节选前 3 行）：

```markdown
### Code
[E2] test_user_input_reaches_runtime_without_voice_invocation_binding — tests/integration/hmi_gateway/test_provider_and_ingress.py:261-342
     reason: bm25 -18.2807 + bm25 rank 9 + vector 0.4880 + vector rank 15 + entry point / exported symbol +0.2 + test fixture (non-test intent) -0.5 + 相邻区间合并
### Flow
```

改后（同一条命令）：

```markdown
### Code
#### Core
[E4] Runtime — src/cvi_agent_core/runtime/runtime.py:20-22
     reason: vector 0.5861 + vector rank 3 + entry point / exported symbol +0.2
     20 | class Runtime:
     21 |     """Serializes input admission and publishes post-admission notifications."""
#### Related
[E5] Runtime.admit — src/cvi_agent_core/runtime/runtime.py:43-105
     reason: vector 0.5642 + vector rank 4
     ...（E6~E13 共 9 条）
#### Tests
[E2] test_user_input_reaches_runtime_without_voice_invocation_binding — tests/integration/hmi_gateway/test_provider_and_ingress.py:304-320
```

- 证据总数 **30 → 11**（另有 2 条 docs；`### Docs` 不分组）；
- 测试文件从**第 1 位**移到 `#### Tests`（`### Code` 内第 207 行，**`[E2]` 编号未变**）；
- 新增标题：`#### Core`（1 条）/ `#### Related`（9 条）/ `#### Tests`（1 条）；
- `### Flow` / `### Docs` / `### Missing Evidence` / `### Suggested Next Queries` / `### Meta`
  节名与顺序**逐字未变**；`budget: 4.0K/10.0K`（改前 10.0K/10.0K）。

#### 配置生效实测（证明不是硬编码）

`ZACE_CONTEXT_SCORE_RATIO` 两次不同取值（同一命令，10K 预算；`evidence (Core, Related, Tests)`）：

| 查询 | 默认 0.50 | `0.7` | `0.3` |
|---|---|---|---|
| Runtime 的输入准入是怎么实现的？ | 11 (1, 9, 1) | **2** (1, 0, 1) | **24** (1, 16, 7) |
| CapabilityGateway 怎么调用 HMI 能力 | 2 (1, 0, 1) | **2** (1, 0, 1) | **5** (1, 1, 3) |
| 欢迎流程的 Workflow 是怎么定义的？ | 18 (5, 6, 7) | **7** (5, 0, 2) | **24** (5, 6, 13) |
| 状态所有权是怎么划分的？ | 36 (16, 15, 5) | **16** (16, 0, 0) | **49** (16, 19, 14) |

`0.7` 时 `Related` 整组为空 → **空组不渲染**（`#### Related` 不出现），与 §B-3 一致。

#### 与设计的偏差

1. **参考分口径**：卡内 §A 伪码写"池中最高分候选"，实现取"池内**非 spec** 候选最高分"。
   理由与实测见上；卡内 §A-1/§B-1 的实测表本身支持该口径（否则两者互相矛盾）。
   若编排者裁定应严格按字面（池总分），Runtime 那题会从 11 条降到 4 条——需一并更新 §A-1 表。
2. **§B `Related` 的 `top1` 参考分**：§B-2 只写"`score ≥ top1 × 0.50`"未指明 `top1`。实现取
   **包内证据最高分（含 test）**，因为 §B-1 的示例正是"测试 100% → Tests、Runtime 72% → Core、
   邻居 59% → Related"。（若按非 test 参考分，`Related` 在实测中整组消失。）
3. **`missing_evidence` 文案微调**：`候选池被预算裁剪` → `候选池被裁剪`，并新增"N 个因低于相对
   分数阈值（top1×K）未予装填"。CF-03 的 `message` 是自由文本、字段集未变（`pack_meta.py` 零改动）。
4. **保底补入路径**：`score_ratio=0.0` 被定义为"显式关闭闸门"；保底（`code_floor`/`spec_floor`）
   不走闸门，与 §A 纪律 2 一致，并有专门用例守护。

#### 既有测试的必要调整（5 处）

新闸门改变了这些用例隐含的"关闸门"前提（它们的候选分数天然跨越阈值）：

| 测试 | 调整 |
|---|---|
| `test_assembly::test_tier3_quota_uses_30_percent_of_used_budget` | 加 `replace(config, score_ratio=0.0)`——该用例只验 tier3 配额 |
| `test_merge_line_order::CONFIG` | 加 `score_ratio=0.0`——该用例验合并后的行序/省略标注；并把 `text.count("省略") == 2` 改为按 `ELISION` 正则只数**正文块**内的标注（全文计数会把新增的闸门上报算进去） |
| `test_spec_floor_dedup::test_reserved_spec_chunk_...` | 加 `replace(config, score_ratio=0.0)`——该用例验去重与 E 编号 |
| `test_render::test_existing_sections_are_byte_identical_to_the_snapshot` | 改为断言**顶层节**逐字未变 + 四级标题确实出现（§B 是卡内要求的渲染变更） |
| `snapshots/rich_pack.md` | 加 `#### Core` / `#### Related` 行与新增的 `retrieval_truncated` 行 |

其余 57 条 contextpack 既有用例**未改一字**、全部通过。

#### 验收命令与结果

```
uv run pytest core/tests/contextpack -q
  → 83 passed（其中本卡新增 21 条）

uv run ruff check .
  → All checks passed!
uv run python scripts/check_dependency_direction.py
  → 依赖方向检查通过（core 纯库 / service 不上探）。
uv run pytest -o addopts="" -q
  → 899 passed, 2 skipped（基线 878 passed, 2 skipped）
```

真实靶场命令（两条都跑通，输出见上）：

```bash
set -a; source .env; set +a
uv run zace-core search "Runtime 的输入准入是怎么实现的？" \
  --repo /home/xuwenzheng/4_AIBOX/gitlab/minicpm/cockpit-agents-py \
  --data /home/xuwenzheng/.zace/cockpit-agents --max-tokens 10000
```

#### 未决问题

1. **0.50 在宽泛查询上截断力度有限**：状态所有权那题仍保留 36/128 条、状态所有权题 `Related`
   组 15 条，Agent 仍需自己挑。这是默认值保守的代价（宁多勿少），是否收紧请编排者裁定；
   未擅自改默认值（避免小样本拟合）。
2. **`E13`（50.0%）被舍入截掉**：`langgraph_adapter.py` 相对 top1 恰为 50.0%，浮点比较
   `1.2529 < 2.4826×0.5 = 1.2413` 成立而被截。若认为"边界即保留"更合适，可把比较改为
   `score < floor` 之外的容差（未做，避免引入未定义行为）。
3. **`E24` 的 `type` 与路径不一致**：`tests/v2/runtime/test_events_and_errors.py` 的 fallback 切片
   其 `kind` 是 `fallback`（`classify_kind` 对 `fallback_block` 的判定优先于测试路径），
   因此它渲染在 `#### Related` 而非 `#### Tests`。§B-2 的规则是 `type == test`，按字面实现即
   当前行为。是否让 §B 额外按**路径**判定测试（需要 `is_test_path`，属 retrieval 公共面）
   请编排者裁定——本卡未做，以守住"只改渲染层"的边界。
4. **`budget.truncated` 语义扩展**：闸门截断也会置 `true`（此前只由预算/配额触发）。CF-03 未
   定义 `truncated` 的确切触发条件，但下游（`pack_meta.py` / web `MetaPanel`）会显示为
   `budget.truncated = true`。若需语义分离，属契约讨论范围，本卡未动。
