# 契约冻结清单（CF）

> 状态：2026-09-10 冻结。维护者：编排者；变更流程见 `docs/plan/orchestration.md` §4。
> 原则：**跨任务的一切接口都是契约**；契约文件之外的实现细节自由。

## 1. 冻结清单

| # | 契约 | 文件 | 设计来源 | 主要消费者 |
|---|---|---|---|---|
| CF-01 | index.db DDL（表/列/索引/语义） | `docs/contracts/index-schema.sql` | Module/01 §3.3 | 001/006/007/010/011 |
| CF-02 | 三种 hash 语义与函数 | `core/zace_core/hashing.py` | Module/01 §2.4、D-43 | 001/007/009；Phase 2 client |
| CF-03 | ContextPack JSON 合同 | `docs/contracts/contextpack.schema.json` | Module/03 §2、D-21 | 012/013；Phase 2/3 service/web |
| CF-04 | 检索候选内部结构（Candidate/Flow/MissingEvidence） | `core/zace_core/types.py` | Module/02 §4、Module/03 §2 | 010/011/012 |
| CF-05 | REST API 形态（路径/方法/关键 payload） | `docs/contracts/openapi.yaml` | Module/06 §2.1、D-37 | Phase 2 service/client/web |
| CF-06 | MCP 工具 schema | `docs/contracts/mcp-tools.json` | Module/05 §2.1、D-12 | Phase 2 client |
| CF-07 | ContextEngine 接口面 | `core/zace_core/interfaces.py` | Module/06 §1、D-34 | 007/013；Phase 2 service |
| CF-08 | 索引侧数据类型（ParsedFile/Symbol/Edge/Chunk/FileDelta） | `core/zace_core/types.py` | Module/01 §2 | 002..007/009 |
| CF-09 | Provider 接口（Embedding/Answer/Parser） | `core/zace_core/interfaces.py` | Module/01/04、D-44 | 002..005/008；Phase 3 |

> CF-09 变更（2026-09-10，L2，编排者）：`EmbeddingProvider` 新增 `embed_query()`——e5 类模型 query/passage 前缀不同，检索侧必须走专用方法；索引侧一律 `embed()`。实现（TASK-008）已含此方法，本次仅补契约；同时统一 `model_id` 命名示例为 `local:<slug>`。

## 2. 跨文件不变式（写代码时不得违反）

1. `chunk_id = {path}:{symbol_fqn}:{start_line}`（spec 块的 `symbol_fqn = heading_path`），代内唯一即可（D-04）。
2. `blob_hash / file content_hash / chunk content_hash` 三者用途互不可替代（D-43 / CF-02）。
3. `symbol_kind ∈ {function, method, class_skeleton, spec_block, fallback_block, ...}`；spec 块双表同 id（见 §3-2）。
4. `evidenceTier` 是元数据 + 装填资格线 + rerank 特征，**不是 ORDER BY**（D-17）。
5. `evidence` 与 `docs` 共用 `E` 编号空间，`flows` 用 `F` 编号（D-21）。
6. RRF `K=60` 且融合层不加通道权重（D-16）。
7. `spec_references.provenance` 永远 `inferred`（D-06）。
8. 所有面向 agent 的时间/预算语义：`freshness` 如实报告，缺证据必须有 `missingEvidence`（D-30、A5）。

## 3. 规划期与实现期裁定（编排者；需在对应 Module 文档下次修订时回记）

### 3.1 规划期裁定（2026-09-10）

1. **chunks_fts 采用独立 FTS5 表（非 external content）**：D-20/D-45 要求索引侧写入预分词文本，与 external-content 直读 `chunks.content` 冲突；写入器与 chunks 同事务维护，渲染一律用原文。DDL 见 CF-01 文件头。
2. **SpecBlock 双表同 id**：检索单元同时写入 `chunks(symbol_kind='spec_block')` 与 `spec_blocks`（结构字段：doctype/heading_path/code_fences）；保证单一 RRF 池、单一向量表、单一 E 编号空间（D-42 的"不新增检索通道"由此落地）。
3. **batch-upload 的 blob 内容编码 = base64（`contentB64`）**：JSON 传输二进制安全；gzip 是否叠加留待 Phase 2 实测（Module/05 §9-2 开放问题不变）。
4. **MCP 工具 description 文案可由 client 任务打磨，但 schema（名字/参数/类型/默认值/上限）冻结**（CF-06 文件头声明）。

### 3.2 实现期裁定（W1 泳道评审，2026-09-10；均已核对代码与测试）

| # | 议题 | 裁定 | 影响 |
|---|---|---|---|
| R1 | `.h` 的 C/C++ 归属 | 默认归 C（TASK-002 registry）；**仓库级策略归 TASK-007 实现**：当仓库已见任意 C++ 扩展名文件（.cc/.cpp/.cxx/.hpp/.hh/.hxx/.ipp/.tpp）时，`.h` 改由 C++ 解析器处理（在 C++ 仓库里 `.h` 语义上就是 C++ 头） | TASK-007 卡片已补口径；V1 已知限制：先索引 `.h` 后出现 `.cpp` 时旧 `.h` 需等下次变更才重解析 |
| R2 | `EmbeddingProvider.embed_query()` | 升格为契约（见 CF-09 说明） | TASK-010 检索侧必须调用；TASK-007 索引侧用 `embed()` |
| R3 | `model_id` 命名 | `local:<slug>` / `api:<model_name>`（落库→改名等于换模型），修订 interfaces.py 示例 | — |
| R4 | `FileDelta` 三集合语义 | 两两不重叠：`new` = hash 新增/变化（需嵌入），`reused` = hash 未变（可复用向量，**复用键是 hash 不是 id**），`removed` = 旧 id 消失（删向量）；下游 upsert/delete 顺序无关 | TASK-007 按此对账 |
| R5 | edges 归属与重挂 | 边按 **source 侧**文件归属（文件变更只清 source ∈ 本文件的边，防误删入边）；符号行号漂移时 spec 引用从旧 id 重挂新 id，fqn 消失才 stale=1 | TASK-006 消费 |
| R6 | C++ MISSING 容忍（TASK-004 偏差申请） | 接受：**仅** 全部错误均为 MISSING 且 ≤5 条时照常抽取（错误入 parse_errors、宏生成声明入 unresolved）；出现任何 ERROR 或超限仍整体 fallback | 仅 cpp.py 内实现 |
| R7 | 函数原型不成符号（TASK-003） | 接受：仅声明的头文件只产出 include-guard 宏；定义处成符号，解析层按 fqn 匹配 | TASK-014 出题时避免只靠声明定位 |
| R8 | imports 边 target_name 形态 | 接受现有形态（如 `.service.Service` / `x.*`）；fqn 化与跨文件匹配算法全部归 TASK-006（含相对导入/包语义） | TASK-006 需要处理该形态 |
| R9 | SpecBlock 结构口径（TASK-005 补充） | 前言块 heading_path=`(preamble)`、level=0；front matter 单独成块；fence 归属最内层 SpecBlock；content 用 splitlines 归一 | TASK-006 切片按此 |
| R10 | 向量相似度语义（TASK-009） | `search()` 返回余弦相似度（越大越相关，按分降序）；`rebuild(dim)` 用 `create_table(mode='overwrite')` 原子替换（LanceDB OSS 无 rename_table）；单写者假设 | TASK-010 直接消费 |

### 3.3 集成期裁定（编排者 E2E 实测发现，2026-09-10）

| # | 议题 | 裁定 | 影响 |
|---|---|---|---|
| R11 | **BM25 多词召回语义**：TASK-001 的 `fts_search` 用 FTS5 隐式 AND，中文自然语言查询（分词后 7+ token）恒零命中 → Vector 单通道 → `answerable` 恒 False | **修复**：`fts_search(..., operator="or")` 为默认（OR 连接、每词引号包裹），`"and"` 保留供高精度调用；同时引入 bm25 列权重 `(content=1.0, signature=5.0, docstring=1.0)`。依据 codegraph `queries.ts:1505-1513`（OR + 列加权）【已验证·快照 2025-09】 | TASK-016；前缀匹配列为 TASK-015 校准项 |
| R12 | **证据块行号非单调**：`_try_merge` 按分数顺序拼接 content、lines 取包围盒 → 渲染出行号回跳（9→6→14→1），误导 agent 对齐编辑；`elidedLines` 语义失真 | **修复**：片段化存储 + 按行序渲染，`elidedLines` = 真实省略行数 | TASK-017 |
| R13 | 跨模块集成回归缺位 | **补齐**：新增 `core/tests/integration/` 承载 M1 级端到端回归（真实 Store+Vector+Indexer+retrieval+contextpack，embedding 用确定性假 provider） | TASK-016 交付该目录；TASK-013/014 在此基础上扩展 |

> 教训（记入流程）：逐模块测试全绿不等于产品可用——R11/R12 均为逐层测试无法暴露的集成缺陷。
> 故 W3 起，任何检索/组装类任务卡的 DoD 必须含跨模块 E2E 断言（已在 TASK-013/014 卡补充）。

## 4. 契约的验证方式（集成保障）

- CF-01：TASK-001 的测试必须真实执行该 SQL 建库；DDL 与测试一起通过才算契约落地。
- CF-03：TASK-012 必须对产出 JSON 做 schema 校验（`jsonschema` 校验器进 core dev 依赖，TASK-012 卡内落地）。
- CF-04/CF-07/CF-08：Python 类型层面由导入即用保证；签名变化即 CI 失败（下游测试无法通过）。
- CF-05/CF-06：Phase 2 service/client 各自对文件做一致性测试（服务端路由快照测试 / client schema 校验）。
- 契约文件与设计文档冲突时：以本清单行 + 契约文件为准，由编排者裁定并同步设计文档（§3 记录为例）。
