# zace golden eval 报告

- golden：/home/xuwenzheng/2_github/AI/ACE/zace-lane-f/benches/golden/leveldb（20 条用例）
- repo：(未绑定仓库：--project-id 模式)
- project：3ed886ce58bc0e47
- 生成时间：2026-09-16 00:25:03
- 预算：maxTokens=10000｜排名口径=ContextPack 装填序｜top-k=10
- 向量通道降级用例数：0

## 总体（正例）

| 指标 | 值 |
|---|---|
| 正例数 | 19 |
| recall@5 | 1.000 |
| recall@10 | 1.000 |
| MRR | 0.721 |
| 负例通过 | 1/1 |

## 按语言（lang）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| en | 4 | 1.000 | 1.000 | 0.688 |
| mixed | 5 | 1.000 | 1.000 | 0.733 |
| zh | 10 | 1.000 | 1.000 | 0.728 |

## 按类别（category）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| behavior | 6 | 1.000 | 1.000 | 0.792 |
| path | 2 | 1.000 | 1.000 | 0.750 |
| spec | 3 | 1.000 | 1.000 | 0.778 |
| symbol | 8 | 1.000 | 1.000 | 0.640 |

## 失败清单（正例）

（无）

## 负例清单

| id | 通过 | query | answerable | missingEvidence |
|---|---|---|---|---|
| L-20 | 是 | leveldb 的 Transaction（事务）类声明在哪个头文件里？ | False | unresolved_reference, retrieval_truncated |
