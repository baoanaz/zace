# zace golden eval 报告

- golden：/home/xuwenzheng/2_github/AI/ACE/zace-lane-f/benches/golden/langchain（20 条用例）
- repo：(未绑定仓库：--project-id 模式)
- project：ca2050db0db5b1e2
- 生成时间：2026-09-16 00:26:03
- 预算：maxTokens=10000｜排名口径=ContextPack 装填序｜top-k=10
- 向量通道降级用例数：0

## 总体（正例）

| 指标 | 值 |
|---|---|
| 正例数 | 19 |
| recall@5 | 0.895 |
| recall@10 | 0.947 |
| MRR | 0.798 |
| 负例通过 | 1/1 |

## 按语言（lang）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| en | 4 | 1.000 | 1.000 | 1.000 |
| mixed | 5 | 0.800 | 1.000 | 0.532 |
| zh | 10 | 0.900 | 0.900 | 0.850 |

## 按类别（category）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| behavior | 6 | 1.000 | 1.000 | 1.000 |
| path | 4 | 0.500 | 0.750 | 0.331 |
| symbol | 9 | 1.000 | 1.000 | 0.870 |

## 失败清单（正例）

| id | lang | category | query | 期望 | top-3 |
|---|---|---|---|---|---|
| LC-08 | zh | path | langchain_core 自带的进程内向量库实现是哪个文件、哪个类？ | libs/core/langchain_core/vectorstores/in_memory.py#InMemoryVectorStore | libs/core/README.md:1-52 (🦜🍎️ LangChain Core) / libs/core/langchain_core/__init__.py:1-20 ((module)) / libs/core/langchain_core/load/mapping.py:627-642 (OLD_CORE_NAMESPACES_MAPPING) |

## 负例清单

| id | 通过 | query | answerable | missingEvidence |
|---|---|---|---|---|
| LC-20 | 是 | langchain_core 内置的 SQLite FTS5 全文检索实现在哪个文件？ | False | unresolved_reference, retrieval_truncated |
