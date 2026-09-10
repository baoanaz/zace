# TASK-019：spec 保底块重复装填修复（U2）+ 预算不变量测试

> 状态：review ｜ 阶段：Phase 1（W3c）｜ 硬依赖：TASK-017（已合并）｜ soft 依赖：无
> 建议分支：`feature/task-019_<你的缩写><MMDD>`（从最新 main）
> 交付物所有权：`core/zace_core/contextpack/assembly.py`、`core/tests/contextpack/`
> 其它文件不得改动（尤其 `core/zace_core/parsing/`、`chunking/`、`pipeline/`，那是 TASK-018 的范围）。

## 背景（TASK-013 自举时发现并给出复现路径，编排者已核对代码）

`assemble` 的 spec 保底机制会把**同一个 spec 候选装填两次**：

```python
# assembly.py 现状
reserved: _Slot | None = None
if active.spec_floor > 0:
    for candidate in pool:
        if candidate.kind != "spec": continue
        ...
        reserved = slot          # ① 预留：为最高分 spec 候选造了一个 _Slot 对象
        break
...
for candidate in pool:            # ② 贪心循环会再次遍历到同一 candidate
    ...
    _place(candidate, slot, tokens)   # 造成另一个 _Slot 对象并装填
...
if reserved is not None and reserved not in slots and used + reserved.tokens <= active.hard_cap:
    _place(reserved.candidate, reserved, reserved.tokens)   # ③ 该判断在 slot 被改动后失效
```

**根因校正（本卡实测，见"执行记录"）**：`_Slot` 是**非 frozen** dataclass，Python 会生成 `__eq__`
（**值**比较），因此③的"是否已装填"判断只在"贪心路径装下的 slot 未被改动"时才生效；一旦贪心
路径把后来的相邻块**并入**该 slot（`_try_merge`）或对它做 `_degrade`，值不再相等 → 判断翻成真
→ 同一 chunk 的原始 span 被再装一次。

**实测后果**（TASK-013 在真实仓库 5 条查询中 2 条命中）：同一 spec chunk 同时为 `E1(173-232)` 与
`E28(175-197)`（本卡复现时为 `E30(175-197)`，随候选集不同），重复块吃掉约 1.4K token，
且预算已满（10.0K/10.0K）——直接挤压真正相关的代码证据，
并把 ContextPack 的 `omittedCount` 变得不可解释。

## 修复要求

- 装填去重改为**按 chunk_id 判定**（例如维护 `placed_ids: set[str]`，供 `_place` 与保底分支共用），
  而不是靠 `_Slot` **值**比较；
- 保底语义保持：spec 保底仍要"预留预算 + 存在相关 spec 时至少装 1-2 块"（Module/03 §4.1）；
  已被贪心循环装填过的同一 chunk 不得再装一次；
- `E` 编号顺序仍等于装填顺序（D-21，不得改变）；
- 若同一 spec 候选确实被贪心循环装填，预留预算应归还（不得因预留而少装其它候选）——即
  最终 `used` 与"无预留情况下的装填结果"一致（在无重复的前提下）。

## 验收标准（DoD）

- [x] 新增测试（`core/tests/contextpack/`）：
  1. **去重**：构造"最高分 spec 候选同时也是贪心首个候选"的场景 → 断言该 chunk_id 在
     `evidence + docs` 中只出现一次，且两个 E 编号的重复不再发生；
  2. **预算不变量**：`budget.usedTokens ≤ budget.hardCap`；`usedTokens` 等于各项证据 token 之和
     （可用 `estimate_tokens` 复核）；
  3. **保底仍在**：构造"spec 候选分数很低、代码候选分数很高且足以占满预算"的场景 →
     断言仍至少装填 1 块 spec（保底语义未被本次修复破坏）；
  4. **回归**：既有 contextpack 用例（含 TASK-017 的行序测试与快照）全绿。
- [x] 全仓 `uv run pytest` 全绿；`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py` 通过
- [x] 修复前后对比（贴进执行记录）：复用 TASK-013 的复现仓库/查询，展示该查询的 E 编号清单
      修复前（含重复）与修复后（无重复 + usedTokens 变化）
- [x] 任务卡"执行记录"回填 + 任务板状态改 review

## 参考

- TASK-013 执行记录 U2（发现者）
- `docs/design/Module/03-上下文组装.md` §4.1（装填主流程与 spec 保底）、§4.2（预算裁决）

## 明确不做

- 不改预算默认值、单文件上限、tier3 配额（这些是 TASK-015 校准项）；
- 不改去重三招中的另两招（相邻区间合并归 TASK-017 已修、同符号聚合不动）；
- 不改 `render.py` 格式。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

日期：2026-09-10 ｜ 分支：`feature/task-019_xwz0910` ｜ 状态：待评审（review）

### 根因校正（与卡内描述的差异，重要）

卡内写的"`_Slot` 无 `__eq__`（身份比较）→ `reserved not in slots` 恒为 True"**不准确**：`_Slot` 是
**非 frozen** dataclass，Python 会生成 `__eq__`（**值**比较）。实测（把测试跑在修复前的代码上）：

- "最高分 spec 候选同时也是贪心首个候选、且 slot 未被改动"的朴素场景**不会**重复：
  预留块与贪心装下的块逐字段相等 → `reserved in slots` 为 True；
- 真实重复的触发条件是：贪心路径装下该候选后，**该 slot 被就地改动**——去重第 1 招的
  `_try_merge`（后到的相邻块并入它，segments/elision 变化）或 `_degrade`（skeleton 降级）——
  值不再相等 → 判定翻转为 True → 保底分支把**同一 chunk 的原始 span** 再装一次。

这正是真实复现的形状（`E1(173-232)` 合并块 + `E30(175-197)` 预留原始 span），也解释了为何
TASK-013 的自举能命中而这之前的单层测试命中不了。裁定 R15 的**修复方向**（按 chunk_id 去重、
保底语义与 E 编号=装填顺序不变）与本卡实现一致，故不阻塞；仅根因表述需澄清。

### 实现（交付物：`core/zace_core/contextpack/assembly.py`、`core/tests/contextpack/`）

1. 新增 `placed_ids: set[str]`（**按 chunk_id** 判重），由 `_place`、贪心循环 merge 路径、保底分支三处共用；
2. 贪心循环入口跳过 `candidate.chunk_id in placed_ids` 的候选（同一 chunk 只装一次）；
3. 合并路径 `_try_merge` 命中时同样登记 `placed_ids`（已并入既有块 → 不再单独装填）；
4. 末尾保底补入的条件由 `reserved not in slots` 改为 `reserved.candidate.chunk_id not in placed_ids`；
5. **预留预算归还**：预留期间硬顶 = `hardCap − reserve`（原实现为循环外一次性计算）；改为每轮按
   "预留块是否仍在等待装填"动态求值 `_hard_limit()`，预留块一旦被装填（含并入既有块）即恢复完整
   `hardCap`——不再因预留而少装其它候选。

未改：`BudgetConfig` 默认值、单文件上限、tier3 配额、`render.py`、去重另两招（同符号聚合、
相邻区间合并语义）；E 编号规则不变（仍 `E1..En` = 装填顺序，evidence 与 docs 共用编号空间）。

### 验收命令与结果

```text
$ uv run pytest core/tests/contextpack -q
48 passed

$ uv run pytest            # 全仓基线
477 passed, 2 skipped in 17.29s

$ uv run ruff check .
All checks passed!

$ uv run python scripts/check_dependency_direction.py
依赖方向检查通过（core 纯库 / service 不上探）。
```

新增测试 `core/tests/contextpack/test_spec_floor_dedup.py`（5 条，覆盖 DoD 四项）：

| # | 测试 | 覆盖 | 修复前 |
|---|---|---|---|
| 1 | `test_reserved_spec_chunk_merged_into_neighbor_is_not_placed_again` | 去重（**真实复现路径**：贪心装填预留块后被 `_try_merge` 扩段） | **FAIL**（`len(pack.docs) == 2`，used 608 vs 305） |
| 2 | `test_reserved_spec_chunk_is_placed_only_once_when_greedy_takes_it_first` | 朴素路径只装一次 + E 编号连续 | PASS |
| 3 | `test_used_tokens_equals_framework_overhead_plus_evidence_tokens` | 预算不变量 `used ≤ hardCap` 且 `used = overhead + Σ证据 token` | PASS |
| 4 | `test_spec_floor_still_places_a_spec_when_code_candidates_fill_budget` | **保底仍在**（防修过头） | PASS |
| 5 | `test_reserved_capacity_is_returned_once_the_spec_is_placed` | 预留预算归还（回归） | **FAIL**（`src/b.py` 被预留额度挤掉） |

（修复前结果由 `git stash` 暂存 `assembly.py` 后重跑同一文件得到；改回修复版后 48 passed。）

### 真实仓库修复前后对比

复现路径同 TASK-013 U2：`/tmp/zace-self-ingest`（本仓库同内容副本，无 `.git`/`uv.lock`），
数据根 `~/.zace-test`（project `6df6db722a2871c2`），查询
`BM25 多词召回为什么会恒零命中中文查询`，`--max-tokens` 默认 10000。

| | 修复前 | 修复后 |
|---|---|---|
| `budget` | `usedTokens 9991 / hardCap 10000`，`truncated true`，`omittedCount 9` | `usedTokens 9935 / hardCap 10000`，`truncated true`，`omittedCount 9` |
| 装填项数 | 30（evidence 9 + docs 21） | 31（evidence 10 + docs 21） |
| E29 | `docs/tasks/TASK-001-存储层.md` 8-12 | 同 |
| **E30** | **`docs/design/Background/06-core-engine-proposal.md` 175-197（spec）— 与 E1 重复** | `docs/tasks/TASK-002-Parser基座与Python.md` 36-46 |
| **E31** | — | `core/zace_core/retrieval/rerank.py` 359-365 |

- 修复前 E1 = `06-core-engine-proposal.md` 173-232（合并块）、E30 = 同一 chunk 的 175-197（保底预留
  原始 span）：**同一 chunk_id 占两个 E 编号**；重复正文 1053 字符（≈264 token）。
- 修复后该 chunk 仅保留 E1（合并块，保底语义仍满足：`docs` 仍有 21 项、E1 即该 spec）；释放的预算
  装入了两个新候选（E30 112 token + E31 96 token），净变化 −56 token，`omittedCount` 不变。
- 连跑 3 次结果逐字节一致（`E1..E31`、`usedTokens 9935`）。

> 注：TASK-013 记录里"重复块吃掉约 1.4K token"是当时那次 pack 的合计口径；本次同查询实测重复块
> 为 264 token（预留 span 175-197 本身很小，被合并进 E1 的部分不计二次）。数字差异不影响结论。

### 完成报告

- 卡号：TASK-019（R15 / U2）
- 分支：`feature/task-019_xwz0910`（本地提交，未 push）
- 验收：见上（48 passed / 477 passed, 2 skipped / ruff clean / 依赖方向通过）
- 关键产物：`core/zace_core/contextpack/assembly.py`、`core/tests/contextpack/test_spec_floor_dedup.py`
- 契约影响：**无**（未改 `docs/contracts/**`、`types.py`、`interfaces.py`）
- 与设计偏差：无（`placed_ids` 判重 + 预留归还均属 R15 裁定内的实现；未改预算默认值/配额/渲染）
- 未决问题：
  1. **任务卡根因描述需修订**（见上"根因校正"）："无 `__eq__` → 恒为 True"应改为"`_Slot` 值比较，
     贪心路径经 `_try_merge`/`_degrade` 改动该 slot 后值不再相等"。属文档表述问题，
     建议编排者在 R15 行或本卡"背景"节补一句澄清（本卡禁改设计文档，故只在执行记录登记）；
  2. 判重命中记入 `omittedCount` +1：语义上"池中候选未被展示"，但被跳过的其实是重复候选；
     真实查询的 `omittedCount` 未变（9）。若编排者希望"重复不计 omitted"，需明确口径（本次未改）；
  3. 自举环境注意：`~/.zace-test` 的向量通道在首次查询时可能 5s 超时降级（Exact+BM25），
     会改变候选集；本卡前后对比均在未降级的运行上完成（各跑 3 次确认可复现）。
- 建议复核点：
  1. `_hard_limit()` 动态求值的边界：预留候选被 `omitted` 时仍保留预留额度（行为与修复前一致）；
  2. 判重是否应有第二种口径（同一 chunk 在 evidence/docs 之间不得重复已由本修复覆盖）；
  3. 测试 1 的场景（merge 触发）是否可作为 TASK-014 之后的 `core/tests/integration/` 层用例补充。
