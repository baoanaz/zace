# 基准题库与首轮质量评测（v1 · 2026-09-15）

> 状态：**已实测**｜设备：`vps-la-2c2g`｜索引：`/root/.zace/bench/voyage-4-lite-d1024`（复用 v1 持久索引，未重建）
> 题库：`benches/golden/{leveldb,HelloAgents,langchain}/`（各 20 题，共 60 题；题目 + 人工核实答案见各目录 `qa.md`）
> 跑分脚本：`benches/golden/qa_probe.py`｜原始证据：`benches/results/raw/qa-probe/*.json`

## 0. 一句话

**search 侧 recall@5 = 0.64–0.77、MRR 0.39–0.69；ask 侧 16 条全部产出答案且证据不足时如实拒绝（不编造），
但 ask 的成败由「检索层有没有把证据捞进包」决定 —— leveldb 有 4/5 条 ask 题根本没捞到证据。**

## 1. 题库设计

| 仓库 | 题目文档 | 机器可跑 | search 题 | ask 题 | 负例 |
|---|---|---|---|---|---|
| leveldb @ `7ee830d` | `benches/golden/leveldb/qa.md` | `leveldb.jsonl` | 15 | 5 | 1 |
| HelloAgents @ `93e77ea` | `benches/golden/HelloAgents/qa.md` | `HelloAgents.jsonl` | 14 | 6 | 1 |
| langchain @ `41d3572` | `benches/golden/langchain/qa.md` | `langchain.jsonl` | 15 | 5 | 1 |

- 每题在 `qa.md` 里给了**参考答案**（人工读码核实）、**依据路径**与**建议工具**：
  `search` = 定位/事实型（常量、定义、文件位置）；`ask` = 需要跨文件综合的解释型（流程、机制、为什么）。
- `expected[].path` 全部落在**被索引的文件集**内（langchain 特意避开了索引时被跳过的 `libs/core/langchain_core/runnables/base.py`）。

## 2. 首轮结果

| 仓库 | search recall@5 | recall@10 | MRR | 负例通过 | ask 有答案 | ask `pack_hit`（检索层） | ask `answer_hit`（正文点名期望文件） |
|---|---|---|---|---|---|---|---|
| leveldb @ `7ee830d` | 0.7143 | 0.7143 | 0.3869 | 1/1 | 5/5 | 1/5 | 2/5 |
| HelloAgents @ `93e77ea` | 0.7692 | 0.9231 | 0.6926 | 0/1 | 6/6 | 5/6 | 2/6 |
| langchain @ `41d3572` | 0.6429 | 0.6429 | 0.6429 | 0/1 | 5/5 | 5/5 | 4/5 |

- ask 单题延迟中位 **9241 ms**（n=16，本机回环 LLM 网关、deepseek flash）；
- `pack_hit` = 期望路径出现在包内 top-10；`answer_hit` = LLM 答案正文里出现期望路径（严格口径，LLM 常只写 `[E1]` 引用号）。

## 3. 逐题结果

### 3.1 search 组

| ID | 类别 | 排名 | 结果 | top-3（失败诊断） |
|---|---|---|---|---|
| L-01 | symbol | 1 | ✅ 命中 |  |
| L-02 | symbol | 4 | ✅ 命中 |  |
| L-03 | symbol | — | ❌ 未命中 | db/version_set.h:252-255 (leveldb::VersionSet::NeedsCompaction) … |
| L-04 | spec | 3 | ✅ 命中 |  |
| L-05 | spec | — | ❌ 未命中 | db/log_format.h:9-9 (STORAGE_LEVELDB_DB_LOG_FORMAT_H_) ; doc/impl.md:1-21 (Files > Log files) … |
| L-06 | symbol | 4 | ✅ 命中 |  |
| L-07 | path | 1 | ✅ 命中 |  |
| L-08 | behavior | 4 | ✅ 命中 |  |
| L-11 | symbol | — | ❌ 未命中 | table/block_builder.cc:40-44 (leveldb::BlockBuilder::BlockBuilder) … |
| L-12 | symbol | — | ❌ 未命中 | db/version_edit.h:29-31 (leveldb::VersionEdit) ; doc/impl.md:44-56 (Sorted tables > Manifest) … |
| L-13 | behavior | 2 | ✅ 命中 |  |
| L-15 | symbol | 1 | ✅ 命中 |  |
| L-17 | path | 2 | ✅ 命中 |  |
| L-18 | symbol | 3 | ✅ 命中 |  |
| L-20 | negative | — | ✅ 负例通过 | benchmarks/db_bench_sqlite3.cc:674-726 (main) ; util/testutil.h:22-25 (EXPECT_LEVELDB_OK) ; include/leveldb/export.h:23-23 (LEVELDB_EXPORT) |
| H-01 | symbol | 1 | ✅ 命中 |  |
| H-02 | symbol | 1 | ✅ 命中 |  |
| H-03 | behavior | 1 | ✅ 命中 |  |
| H-04 | behavior | 1 | ✅ 命中 |  |
| H-07 | behavior | 7 | ✅ 命中 |  |
| H-08 | path | 2 | ✅ 命中 |  |
| H-09 | behavior | 1 | ✅ 命中 |  |
| H-11 | behavior | 1 | ✅ 命中 |  |
| H-13 | symbol | 4 | ✅ 命中 |  |
| H-14 | behavior | 1 | ✅ 命中 |  |
| H-16 | behavior | 1 | ✅ 命中 |  |
| H-17 | behavior | — | ❌ 未命中 | docs/streaming-sse-guide.md:99-136 (流式输出与 SSE 指南（Streaming & SSE） > 💡 核心概念) … |
| H-19 | behavior | 9 | ✅ 命中 |  |
| H-20 | negative | — | ✅ 负例通过 | README.md:100-141 (HelloAgents > 🏗️ 项目结构) ; .env.example:1-91 ((module)) ; docs/custom_tools_guide.md:296-298 (HelloAgents 自定义工具开发指南 > 🎓 实战示例 > 3. cod |
| LC-01 | symbol | — | ❌ 未命中 | libs/core/langchain_core/output_parsers/pydantic.py:57-93 (PydanticOutputParser.parse) … |
| LC-02 | symbol | 1 | ✅ 命中 |  |
| LC-03 | symbol | — | ❌ 未命中 | libs/langchain_v1/tests/unit_tests/agents/middleware/implementations/test_summarization.py:1478-1479 (test_and … |
| LC-04 | symbol | 1 | ✅ 命中 |  |
| LC-05 | symbol | 1 | ✅ 命中 |  |
| LC-06 | path | — | ❌ 未命中 | libs/partners/anthropic/tests/unit_tests/middleware/test_prompt_caching.py:539-542 (TestToolCaching.test_does_ … |
| LC-08 | path | — | ❌ 未命中 | openwiki/architecture.md:307-316 (Key Files and Symbols > langchain-core) … |
| LC-09 | symbol | 1 | ✅ 命中 |  |
| LC-11 | symbol | 1 | ✅ 命中 |  |
| LC-12 | symbol | 1 | ✅ 命中 |  |
| LC-13 | symbol | 1 | ✅ 命中 |  |
| LC-15 | symbol | 1 | ✅ 命中 |  |
| LC-17 | behavior | 1 | ✅ 命中 |  |
| LC-19 | path | — | ❌ 未命中 | libs/langchain/langchain_classic/retrievers/ensemble.py:218-302 (EnsembleRetriever.rank_fusion) … |
| LC-20 | negative | — | ✅ 负例通过 | libs/langchain/langchain_classic/memory/entity.py:347-368 (SQLiteEntityStore) ; libs/core/README.md:13-52 (🦜🍎️ LangChain Core > Quick Install) ; libs/ |

### 3.2 ask 组

| ID | pack 排名 | 状态 | 正文点名 | 引用覆盖 | 结论（人工判读） |
|---|---|---|---|---|---|
| L-09 | — | answered | ❌ | 1.0 | 检索未捞到 `db/db_impl.cc#DBImpl::Get`；LLM **如实拒绝**（明确说"任何顺序陈述都会是虚构"）——行为对，但用户拿不到答案 |
| L-10 | — | answered | ✅ | 0.8261 | 只有 `doc/index.md` 的 sync 语义，没有写路径代码；LLM 标注了"代码证据不足"，只答了文档层 |
| L-14 | — | answered | ❌ | 0.4615 | 包内只有 `DBIter` 与 `dbformat.h` 的注释，没捞到 `DBImpl::Get`；LLM 拒绝编造 |
| L-16 | — | answered | ❌ | 0.3333 | 只用了 `doc/impl.md` 的 Level 0 流程，没有代码路径（`DBImpl::CompactMemTable`/`BuildTable` 都没进包） |
| L-19 | 1 | answered | ✅ | 1.0 | 唯一 pack_hit=1；答案与 README 一致（无 SQL / 单进程 / 无内置 C-S） |
| H-05 | 2 | answered | ❌ | 1.0 | 引到 `ToolStatus` 所在文件但未点出 PARTIAL 的语义结论，偏泛 |
| H-06 | 2 | answered | ❌ | 1.0 | 熔断阈值/恢复时间答对（3 次 / 300s），但未点名文件 |
| H-10 | 1 | answered | ✅ | 0.9167 | 答对：TaskTool 用 `_create_tool_filter` + `run_as_subagent` 隔离工具集，点名了文件 |
| H-12 | — | answered | ❌ | 0.8333 | 包内没捞到 `session_store.py`，LLM 只能说证据不足 |
| H-15 | 1 | answered | ❌ | 1.0 | 答对截断+另存全文，但未点名文件 |
| H-18 | 1 | answered | ✅ | 0.7 | 答对：按 base_url 自动选适配器 + `LLM_BASE_URL` 兜底，点名了文件 |
| LC-07 | 1 | answered | ✅ | 1.0 | 答对且点名 `vectorstores/base.py`（add_texts/similarity_search 抽象、add_documents 有默认实现） |
| LC-10 | 1 | answered | ✅ | 0.875 | 答对：BaseRetriever ↔ VectorStoreRetriever + `as_retriever` |
| LC-14 | 2 | answered | ✅ | 1.0 | 答对 cleanup 三档与 sha1 key；**明确指出包内函数体被截断 292 行**，所以判定逻辑只能靠测试反推 |
| LC-16 | 1 | answered | ❌ | 1.0 | 三个 Runnable 的职责答对（fallback/retry/branch），但未点名文件 |
| LC-18 | 1 | answered | ✅ | 0.6667 | 答对 5 种写法 + MessagesPlaceholder，点名了文件 |

## 4. 发现（按重要性）

1. **search 的失败几乎都是「符号级定位」，不是「没找到文件」**：
   - leveldb 4 条失败全是相邻/同名文件互串：期望 `db/dbformat.h`（L-03）给了 `db/version_set.h`；
     期望 `doc/log_format.md`（L-05）给了 `db/log_format.h` + `doc/impl.md`；期望 `include/leveldb/options.h`（L-11）给了 `table/block_builder.cc` + `doc/index.md`；
     期望 `db/version_edit.cc`（L-12）给了 `db/version_edit.h`。→ **.h/.cc 成对文件与 doc/代码同主题文件的区分度不足**。
2. **langchain 有 2/5 的"失败"其实是判定口径偏严**：LC-01 的 top1 就是期望文件（`output_parsers/pydantic.py`），
   只是命中的是 `PydanticOutputParser.parse` 而非类定义；LC-03 的 top2 也在期望文件里（`messages/utils.py`）。
   → 评估器要求 `symbol` 同时出现，对"按文件算命中"的场景会低估。**建议新配置 A/B 时同时看文件级命中率**。
3. **大仓库的概念歧义**：LC-06（问 `@tool`）召回的是 anthropic 测试里的 `.my_tool`；LC-19（问 BM25 检索器）召回 `EnsembleRetriever`。
   → 单靠语义相似度在 2 万 chunk 规模上会被"同名/近义词"带偏，需要符号通道加权（属检索侧改进，不在本轮范围）。
4. **负例 2/3 失败**（HelloAgents H-20「Qdrant 实现」、langchain LC-20「SQLite FTS5」）：系统判 `answerable=True`，
   因为检到了名字沾边的 `SQLiteEntityStore` / `README 项目结构`。→ **可回答性阈值在大仓库上偏宽松**，会把"沾边但不相关"当成证据。
5. **ask 的质量上限由检索决定**：leveldb 的 ask 题 4/5 在检索层就没捞到证据，LLM 只能回答"证据不足"——
   这是**正确行为**（不编造、明确标注缺口），但说明"问复杂流程题时先把检索修好"优先级高于换模型。
6. **包内截断直接限制 ask 深度**：LC-14 的答案里明确出现"函数体被省略 292 行"。→ 与你接下来要调的 chunk 策略强相关：
   **chunk 越小/包内截断越狠，ask 能答的深度越浅**，这条会把"索引更快"直接兑换成"回答更浅"。

## 5. 复现命令

```bash
set -a; . /etc/zace/zace.env; set +a   # EMBED_* + ANSWER_*（密钥不进仓库）

# 三仓库一把跑（按每题标注的 tool 分别走 search / ask）
for pair in leveldb:3ed886ce58bc0e47 HelloAgents:06078cc80c7ce7d7 langchain:ca2050db0db5b1e2; do
  repo="${pair%%:*}"; pid="${pair##*:}"
  uv run python benches/golden/qa_probe.py --golden "benches/golden/$repo/$repo.jsonl" \
    --project-id "$pid" --data /root/.zace/bench/voyage-4-lite-d1024 \
    --out "benches/results/raw/qa-probe/$repo.json"
done

# 只跑 search 侧（core 自带评估器，输出 recall/MRR 报告）
uv run zace-core eval --golden benches/golden/leveldb/leveldb.jsonl \
  --project-id 3ed886ce58bc0e47 --data /root/.zace/bench/voyage-4-lite-d1024 \
  --report /tmp/leveldb-eval.md
```

## 6. 与「维度 / chunk 策略」实验的关系

- 这 60 题就是那批实验的**质量护栏**：换维度会直接改向量语义与命中排序，换 chunk 会改切片边界与包内截断深度；
- 判据建议：**质量不允许下降**（文件级命中率与 ask 答案正确率），再谈耗时收益；
- 注意方差：search 侧指标是确定性的（同一索引重复跑结果一致），不需要像耗时那样跑多次；
  ask 侧受 LLM 采样影响，同一题可能波动，比较时建议同温度重复 2 次或只看定性结论。

