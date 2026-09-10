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

## 2. 跨文件不变式（写代码时不得违反）

1. `chunk_id = {path}:{symbol_fqn}:{start_line}`（spec 块的 `symbol_fqn = heading_path`），代内唯一即可（D-04）。
2. `blob_hash / file content_hash / chunk content_hash` 三者用途互不可替代（D-43 / CF-02）。
3. `symbol_kind ∈ {function, method, class_skeleton, spec_block, fallback_block, ...}`；spec 块双表同 id（见 §3-2）。
4. `evidenceTier` 是元数据 + 装填资格线 + rerank 特征，**不是 ORDER BY**（D-17）。
5. `evidence` 与 `docs` 共用 `E` 编号空间，`flows` 用 `F` 编号（D-21）。
6. RRF `K=60` 且融合层不加通道权重（D-16）。
7. `spec_references.provenance` 永远 `inferred`（D-06）。
8. 所有面向 agent 的时间/预算语义：`freshness` 如实报告，缺证据必须有 `missingEvidence`（D-30、A5）。

## 3. 规划期裁定（2026-09-10，编排者；需在对应 Module 文档下次修订时回记）

1. **chunks_fts 采用独立 FTS5 表（非 external content）**：D-20/D-45 要求索引侧写入预分词文本，与 external-content 直读 `chunks.content` 冲突；写入器与 chunks 同事务维护，渲染一律用原文。DDL 见 CF-01 文件头。
2. **SpecBlock 双表同 id**：检索单元同时写入 `chunks(symbol_kind='spec_block')` 与 `spec_blocks`（结构字段：doctype/heading_path/code_fences）；保证单一 RRF 池、单一向量表、单一 E 编号空间（D-42 的"不新增检索通道"由此落地）。
3. **batch-upload 的 blob 内容编码 = base64（`contentB64`）**：JSON 传输二进制安全；gzip 是否叠加留待 Phase 2 实测（Module/05 §9-2 开放问题不变）。
4. **MCP 工具 description 文案可由 client 任务打磨，但 schema（名字/参数/类型/默认值/上限）冻结**（CF-06 文件头声明）。

## 4. 契约的验证方式（集成保障）

- CF-01：TASK-001 的测试必须真实执行该 SQL 建库；DDL 与测试一起通过才算契约落地。
- CF-03：TASK-012 必须对产出 JSON 做 schema 校验（`jsonschema` 校验器进 core dev 依赖，TASK-012 卡内落地）。
- CF-04/CF-07/CF-08：Python 类型层面由导入即用保证；签名变化即 CI 失败（下游测试无法通过）。
- CF-05/CF-06：Phase 2 service/client 各自对文件做一致性测试（服务端路由快照测试 / client schema 校验）。
- 契约文件与设计文档冲突时：以本清单行 + 契约文件为准，由编排者裁定并同步设计文档（§3 记录为例）。
