# TASK-020：BM25 查询侧判别力修复（token 噪声过滤 + IDF 加权重排）

> 状态：pending ｜ 阶段：Phase 1（W3d，**检索质量关键**）｜ 硬依赖：TASK-016（OR 语义，已合并）｜ soft 依赖：无
> 建议分支：`feature/task-020_<你的缩写><MMDD>`（从最新 main）
> 交付物所有权：`core/zace_core/retrieval/bm25.py`、`core/zace_core/storage/store.py`（仅新增 DF/批量命中查询原语）、
> `core/tests/retrieval/`、`core/tests/storage/test_storage_fts.py`、`core/tests/integration/`
> 其它文件不得改动（尤其 `contextpack/`——装填层问题不在本卡范围）。

## 背景（编排者在真实 demo 仓库上实测，2026-09-10）

用指定的评测靶场 `aibox-super-sdk` 实测用户种子问题
**「workflow 在记忆系统里是怎么定义和使用的？」**，结果严重失真：

- 最终 ContextPack：**Docs 35 块 / Code 1 块**，且代码中唯一提到 workflow 的
  `src/aibox/capabilities/memory/internal/maintenance.py` **完全未出现**；
- 单独检索 `workflow` 时它明明排 BM25 第 3（实测 `fts_search("workflow", 5)`）。

### 根因实测数据（同一查询的分词与各 token 文档频率）

| token | DF | 判别力 |
|---|---|---|
| `workflow` | **22** | 强（真正的查询意图词） |
| `里` | 19 | 弱（疑问虚词，非意图） |
| `怎么` | 19 | 弱（同上） |
| `记忆系统` | 462 | 弱 |
| `是` / `使用` | 494 / 531 | 弱 |
| `在` | 825 | 弱 |
| `定义` | 386 | 弱 |
| `的` | 1485 | 弱 |
| `和` | 1680 | 弱 |
| `？` | **0** | 噪声（全库无命中） |

**机制**：TASK-016 的 OR 语义下，BM25 分 = 各命中 token 贡献之和。9 个高频虚词/常用词的
累加贡献远超单个稀有词 `workflow` ⇒ 只命中 `workflow` 的代码块被大量"命中 8-9 个高频词"的
Markdown 段落挤出 top50 ⇒ 召回层就丢了正确目标。

**另一独立现象**（同一根因的推论）：标点 `？` 被分词产出且 DF=0，导致
`AND` 语义恒为空（实测 AND 命中数 = 0）——即 TASK-016 保留的高精度通道实际不可用。

**连带失真**（负例）：查询「Kubernetes operator 的部署协调逻辑在哪里实现？」在该仓库中
应为负例（已 grep 核验 0 命中），实测却返回 11 个文档块，无 `missingEvidence` 提示——
因为 `部署`/`协调`/`实现` 等高频词命中了无关段落。修复本卡后应显著改善（不要求彻底解决，
负例判定属 answerable 规则，见"明确不做"）。

## 修复要求

### A. 查询侧 token 过滤（确定性，零业务规则）

分词产物进入 FTS MATCH 前过滤：

1. **纯标点/空白 token 丢弃**（如 `？` `：` `,` `.`）——判据：token 中不含任何字母/数字/CJK 字符；
2. **库中不存在的 token 丢弃**（DF=0）——需一次轻量查询（见 §B 原语）；
   注意：只在 `operator="or"` 路径生效，`"and"` 路径保持原样（调用方明确要高精度时应如实返回空）。

> 纪律说明：这不是"业务关键词规则"（违反 R4/D-14），而是**通用检索卫生**——停用词表仍然不做。

### B. IDF 加权重排（核心修复）

保留现有"OR 召回"的召回率，但**排序改为按判别力加权**：

```text
对每个候选 chunk c：
  weighted(c) = Σ_{t ∈ tokens, t 命中 c} IDF(t)         # 或等价的 bm25 加权形式
按 weighted(c) 降序 → 转成 1-based rank 交给 RRF（D-16 的"只用排名"约定不变）
```

- IDF 可取 `log2(1 + N/DF)`（N = chunks 总数；`Store.counts()["chunks"]` 或同义查询）；
- `Store` 新增原语（保持纯数据访问，不含检索策略）：
  - `chunk_count() -> int`（若已有 `counts()` 可复用则不必新增）；
  - `token_document_frequency(tokens: Sequence[str]) -> dict[str, int]`（批量 DF，单条 SQL 完成）；
  - `fts_hit_tokens(chunk_ids, tokens) -> dict[str, set[str]]` 或等价批量原语
    （避免 N×M 次单查——**性能是硬要求**，见 DoD）；
- 原 `bm25(chunks_fts)` 分值仍可保留用于 `reasons` 展示，但**排名以加权分为准**。
- FTS5 原生 bm25() 的列权重（TASK-016 的 `FTS_COLUMN_WEIGHTS`）保持不变，两者不冲突。

### C. 回归与护栏

- 保持 `operator="and"` 语义与既有测试不变；
- `bm25_query_text` 的既有归一化（去反引号/`::`）保留；
- 空查询 / 全 token 被过滤 → 返回空列表（不抛异常）。

## 验收标准（DoD）

- [ ] **核心回归（必须，用真实仓库）**：对 `aibox-super-sdk`
      （`/home/xuwenzheng/4_AIBOX/gitlab/minicpm/aibox-super-sdk`，索引数据可由
      `uv run zace-core ingest --repo <路径> --data <临时目录>` 重建，
      或复用已在 `/tmp/zace-aibox` 的索引）执行查询
      `workflow 在记忆系统里是怎么定义和使用的？`，断言：
      1. `src/aibox/capabilities/memory/internal/maintenance.py` **出现在 BM25 通道 top10**；
      2. 最终 ContextPack 中该文件可见（或至少其 BM25 rank ≤10 且进入候选池）。
      —— 允许把该断言写成 `@pytest.mark.slow` + 环境变量开关的集成测试（大仓库索引耗时长），
      但**必须在执行记录里贴出实跑输出**。
- [ ] **性能**：`fts_search` 的重排路径在 50 候选 × 10 token 规模下额外开销 <20ms（单测计时）；
      批量 DF 查询不超过 2 条 SQL。
- [ ] 单测：token 过滤（标点、DF=0）、IDF 权重单调性（稀有词命中应排在多高频词命中之前）、
      空结果、`operator="and"` 不变。
- [ ] 全仓 `uv run pytest` 全绿（既有 484 用例零回归；如既有 BM25 断言因排序变化需调整，
      逐条说明理由，**不得弱化覆盖**）。
- [ ] `uv run ruff check .`、`uv run python scripts/check_dependency_direction.py` 通过。
- [ ] 修复前后对比（贴进执行记录）：该查询的 BM25 top10 列表 + 最终 ContextPack 的
      **Code/Docs 块数量** + 目标文件是否出现。
- [ ] 任务卡"执行记录"回填 + 任务板状态改 review。

## 明确不做

- **不做停用词表**（违反 Module/02 R4 的"少规则"纪律；IDF 加权是通用解法，不需要人工词表）；
- 不改 RRF 公式与通道权重（D-16）；不改 rerank 特征表（TASK-015 校准项）；
- **不改装填层配额**（Code/Docs 配额平衡是独立议题，若本卡修复后仍失衡，另立卡）；
- 不改 `answerable` 判定规则（负例弱点属 Module/03 §4.4 的规则范畴，需编排者另行裁定）；
- 不改向量通道。

## 参考

- `docs/plan/contracts.md` §3.3 R11（BM25 OR 语义的来源）、§3.5 R20（本卡背景裁定）
- codegraph `source/codegraph/src/db/queries.ts:1505-1513`（OR + 列权重参考；**其未做 IDF 重排**，
  本卡是 zace 的增量改进）
- FTS5 文档：`bm25(fts, w1, w2, ...)` 与 `fts5vocab` 表（可作为 DF 查询的替代实现路径）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写；执行记录必须含**真实仓库修复前后对比**。

## 执行记录

（实施 AI 在此填写。）
