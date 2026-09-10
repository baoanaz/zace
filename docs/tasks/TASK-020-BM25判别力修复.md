# TASK-020：BM25 查询侧噪声 token 过滤（原 IDF 重排方案已被实测否决）

> 状态：review（实施完成，待编排者复核）｜ 阶段：Phase 1（W3d）｜ 硬依赖：TASK-016（OR 语义，已合并）｜ soft 依赖：无
> 建议分支：`feature/task-020_<你的缩写><MMDD>`（从最新 main）
> 交付物所有权：`core/zace_core/retrieval/bm25.py`、`core/tests/retrieval/`、`core/tests/storage/test_storage_fts.py`
> （**不新增 Store 原语**——见 §D；`contextpack/` 与 `storage/store.py` 本卡不得改动）

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

### B. ~~IDF 加权重排~~ —— **经实测否决，不要实现**（编排者 2026-09-10 更正）

实施 AI 按本卡原公式（Σ IDF）实测：目标块 rank **797**（DoD 要求 ≤10）；编排者独立复现得
**rank 148**（同一量级）。根因经数据确认：

| 排序方案 | 目标块 rank | 原因 |
|---|---|---|
| FTS5 原生 bm25（当前） | 跌出 top50 | OR 语义下多词命中累加 |
| **Σ IDF（本卡原公式）** | **148 / 797** | Σ 仍奖励"命中词多"的块；且丢掉 bm25 的长度归一 |
| max-IDF 门控（必须命中 workflow） | 21 | 有好转但仍不达 ≤10；且装填层 R21 会再溺一次 |

另一关键数据：`workflow` 的 IDF=8.04，而虚词 `里`/`怎么` 的 IDF=**8.25**（jieba 碎片化产物，
DF 仅 19）——**稀有度本身在本语料上不可靠**，所以纯 IDF 家族（Σ/ max）都无法单独解决。

**结论：排序变更属风险变更，必须先在 golden set（TASK-014）上验证，不得在本卡拍脑袋做。**
本卡只保留 §A（确定收益且零风险）——详见下方 §D。

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

### D. 本卡最终范围（编排者裁定 2026-09-10；已含实测修正）

**只做 §A 的纯函数部分**：

1. `is_noise_token`（纯标点判定）+ `filter_bm25_tokens(tokens)`（**不接 `store` 参数**）；
2. `recall_bm25` 用它清洗 MATCH 串；
3. **删除逐 token 的 DF 探测**（`store.fts_search(token, limit=1)`）：实测 `fts_search` 的唯一生产调用方
   是 `recall_bm25`，而它恒用 `operator="or"`；**OR 语义下 DF=0 token 对结果零影响**（实测：含/不含
   `？` 的 OR 结果逐项相同）——探测只带来 1+N 条 SQL（约 7.4ms/查询）而零收益；
4. `operator="and"` 路径不由本卡处理：无生产调用方；未来启用时由调用方自备 DF=0 清洗
   （在模块 docstring 里写明这条约定）。

**不实现**：IDF 加权重排（已实测否决）、停用词表/词性过滤、新 Store 原语、排序行为变更。

保留的确定收益（诚实表述）：进入 MATCH 的 token 串更干净，且把“AND 需自行清洗”的口径写进代码与测试；
**对 OR 召回结果无任何改变**（这是实测结论，不要声称有质量提升）。

### C. 回归与护栏

- 保持 `operator="and"` 语义与既有测试不变；
- `bm25_query_text` 的既有归一化（去反引号/`::`）保留；
- 空查询 / 全 token 被过滤 → 返回空列表（不抛异常）。

## 验收标准（DoD）

- [ ] **噪声过滤回归**（纯函数级，不要求 SQL）：
      ① `is_noise_token` 对标点/空白/符号为真，对字母/数字/CJK 为假；
      ② `filter_bm25_tokens` 不接 store 参数；③ 全 token 被过滤 → 返回空列表。
- [ ] **性能回归（本卡新增硬要求）**：`recall_bm25` 单次调用不得引入逐 token SQL 探测——
      断言其 SQL 调用次数与 TASK-016 一致（可用计数包装 store 验证）；实测单次 `fts_search` 耗时不因本卡上升。
- [ ] **真实仓库前后对比（必须）**：对 `aibox-super-sdk` 查询
      `workflow 在记忆系统里是怎么定义和使用的？`，贴出：
      ① 过滤前/后进入 MATCH 的 token 清单；② 目标文件
      `src/aibox/capabilities/memory/internal/maintenance.py` 的 **BM25 rank 前后对比**；
      ③ 最终 ContextPack 的 Code/Docs 块数。
      —— 索引数据可直接复用 `/tmp/zace-aibox`（project id `8f39057792cf72e8`）；
      若需重建：`uv run zace-core ingest --repo /home/xuwenzheng/4_AIBOX/gitlab/minicpm/aibox-super-sdk --data /tmp/zace-aibox`（约 17 分钟）。
- [ ] **不要求**目标块进 BM25 top10：编排者原 DoD 已被数据推翻（见 §B 与未决问题 R21）；
      本卡只要求其 rank **不劣于**修复前且噪声路径被清理。
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

- **不做 IDF/加权重排**（原方案已被实测否决，见 §B）；
- **不做停用词表/词性过滤**（后者已实验：过滤虚词后 Σ IDF 仍为 rank 148，收益不足且引入行为变更）；
- 不改 RRF 公式/通道权重/rerank 特征表/装填配额/向量通道/DF 与 hash 语义；
- 不改 `answerable` 规则（负例弱点见 R22，属 Module/03 §4.4 范畴）。

## 参考

- `docs/plan/contracts.md` §3.3 R11（BM25 OR 语义的来源）、§3.5 R20（本卡背景裁定与**实测否决记录**）
- codegraph `source/codegraph/src/db/queries.ts:1505-1513`（OR + 列权重参考）
- FTS5 文档：`bm25(fts, w1, w2, ...)` 与 `fts5vocab` 表（可作为 DF 查询的替代实现路径）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写；执行记录必须含**真实仓库修复前后对比**。

## 执行记录

### TASK-020 完成报告（2026-09-10，第二轮：按修订后 §D 收窄为「零成本清理」）

- 分支：`feature/task-020b_xwz0910`（从 `main@086d24e` 开；上一轮分支 `feature/task-020_xwz0910`
  已按指令删除，其 DF 探测实现**未带入**本轮；仅本地提交，未 push）
- 交付（严格限定在卡内所有权清单）：
  - `core/zace_core/retrieval/bm25.py`：`is_noise_token`（纯标点判定）+ `filter_bm25_tokens(tokens)`
    （**签名不接 `store`**，纯函数零 SQL）+ `recall_bm25` 接入清洗 + 模块 docstring 写明
    「`operator="and"` 路径若未来启用，需调用方自备 DF=0 清洗」的约定；
  - `core/tests/retrieval/test_bm25.py`（+5 用例）、`core/tests/storage/test_storage_fts.py`（+1 用例）；
  - **未改** `storage/store.py`（无新 Store 原语）、未动 RRF/rerank/装填层/向量通道/契约/设计文档。

#### 验收命令与结果

| 命令 | 结果 |
|---|---|
| `uv run ruff check .` | All checks passed! |
| `uv run python scripts/check_dependency_direction.py` | 依赖方向检查通过（core 纯库 / service 不上探） |
| `uv run pytest` | **490 passed, 2 skipped**（基线 484 + 本卡新增 6；零回归） |
| `uv run pytest core/tests/retrieval/test_bm25.py core/tests/storage/test_storage_fts.py -q` | 13 + 11 passed |

#### 是否引入额外 SQL / 耗时（性能回归结论）

**零额外 SQL**：`recall_bm25` 单次调用恒为 **1 条 `fts_search`**，不随 token 数增长——
由 `test_recall_bm25_does_not_probe_tokens_one_by_one`（`_CountingStore` 计数包装）固定：
单 token 查询与 ≥6 token 查询的 SQL 次数都恰为 1，且 `operator` 恒为 `"or"`。

| 指标（真实靶场，20 次采样） | 上一轮（已否决的 DF 探测） | 本轮（纯函数清洗） |
|---|---|---|
| `recall_bm25` 额外 SQL | 11 条（1+11，逐 token `fts_search(limit=1)`） | **0 条** |
| 清洗自身耗时 | 约 7.4ms/查询 | **0.0036ms**（`filter_bm25_tokens`） |
| 单次 `fts_search(limit=50)` | 7.02ms（含 `？` 的 MATCH 串） | 6.61ms（清洗后，差异在噪声内） |
| 单次 `recall_bm25` 端到端（含分词） | — | 6.80ms |

#### 真实仓库前后对比（靶场 `aibox-super-sdk`；复用只读索引 `/tmp/zace-aibox`，project `8f39057792cf72e8`，434 文件 / 5760 chunks）

查询：`workflow 在记忆系统里是怎么定义和使用的？`（「前」= TASK-016 原路径直接 `fts_search`，
「后」= 本卡 `recall_bm25`；两组均在同一索引上实测）

**① 进入 MATCH 的 token 清单**

| | token 清单 | 个数 |
|---|---|---|
| 前 | `workflow 在 记忆系统 里 是 怎么 定义 和 使用 的 ？` | 11 |
| 后 | `workflow 在 记忆系统 里 是 怎么 定义 和 使用 的` | 10 |
| 丢弃 | `？`（DF=0，全库无命中；`is_noise_token` 判为纯标点） | 1 |

各 token 实测 DF：`workflow 22`、`在 825`、`记忆系统 462`、`里 19`、`是 494`、`怎么 19`、
`定义 386`、`和 1680`、`使用 531`、`的 1485`、`？ 0`（与卡内背景表一致）。

**② 目标文件 `src/aibox/capabilities/memory/internal/maintenance.py` 的 BM25 rank 前后对比**

| 指标 | 前 | 后 |
|---|---|---|
| OR 命中集规模 | 2400 | 2400 |
| 目标文件首个块（`...(module):1`）rank | 471 | **471（不劣化）** |
| 是否进 top50 | 否 | 否 |
| OR 结果 chunk_id 序列逐项一致 | — | **是** |
| bm25 分值序列逐项一致 | — | **是** |

**③ 最终 ContextPack 的 Code/Docs 块数**（`zace-core search --json`，预算 10000 tokens）

| 指标 | 前 | 后 |
|---|---|---|
| Code（`evidence` 非 elided） | 1（`.../memory/example/chatbot/agent.py`） | 1（同） |
| Docs（`docs` 非 elided） | 34 | 34 |
| 目标文件出现 | 否 | 否 |
| answerable / confidence | True / medium | 完全相同 |
| budget | usedTokens 9087、truncated True、omittedCount 6 | 完全相同 |
| `--json` 全量输出 | — | 与修复前 **逐字节一致**（`diff` 无差异） |

**结论（诚实表述）**：本卡对 **OR 召回结果与最终 ContextPack 无任何改变**（实测逐项/逐字节一致）——
这正是 R20 的实测结论，不声称任何质量提升。确定收益是：① 进入 MATCH 的 token 串更干净；
② 删除约 7.4ms/查询的零收益探测；③ 把「AND 需调用方自备 DF=0 清洗」的口径写进代码与测试。
目标 rank 471 与装填层 Docs/Code 失衡按裁定分别归 R24 / R21。

#### 测试覆盖（对照修订后 DoD）

| DoD 条目 | 落点 |
|---|---|
| ① `is_noise_token` 真值表 | `test_is_noise_token_truth_table`（标点/空白/符号为真；字母/数字/CJK/混合/`token_1` 为假） |
| ② `filter_bm25_tokens` 不接 store | `test_filter_bm25_tokens_is_a_pure_function`（`inspect.signature` 断言参数恰为 `["tokens"]`） |
| ③ 全 token 被过滤 → 空列表 | `test_recall_bm25_returns_empty_when_every_token_is_noise`（4 组纯标点查询） |
| 性能回归（新增硬要求） | `test_recall_bm25_does_not_probe_tokens_one_by_one`（单次调用恒 1 条 SQL、`operator="or"`） |
| 不得声称质量提升 | `test_noise_filter_does_not_change_or_results`（清洗前后 OR 的 chunk_id 与 bm25 分逐项一致） |
| 保持 `operator="and"` 语义与 Store 边界 | `test_operator_and_boundary_facts_are_unchanged_by_query_side_cleaning`（Store 层：标点不影响 OR/AND；库外词仍使 AND 恒空） |

上一轮写入 `test_storage_fts.py` 的 `test_operator_and_is_unchanged_by_query_side_noise_filtering` 因从最新
`main` 重开分支已不在工作树中；本轮以新口径的 Store 层用例重新落点，断言**未弱化**（新增 OR 逐项一致断言）。

#### 契约影响

无。只改 `retrieval/bm25.py` 内部与两个测试文件；`Store` 签名/语义、`types.py`、`interfaces.py`、
`docs/contracts/**`、`docs/design/**`、RRF/rerank/装填层/向量通道全部未动。

#### 与设计偏差

无。本轮严格按修订后 §D 执行：`filter_bm25_tokens` 不接 `store`、无逐 token DF 探测、
无 IDF 重排、无新 Store 原语、无排序行为变更。

#### 未决问题

1. **R20 因果描述已按实测修正，卡内 §A/§D 的历史文字仍留有旧表述**（§A.2「库中不存在的 token 丢弃
   ——需一次轻量查询」已由 §D.3 显式推翻；§B 保留为否决记录）。本轮不改设计/契约文档，仅提示编排者：
   任务卡正文中 §A.2 与 DoD 中「批量 DF 查询不超过 2 条 SQL」「IDF 权重单调性」「目标块进 BM25 top10」
   仍是 §B 时代的残留条目（与本轮范围冲突），建议在合并时统一清理。
2. **`？` 不会使 AND 恒空**（R20 已裁定，本轮测试已按真实机制落点）：FTS5 unicode61 把不可切分标点
   当分隔符，`"？"` 不产生词项。真实使 AND 恒空的是**可切分但库外（DF=0）**的 token（如 `k8s`）。
   因 `filter_bm25_tokens` 不再探测库内，**本卡实现不解决该场景**——按 §D.4 属未来 AND 调用方责任。
3. **R22 负例未改善（预期内）**：负例 `Kubernetes operator 的部署协调逻辑在哪里实现？` 的 token
   `Kubernetes(DF=3)/operator/部署/协调/逻辑/实现` 均在库中，唯一 DF=0 的仍是 `？`，
   清洗后 token 集仅少一个零贡献项，故结果不变（仍无 `missingEvidence`）。按卡「明确不做」转 R22/R24。
4. **目标 rank 471 未改善**：本卡范围内不可解（排序变更属 R24，需 golden set 基线）。
