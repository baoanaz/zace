# TASK-011：图扩展（calls + spec_references）+ 确定性 rerank

> 状态：pending ｜ 阶段：Phase 1 ｜ 硬依赖：TASK-010 ｜ soft 依赖：无
> 建议分支：`feature/task-011_<你的缩写><MMDD>`
> 交付物所有权：`core/zace_core/retrieval/expand.py`、`core/zace_core/retrieval/rerank.py`、`core/tests/retrieval/test_expand.py`、`test_rerank.py`
> （`exact.py`/`bm25.py`/`vector.py`/`rrf.py`/`fusion.py` 与 `retrieval/__init__.py` 归 TASK-010，不得改；需要导出时由调用方直接 import 子模块）

## 目标

在 RRF 候选池之上交付两件事：图扩展（图的第一角色：扩展器，D-18-a）与
确定性 Evidence Rerank（D-16：V1 内置、无模型、零延迟）。两者共同决定最终排序分。

## 输入文档（按序读）

1. `docs/design/Module/02-检索策略.md` §4.4-a（扩展与防爆炸）、§4.5（rerank 特征表，**逐项落地**）、§4.6（tier 语义）
2. `docs/design/Module/01-切片存储.md` §2.2-③（spec_references 双向桥）
3. `core/zace_core/types.py`（`Candidate`：`graph_depth` / `channel_ranks` / `tier` / `reasons`）

## 交付内容

### A. 图扩展（`expand.py`）

```text
seeds = 候选池 top 20（按 score）
每 seed 取 symbol：
  ├─ calls 边 1-hop（callers + callees 双向）→ 目标 chunk 入池，tier=3，graph_depth=1
  └─ spec_references 双向：
       代码 seed → 引用它的 SpecBlock（设计意图）
       spec seed → 它提到的代码符号（实现位置）
防爆炸（硬性）：扩展总量 ≤ 30 块；单符号 callers > 200 时按入口点评分截断 top 20
入口点 = 无内部调用者且 is_exported（用 Store 的 edges/symbols 信号）
合成边（provenance='synthesized'）扩展来的候选 → reasons 记录（供 rerank −0.2）
```

### B. 确定性 rerank（`rerank.py`，Module/02 §4.5 特征表逐项实现）

| 特征 | 分值 |
|---|---|
| Explicit symbol/path 命中 | +2.0 |
| query 符号名与 chunk 符号名等值 | +1.0 |
| 3 通道共识 | +0.5 |
| 与 top-1 种子图连通（1 跳） | +0.5 |
| doctype ∈ {agent-instructions, design, adr, readme, api} | +0.8 |
| 入口点 / 被导出符号 | +0.2 |
| generated 文件 | −1.0 |
| test fixture（非测试意图查询） | −0.5 |
| stale spec 引用 | −0.8 |
| fallback_block | −0.5 |
| 图距离 2 跳 | −0.3 |
| synthesized 边扩展 | −0.2 |

- 超参数集中在 `RerankWeights` dataclass（字段与上表一一对应），默认值为上表；
  **TASK-015 校准只改默认值，不改特征结构**。
- 基准分 = RRF 分；输出写回 `Candidate.score` 并降序返回；`reasons` 记录命中特征（可解释性，进 ContextPack）。
- "测试意图查询"判定：V1 用确定性规则（query 含 test/测试/pytest 等词，或路由为 General 且查询符号命中 tests/ 路径）——口径写入卡内记录。

### C. 调用链 flows 最小版（供 ContextPack flows[] 字段）

- 对 top 3 种子，沿 callees 方向做 ≤3 节点链（无环、按行号稳定），编号 F1..Fn；深度截断时 `truncated=true`；
- 不存在的路径宁缺勿编：无法构成 ≥2 节点链的种子不产出 flow。

## 验收标准（DoD）

- [ ] `uv run pytest core/tests/retrieval/test_expand.py core/tests/retrieval/test_rerank.py -q` 全绿，必须覆盖：
  - 扩展配额：>30 块时被截断；caller 爆炸（构造 300 callers 符号）→ 截断 top 20 且入口点优先；
  - spec_references 双向：代码 seed 拉出 spec 块、spec seed 拉出代码符号（构造双向 fixture）；
  - rerank 特征逐项：12 条特征各至少 1 个正/负例断言（可参数化）；
  - 排序可解释：`reasons` 包含对应特征文本；
  - 组合回归：Explicit 命中弱相关模块 vs 三通道共识的强相关符号 → 共识者胜（Module/02 §4.6 反例场景）；
  - flows：构造 A→B→C 调用链 → F1 节点顺序/行号正确；链上出现环或超深 → `truncated` 且不炸。
- [ ] 基线三条命令全绿。

## 参考源码锚点（只读）

- `source/GitNexus/gitnexus/src`（entry-point scoring 截断；见 Background/04 §5）
- `source/codegraph/src/graph/`（named-symbol-flow / 遍历；见 Background/02 §5）
- `source/ragcode/src/rerank/`（确定性特征与 circuit breaker 回退模式）

## 明确不做

- 不做结构型查询的主路径（Phase 3 路由分支）；不做 2-hop 常规扩展（仅 G1 二轮用，Phase 3）；
- 不接 cross-encoder / LLM reranker（V1.5，接口留白即可）；不改通道与 RRF（TASK-010 范围）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

（实施 AI 在此填写。"测试意图查询"的最终判定规则、caller 截断排序的最终实现必须记录。）
