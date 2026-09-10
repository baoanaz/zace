# TASK-016：BM25 多词召回语义修复（OR + 列权重）+ 跨模块 E2E 回归

> 状态：pending ｜ 阶段：Phase 1（W3 质量修复）｜ 硬依赖：无（TASK-001/010 已合并）｜ soft 依赖：无
> 建议分支：`feature/task-016_<你的缩写><MMDD>`（从最新 main）
> 交付物所有权：`core/zace_core/storage/store.py`（仅 fts_search 与其常量）、`core/zace_core/storage/schema.sql` 不改、
> `core/tests/storage/test_storage_fts.py`、`core/tests/storage/test_storage_incremental.py`（仅因语义变更需同步的用例）、
> `core/zace_core/retrieval/bm25.py`、`core/tests/retrieval/test_bm25*.py`、**新建** `core/tests/integration/`
> 其它文件不得改动（尤其 TASK-017 的 `contextpack/`）。

## 背景（编排者 E2E 实测发现，2026-09-10）

端到端冒烟（真实流水线 + 真实 e5 模型）暴露：**中文自然语言查询在 BM25 通道零命中**。

```text
query = "令牌过期后在哪里刷新"
segment(query) = "令牌 过期 后 在 哪里 刷新"        # 7 个 token
Store.fts_search(...) → []                          # 隐式 AND：要求 7 个 token 全在同一 chunk 出现
Store.fts_search(segment("令牌 刷新")) → 命中         # 2 个 token 才能命中
```

后果链条（真实存在，不是理论风险）：
1. BM25 通道对真实自然语言查询恒为空 → 只剩 Vector 单通道；
2. `assemble` 的 `answerable` 规则（Module/03 §4.4：需 Explicit 命中或双通道共识 ≥2）几乎恒为 False
   → ask_project（Phase 3）会走"证据不足"短路，search_context 的 confidence 恒为 low；
3. RRF 退化为单通道排序，D-16 的"多通道共识"设计目标失效。

**参考实现佐证**【已验证·快照 2025-09】：codegraph 的 FTS 查询构造用 **OR 连接 + 每词引号包裹**
（`source/codegraph/src/db/queries.ts:1505-1513`：`split(/\s+/).map(t => `"${t}"*`).join(' OR ')`），
並对列加权（`bm25(nodes_fts, 0, 20, 5, 1, 2)`，符号名列权重 20 倍）——这是 BM25 检索的标准做法。

## 修复要求

### A. `Store.fts_search`：新增操作符参数，默认 OR

```python
def fts_search(self, segmented_query: str, limit: int = 50, *,
               operator: Literal["or", "and"] = "or") -> list[tuple[str, float]]:
```
- `"or"`：token 用 `OR` 连接（每个 token 仍引号包裹，`"` 转义不变）→ 任一 token 命中即入候选，由 bm25 打分排序；
- `"and"`：保留现有语义（全 token 必须命中），供需要高精度的调用方显式选择；
- 分值仍返回**原始 bm25（负数，越小越相关）**并按它升序（TASK-001 既有约定不变）。

### B. BM25 列权重（提升符号命中排序质量）

- `chunks_fts` 三列：`content_seg, signature_seg, docstring_seg`（`file_path` 为 UNINDEXED，不参与权重）。
- 查询改为 `bm25(chunks_fts, W_CONTENT, W_SIGNATURE, W_DOCSTRING)`，权重定义为模块级常量元组
  `FTS_COLUMN_WEIGHTS = (1.0, 5.0, 1.0)`（content, signature, docstring），并加注释说明
  "TASK-015 校准项：与 TASK-015 bake-off 一并调，属通道内权重不是通道间权重（不违反 D-16）"。
- 依据：codegraph 用重名称权重保证符号名命中排在长 docstring 的偶然提及之前。

### C. 同步既有测试（语义变更的必然影响）

- `core/tests/storage/test_storage_fts.py`、`test_storage_incremental.py` 中依赖隐式 AND 的断言
  （例如断言命中数量恰好为 1）需按新语义调整：**用 `operator="and"` 保持原断言，或改为断言 top-1 命中**。
  每处修改在 PR/执行记录里说明理由；**不得为了过测试而弱化原有覆盖**（中文不分词不命中的关键断言必须保留）。
- 新增测试：同一语料下 `operator="or"` 对 7 token 中文查询非空、`operator="and"` 为空（正是本卡的回归锚点）。

### D. 跨模块 E2E 回归测试（本卡必须交付）

新建 `core/tests/integration/test_m1_pipeline.py`：用**真实** Store + VectorStore + Indexer + retrieval + contextpack
（不许 mock 掉被测链路），embedding 用**确定性假 provider**（CI 不联网、不加载模型；要求见下）。

假 provider 要求（写进测试文件，供后续复用）：基于字符/词 bigram 哈希到固定维度向量 + L2 归一化，
保证"共享中文词的 query 与 chunk 在向量空间也相近"，使 E2E 断言的失败只可能来自真实缺陷。

必须断言（每条对应一个真实缺陷场景）：
1. **BM25 回归**：中文 7-token 查询的 BM25 通道非空，且目标符号排在 top-3（本卡的核心回归）；
2. **双通道共识**：该查询至少 2 个候选带 ≥2 通道 → `ContextPack.answerable is True`、`confidence in {"medium","high"}`；
3. **Spec 在场**：Markdown 设计文档块出现在 `pack.docs` 中（D-13/D-42 的一等资产兑现）；
4. **删除级联**：删除文件后重新检索，其证据不再出现（含向量层不残留孤儿）；
5. **增量**：改一个函数 → `IngestReport.chunks_new == 1` 且 `chunks_reused >= 1`。

## 验收标准（DoD）

- [ ] `uv run pytest core/tests/integration core/tests/storage core/tests/retrieval -q` 全绿
- [ ] 全仓 `uv run pytest` 全绿（既有 427 用例不得回归；语义变更导致的调整须逐条说明）
- [ ] `uv run ruff check .`、`uv run python scripts/check_dependency_direction.py` 通过
- [ ] 修复前后对比（写进执行记录）：同一查询的 BM25 命中数 0 → N；`answerable` False → True
- [ ] 任务卡"执行记录"回填 + 任务板状态改 review

## 明确不做

- 不改 `schema.sql`/DDL、不改 chunk/解析/向量逻辑；
- 不引入停用词表或查询改写（保持"少规则"纪律，Module/02 R4）；前缀匹配（`"term"*`）**列为 TASK-015 校准项**，本卡不实现；
- 不改 `contextpack/`（TASK-017 范围）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写；执行记录必须含修复前后对比数据。

## 执行记录

（实施 AI 在此填写。）
