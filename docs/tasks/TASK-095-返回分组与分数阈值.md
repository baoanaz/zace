# TASK-095：返回结构分组与分数阈值截断（agent 视图优化）

> 状态：pending ｜ 阶段：Phase 3（M2c）｜ 硬依赖：无 ｜ soft 依赖：TASK-087（已合并）
> 建议分支：`feature/task-095-render-group_<你的缩写><MMDD>`
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

**默认值 0.50 的依据**（实测，非拟合）：在 `cockpit-agents-py` 的真实查询上，
0.50 保留 11/30 条（含全部 4 条核心实现），0.30 保留 24/30（几乎无截断效果），
0.60 保留 5/30（可能丢掉 `ExecutionCoordinator.admit` 这类真正的相关证据）。

> **重要**：该默认值的选定**必须记录实际测量过程**（用了哪些查询、各自保留多少条、
> 哪些证据被截掉了）。**不要**用 `benches/golden` 的 60 条 smoke 集去优化它（R29/R30 冻结）。

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

（实施 AI 在此填写。）
