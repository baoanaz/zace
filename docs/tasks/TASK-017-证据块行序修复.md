# TASK-017：ContextPack 合并区间的行号单调性与 elided 计数修复

> 状态：pending ｜ 阶段：Phase 1（W3 质量修复）｜ 硬依赖：无（TASK-012 已合并）｜ soft 依赖：无
> 建议分支：`feature/task-017_<你的缩写><MMDD>`（从最新 main）
> 交付物所有权：`core/zace_core/contextpack/assembly.py`、`core/zace_core/contextpack/render.py`（如需）、
> `core/tests/contextpack/`（含快照）
> 其它文件不得改动（尤其 `storage/`、`retrieval/`——TASK-016 范围）。

## 背景（编排者 E2E 实测发现，2026-09-10）

端到端渲染出的证据块**行号非单调**，对消费它的 agent 是主动误导（Module/03 §6 明确要求
"代码带行号，agent 可直接对齐 Edit"）：

```text
[E2] TokenService.refresh — auth/token_service.py:1-16
     9 |     def refresh(self, token: str) -> str:      ← 9,10,11,12
    12 |         return rotated
     6 | class TokenService:                            ← 跳回 6
     7 |     """访问令牌的生命周期管理。"""
    14 |     def revoke(self, token: str) -> None:       ← 又跳到 14
    16 |         raise NotImplementedError
     1 | """Token 服务：负责访问令牌的签发与过期刷新。"""   ← 再跳回 1
     4 | from auth.store import TokenStore
     ... （省略 2 行）
```

根因（`assembly.py::_try_merge`）：合并按**候选分数顺序**进行，`existing.item.content = f"{existing.content}\n{slot.content}"`
直接拼接；`lines` 只更新为 `(min, max)`；`elided_lines += gap` 也是按合并发生顺序累加。
于是内容顺序 = 分数顺序，而行号区间是包围盒，两者不一致；`elidedLines` 也不等于"真实被省略的行数"。

## 修复要求

### A. 片段化存储 + 行序渲染

- `_Slot` 内部改存**片段列表**（每个片段 = `(start_line, end_line, content)`，content 为该区间原始文本），
  合并时按 `start_line` **保持有序插入**（不是简单 append）。
- 出口渲染时按片段行号升序拼接；相邻/重叠片段合并为一个片段（区间合并语义不变）。
- `item.lines = (首个片段 start, 末个片段 end)`；`item.content` = 各片段按行序拼接（片段之间保留省略标注）。
- `elidedLines` 重定义为**真实省略行数** = `(末行 - 首行 + 1) - Σ各片段行数`，与渲染出的"省略 N 行"标注一致。

### B. 保持既有语义不变
- 相邻区间合并阈值（`ADJACENT_GAP_LINES`，行距 ≤10）、单文件 25% 上限、tier3 30% 配额、spec 保底、
  E 编号 = 装填顺序、`reason` 追加 `+ 相邻区间合并` 等行为**全部保持不变**；本卡只修行序与计数。
- `to_json()`（CF-03 字段）与 `render_markdown` 的节顺序、格式不变；快照需按新行序更新。

## 验收标准（DoD）

- [ ] **顺带修一处 flaky**（实测）：`core/tests/contextpack/test_assembly.py` 的性能断言 `elapsed_ms < 50`
      在多泳道并发跑测试时会误报（编排者实测 3 泳道并发时失败 1 次）。处理方式：放宽到 200ms 或改为
      `@pytest.mark.slow` 单独跑；**不得删除该断言**（性能下限仍要有回归保护）。
- [ ] 新增测试（`core/tests/contextpack/`）：
  1. **行序**：构造三个候选（score 顺序与行序刻意相反，如同一文件 L40-50 / L5-12 / L20-28）→ 合并后
     `item.content` 中的行号（解析 `^\s*(\d+) \|` 提取）**严格递增**；
  2. **elided 计数**：上述场景 `elidedLines` == 真实省略行数（手工计算的期望值）；
  3. **原文保真**：每个片段内容与源 chunk 对应行的原文逐字一致（不被重新排序或截断污染）；
  4. **无合并场景回归**：单候选 → 行号与 elidedLines 语义不变。
- [ ] 既有 `core/tests/contextpack` 用例全绿（快照按新行序更新，并在执行记录里说明差异）
- [ ] 全仓 `uv run pytest` 全绿；`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py` 通过
- [ ] 修复后手工渲染一段证据贴进执行记录（证明行号单调、省略标注位置正确）
- [ ] 任务卡"执行记录"回填 + 任务板状态改 review

## 明确不做

- 不改检索/排序/预算算法；不改 CF-03 合同字段名；不引入新的渲染层（仍与服务端渲染同源，D-21）；
- 不改 `storage/`、`retrieval/`（TASK-016 范围）；不做跨文件合并。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

（实施 AI 在此填写。）
