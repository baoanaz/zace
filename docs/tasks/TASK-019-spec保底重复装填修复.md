# TASK-019：spec 保底块重复装填修复（U2）+ 预算不变量测试

> 状态：pending ｜ 阶段：Phase 1（W3c）｜ 硬依赖：TASK-017（已合并）｜ soft 依赖：无
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
    _place(reserved.candidate, reserved, reserved.tokens)   # ③ reserved not in slots 恒为 True
```

`_Slot` 无 `__eq__`（身份比较），所以 ③ 的"是否已装填"判断永远成立 → 同一 chunk 出现两个 E 编号。

**实测后果**（TASK-013 在真实仓库 5 条查询中 2 条命中）：同一 spec chunk 同时为 `E1(173-232)` 与
`E28(175-197)`，重复块吃掉约 1.4K token，且预算已满（10.0K/10.0K）——直接挤压真正相关的代码证据，
并把 ContextPack 的 `omittedCount` 变得不可解释。

## 修复要求

- 装填去重改为**按 chunk_id 判定**（例如维护 `placed_ids: set[str]`，供 `_place` 与保底分支共用），
  而不是比较 `_Slot` 对象身份；
- 保底语义保持：spec 保底仍要"预留预算 + 存在相关 spec 时至少装 1-2 块"（Module/03 §4.1）；
  已被贪心循环装填过的同一 chunk 不得再装一次；
- `E` 编号顺序仍等于装填顺序（D-21，不得改变）；
- 若同一 spec 候选确实被贪心循环装填，预留预算应归还（不得因预留而少装其它候选）——即
  最终 `used` 与"无预留情况下的装填结果"一致（在无重复的前提下）。

## 验收标准（DoD）

- [ ] 新增测试（`core/tests/contextpack/`）：
  1. **去重**：构造"最高分 spec 候选同时也是贪心首个候选"的场景 → 断言该 chunk_id 在
     `evidence + docs` 中只出现一次，且两个 E 编号的重复不再发生；
  2. **预算不变量**：`budget.usedTokens ≤ budget.hardCap`；`usedTokens` 等于各项证据 token 之和
     （可用 `estimate_tokens` 复核）；
  3. **保底仍在**：构造"spec 候选分数很低、代码候选分数很高且足以占满预算"的场景 →
     断言仍至少装填 1 块 spec（保底语义未被本次修复破坏）；
  4. **回归**：既有 contextpack 用例（含 TASK-017 的行序测试与快照）全绿。
- [ ] 全仓 `uv run pytest` 全绿；`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py` 通过
- [ ] 修复前后对比（贴进执行记录）：复用 TASK-013 的复现仓库/查询，展示该查询的 E 编号清单
      修复前（含重复）与修复后（无重复 + usedTokens 变化）
- [ ] 任务卡"执行记录"回填 + 任务板状态改 review

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

（实施 AI 在此填写。）
