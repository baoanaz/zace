# TASK-016：BM25 多词召回语义修复（OR + 列权重）+ 跨模块 E2E 回归

> 状态：done ｜ 阶段：Phase 1（W3 质量修复）｜ 硬依赖：无（TASK-001/010 已合并）｜ soft 依赖：无
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

### 2026-09-10 ｜ 分支 `feature/task-016_xwz0910` ｜ 状态：review（待编排者评审）

#### 1. 交付物

| 文件 | 变更 |
|---|---|
| `core/zace_core/storage/store.py` | §A `fts_search(segmented_query, limit=50, *, operator="or")`；§B 模块常量 `FTS_COLUMN_WEIGHTS=(1.0, 5.0, 1.0)` + `bm25(chunks_fts, w_content, w_signature, w_docstring)` |
| `core/zace_core/retrieval/bm25.py` | 仅 docstring 同步 OR 语义（实现走默认 `operator="or"`，未改行为） |
| `core/tests/storage/test_storage_fts.py` | 新增 4 例：多 token OR/AND 双语义回归锚点、`operator="and"` 精度保留、非法 operator 拒绝、签名列权重排序 |
| `core/tests/storage/test_storage_incremental.py` | 1 处断言改 `operator="and"`（见 §3 逐条说明） |
| `core/tests/retrieval/test_recall.py` | 1 处断言按新语义**扩充**（见 §3；**超出卡内文件清单，申请追认**） |
| `core/tests/integration/`（新建） | `__init__.py`、`conftest.py`（确定性假 provider + M1 环境夹具）、`test_m1_pipeline.py`（§D 五条断言） |

未改：`schema.sql`/DDL、chunk/解析/向量逻辑、`contextpack/`（TASK-017 范围）、契约与设计文档。

#### 2. 修复前后对比（同语料、同查询）

语料 = `core/tests/integration/conftest.py`（真实解析/切块链路产出 6 个 chunk：2 个 Markdown spec 块 + 4 个 Python 块）；
查询 = `令牌过期后在哪里刷新` → 分词后 **6 token**（`令牌 过期 后 在 哪里 刷新`）；无任何单块同时含全部 6 个 token。

| 指标 | 修复前（FTS5 隐式 AND） | 修复后（默认 OR） |
|---|---|---|
| BM25 通道命中数 | **0** | **6** |
| 进入候选池的通道 | vector 单通道 | bm25 + vector |
| 带 ≥2 通道的候选数（consensus） | 0 | 6 |
| 目标符号 `TokenService.refresh_token` 的 BM25 排名 | 未入池 | 2（top-3 达标） |
| `ContextPack.answerable` | **False** | **True** |
| `ContextPack.confidence` | low | medium |
| `pack.docs`（设计文档块） | 2（仅靠 vector 偶然命中） | 2（双通道命中，spec 保底生效） |

补充数据（同一环境）：增量重索引 `chunks_new=1 / chunks_reused=3 / vectors_upserted=1`；
删除 `src/token_service.py` 后 `orphan_files=()`、`VectorStore.count()==Store.counts()['chunks']==2`（无孤儿向量）。
修复前的数值由测试内的反事实路径复现（`M1Env.vector_only_pack`：只喂向量单通道候选 → `answerable is False`），
作为回归护栏留在 `test_two_channel_consensus_makes_pack_answerable` 内，防止未来又退化回单通道。

#### 3. 语义变更导致的既有断言调整（逐条）

1. `core/tests/storage/test_storage_incremental.py::test_reapply_same_change_is_idempotent`
   —— 原 `len(fts_search(segment("return 2"), 10)) == 1` 断言的是"FTS 行不重复累积"。
   OR 语义下两个 chunk 都含 token `return`（共 4 个 token 命中），计数无法再区分"累积"与"多命中"，
   故显式改 `operator="and"` **保持原断言强度与意图**（未弱化）。
2. `core/tests/retrieval/test_recall.py::test_recall_merges_three_channels`
   —— `cache.channel_ranks == {inferred: 1}` → `{inferred: 1, bm25: 2}`。
   查询 `TokenService.refresh refreshToken` 只含 `refreshToken` 的块现在合法进入 BM25 候选（这正是 OR 的目标），
   旧断言编码的是隐式 AND 语义。属**扩充**（新值更严格地锁定了通道构成），未删除任何原有断言。
   **该文件不在卡内交付物清单**，但 DoD 要求"全仓 pytest 全绿 + 语义变更调整逐条说明"，故做最小同步；
   提请编排者追认（或指示改用其它处理方式）。
3. `core/tests/storage/test_storage_fts.py` 中所有"中文不分词不命中"关键覆盖**原样保留**
   （`test_chinese_query_hits_only_after_segmentation` 仍断言 `fts_search("刷新令牌") == []`），未弱化。

#### 4. 验收命令与结果

| 命令 | 结果 |
|---|---|
| `uv run pytest core/tests/integration core/tests/storage core/tests/retrieval -q` | **155 passed** |
| `uv run pytest`（全仓） | **436 passed, 2 skipped**（427 个既有用例无回归；新增 9 例 = 4 storage + 5 integration） |
| `uv run ruff check .` | All checks passed |
| `uv run python scripts/check_dependency_direction.py` | 依赖方向检查通过（core 纯库 / service 不上探） |

#### 5. 契约影响

无。`Store.fts_search` 不在 CF 冻结清单内（`Store` 非契约文件）；
`operator` 为**带默认值的关键字参数**，既有调用方零改动；返回值语义（`(chunk_id, 原始 bm25 分)` 升序）不变。
列权重是通道内权重，不触碰 D-16（融合层不加通道权重）与 RRF 的 K=60。

#### 6. 与设计偏差

无。实现方向严格按 §A/§B/§C/§D 与 R11 执行（OR + 引号包裹 + 列权重 `(1.0, 5.0, 1.0)`）；
前缀匹配 `"term"*`、停用词表、查询改写均未实现（按卡内"明确不做"与 TASK-015 校准项处理）。

#### 7. 未决问题

1. **`core/tests/retrieval/test_recall.py` 的越界修改待追认**（见 §3-2）：文件不在交付物清单，但为满足 DoD 全绿所必需。
   若编排者要求回退，则该用例必红——需要先更新任务板/卡片所有权再改。
2. **OR 语义下的噪声 token 放大**（建议列入 TASK-015 校准项）：jieba 会把标点/`：`/`"` 等切成独立 token，
   OR 连接后这些 token 会"无差别"扩大候选（正文里到处都是）。当前只对 `bm25_query_text` 已覆盖的
   `` ` `` 与 ``:: `` 做了归一化；标点与停用词过滤、前缀匹配、列权重细调都留待 TASK-015 bake-off 决定。
   本卡按"少规则"纪律未自行引入停用词表。
3. `FTS_COLUMN_WEIGHTS` 取值 `(1.0, 5.0, 1.0)` 来自 R11 裁定与 codegraph 参考实现，未做数据校准；
   已加注释标注为 TASK-015 校准项。
4. **任务板缺行（供编排者补）**：`docs/tasks/README.md` 的 Phase 1 表中原本没有 TASK-016 / TASK-017 行
   （只在批次历史里提到）。本卡按指令补了 TASK-016 一行（状态 review）；**TASK-017（lane C）的行仍未补**，
   不属本卡范围，请编排者补上。

#### 8. 给编排者的建议复核点

1. `core/tests/integration/test_m1_pipeline.py` 的 5 条断言是否覆盖了 R11/R13 的全部真实缺陷场景（尤其反事实护栏）；
2. 假 provider 的确定性 bigram 设计与"CI 不联网"要求是否满足，是否值得抽成 TASK-013/014 共用夹具；
3. `FTS_COLUMN_WEIGHTS = (1.0, 5.0, 1.0)` 是否需要在合并前调整（当前无数据支撑，仅按裁定与参考实现）；
4. 是否同意 `test_recall.py` 的最小同步改动（§3-2）。
