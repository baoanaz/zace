# TASK-104：同符号定义块优先聚合

> 状态：review ｜ 阶段：Phase 5（质量）｜ 硬依赖：TASK-103 ｜ soft 依赖：TASK-091
> 分支：`feature/task-104-definition-preference_xwz0915`
> 交付物所有权：`core/zace_core/contextpack/assembly.py`、`core/tests/contextpack/test_assembly.py`

## 目标

修复 C/C++ 声明与定义拥有相同 `symbol_fqn` 时，ContextPack 同符号聚合只保留高分声明、丢弃真正函数体的问题。以 `leveldb::DBImpl::Get` 的 L-09 为回归锚点：定义已进入候选池，但 header 声明分数更高，导致实现正文未进入 pack。

## 输入与参考

1. `docs/design/Module/02-检索策略.md` §4.5、§4.6：RRF 与 Evidence Rerank 负责排序，tier 不得机械决定最终顺序。
2. `docs/design/Module/03-上下文组装.md` §3、§4：同符号聚合只保留一个代表，候选已排序后按预算装填。
3. `source/codegraph/src/graph/dead-code.ts`：区分 declaration container 与实际 symbol definition 的语义。
4. `source/ragcode/src/indexing/analyzers/tree-sitter-base.ts`：从 AST symbol 节点生成 chunk，保留节点对应的源码范围。
5. TASK-103 新索引 trace：`db/db_impl.h#DBImpl::Get` rank 2，`db/db_impl.cc#DBImpl::Get` rank 4；前者被聚合保留，后者未进入 pack。

## 实施边界

- 不修改 `docs/design/**`、`docs/contracts/**`、`core/zace_core/types.py`、`interfaces.py`。
- 不修改 RRF 公式、通道配额、既有 rerank 权重、相对分数闸门或 parser。
- 仅在 ContextPack 的同符号聚合前选择代表：C/C++ 的函数/方法 chunk 若存在函数体定义，优先于同 FQN 的声明；没有定义时保持原有分数优先行为。
- 保留聚合可解释性与 `omitted_count` 统计；不为 L-09 增加路径或符号特例。

## 验收标准

- [x] C/C++ 同 FQN 的低分定义优先于高分声明进入 pack。
- [x] 同 FQN 没有函数体定义时仍按原有分数选择代表。
- [x] `omitted_count` 与“同符号聚合”原因保持正确。
- [x] leveldb L-09 的 `db/db_impl.cc#DBImpl::Get` 进入 pack；search MRR 不低于 TASK-103 新索引结果。
- [x] HelloAgents/langchain 指标无回归。
- [x] `uv run pytest core/tests/contextpack/test_assembly.py core/tests/retrieval/test_rerank.py -q`、ruff、依赖方向、全仓 pytest 全绿。

## 执行记录

### 2026-09-15 实施与验收

- 实现：在 ContextPack 同符号聚合前批量读取 chunk 元数据；同 FQN 的 C/C++ `function`/`method` 候选若存在函数体（源码片段同时含 `{` 与 `}`），优先保留定义；无定义时保持原有分数优先。定义替换仍计入 `omitted_count`，并在 reason 写入 `同符号聚合×N`。
- 参考核对：`source/codegraph/src/graph/dead-code.ts` 区分 declaration container 与 definition 语义；`source/ragcode/src/indexing/analyzers/tree-sitter-base.ts` 从 AST symbol 节点保留对应源码范围。未复制参考实现。

| 验收命令/探针 | 结果 |
|---|---|
| `uv run pytest core/tests/contextpack/test_assembly.py core/tests/retrieval/test_rerank.py -q` | 70 passed |
| `uv run ruff check .` | All checks passed |
| `uv run python scripts/check_dependency_direction.py` | 依赖方向检查通过 |
| `uv run pytest -o addopts=\"\" -q` | 1027 passed, 2 skipped |
| leveldb L-09 trace | `db/db_impl.cc#DBImpl::Get` 为 pack E1；声明不再覆盖定义 |

| 靶场指标 | TASK-103 新索引 | TASK-104 |
|---|---:|---:|
| leveldb search R@5 / R@10 | 0.684 / 0.684 | 0.737 / 0.737 |
| leveldb search MRR | 0.492 | 0.545 |
| leveldb 负例 | 1/1 | 1/1 |
| leveldb ask pack any / complete | 4/5 / 3/5 | 5/5 / 4/5 |
| HelloAgents search R@5 / R@10 / MRR | 0.842 / 0.895 / 0.744 | 完全一致 |
| HelloAgents ask pack any / complete | 5/6 / 3/6 | 完全一致 |
| langchain search R@5 / R@10 / MRR | 0.789 / 0.789 / 0.711 | 完全一致 |
| langchain ask pack any / complete | 5/5 / 4/5 | 完全一致 |

本卡没有修改 RRF、通道配额、rerank 权重、相对分数闸门、parser 或冻结契约。

### 未决问题

无。定义优先策略在 leveldb、HelloAgents、langchain 三个真实索引上验证，无需扩大到 rerank 权重调参。
