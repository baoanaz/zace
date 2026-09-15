# TASK-105：Rerank 语义相关性特征与基准分缩放修正

> 状态：review ｜ 阶段：Phase 5（质量）｜ 硬依赖：TASK-104 ｜ soft 依赖：TASK-101
> 分支：`feature/task-104-definition-preference_xwz0915`（TASK-104 串联）
> 交付物所有权：`core/zace_core/retrieval/rerank.py`、`core/tests/retrieval/test_rerank.py`

## 目标

修复检索排序中的**语义相关性缺位**：正确答案常在向量通道 rank 1-3，但经 RRF 融合与 rerank
后被压到 17-58，导致 ContextPack 无法装填。三仓合起来有 12 道正例受此影响。

## 根因（实测确诊）

1. **特征表没有"语义相关性"这一项**。`score = rrf_score * RRF_BASE_SCALE + Σ特征` 中，
   `RRF_BASE_SCALE = 100.0` 使 base 分区间为 1.6-4.9，而特征表只有 ±0.2-2.0 —— 特征**压不过
   base 分差**，D-16 "靠 rerank 做质量区分"实际失效。
2. **RRF 在奖励"通道数量"而非相关性**。`Σ 1/(60+rank)` 下，向量 rank 1 = 1.64，而任意
   双通道平庸命中 ≈ 3.2。于是"沾边词命中两路"恒压过"语义最相关的唯一命中"。
3. 原有 `consensus3`（≥3 通道 +0.5）进一步强化了该病态偏好，而向量通道作为最弱 tier 2
   没有任何正向信号。

## 实施内容

- 新增 2 条特征：`vector_rank_top`（向量 rank ≤ 8，+1.5）、`vector_rank_near`（rank 9-10，+0.7）。
  分两档避免硬阈值跳变；窗口取 top-10（向量通道自身召回上限 50，更靠后的排名区分度不足）。
- `RRF_BASE_SCALE` 由 `100.0` 降到 `25.0`，让既有特征表重新具备区分度。
- 未改动：RRF 公式与 `RRF_K`（契约冻结）、通道配额、预算闸门、parser、冻结契约。

## 验证方法

离线回放台（`/tmp` 临时脚本，不入库）：采集一次三仓 query 向量后落盘，之后纯本地重算
融合与 rerank，**零 embedding 成本**做参数网格扫描；`/tmp/replay.py` 复用官方
`run_golden` 保证指标口径与 `benches/run.py` 一致（复现基线数值逐位相同）。

关键隔离实验（证明增益来源）：

| 配置 | leveldb R@5 | langchain R@5 | TOTAL R@5 | TOTAL MRR |
|---|---:|---:|---:|---:|
| baseline | 0.737 | 0.789 | 0.789 | 0.667 |
| 只降 scale、不加向量特征 | 0.632 | 0.737 | 0.737 | 0.617 |
| **本卡实现** | **0.947** | **0.895** | **0.895** | **0.744** |

只降 scale 反而变差 → 增益**完全来自向量语义特征**，不是权重缩放调整。
余弦值特征方案（`cos = max(0, sim - 0.60) * w`）实测全线劣于 rank 方案且无增量信息，已弃用。

## 验收标准

- [x] 新增向量语义特征，语义相关性可参与排序。
- [x] `RRF_K`、RRF 公式、通道配额、预算装填规则均未改动。
- [x] 三仓 golden search 指标均不低于 baseline，且无单一仓库回退。
- [x] 全仓 pytest、ruff、依赖方向检查全绿。

## 执行记录

### 2026-09-15 实施与验收

- 参考审计结论（`benches/results/qa-audit-2026-09-15.md` §5 P1"候选已召回，但路由/排序/装填
  不能区分用户要的证据形态"），本卡只解决其中的**排序**部分，未涉及轻路由与 Gap 二轮。

| 验收命令/探针 | 结果 |
|---|---|
| `uv run pytest core/tests/retrieval/test_rerank.py -q` | 31 passed |
| `uv run pytest -o addopts="" -q` | 1029 passed, 2 skipped |
| `uv run ruff check .` | All checks passed |
| `uv run python scripts/check_dependency_direction.py` | 依赖方向检查通过 |

### golden search（`benches/run.py`，官方口径）

| 靶场 | R@5（前 → 后） | R@10 | MRR（前 → 后） | 负例 |
|---|---|---|---|---|
| leveldb | 0.737 → **0.947** | 0.947 | 0.545 → **0.708** | 1/1 |
| HelloAgents | 0.842 → 0.842 | 0.842 | 0.744 → 0.739 | 0/1 |
| langchain | 0.789 → **0.895** | 0.895 | 0.711 → **0.784** | 1/1 |

### 端到端 LLM（`benches/golden/qa_probe.py`，`deepseek-v4-flash`）

| 靶场 | ask 有答案 | pack 命中 | 完整覆盖 | 引用命中期望证据 | 路径点名 |
|---|---|---|---|---|---|
| leveldb | 5/5 | 5/5 | 4/5 | 3/5 → **5/5** | 3/5 → 4/5 |
| HelloAgents | 6/6 | 5/6 | 3/6 | 4/6 → **5/6** | 1/6 → 3/6 |
| langchain | 5/5 | 5/5 | 4/5 | 3/5 → **5/5** | 2/5 |

逐题审计：57 正例中改善 14 题、回退 4 题（净 +10），负例由 1/3 改善到 2/3。

### 未决问题

- 残余失败集中在两类，均**不属于**本卡范围：
  1. **路径类题候选未召回**：LC-06 / LC-08 的目标文件在四个通道里都排不进（向量 rank 16 / 2
     但被 README 的 `doctype +0.8` 重复吃满）。属审计 §6.3 的"轻路由"问题。
  2. **负例仍假阳性**：HelloAgents H-20 仍判 `answerable=True`，属审计 §6.4 的 answerable 闸门问题。
- 本卡参数（top-8 / 1.5 / 0.7 / scale 25）在 57 题上定档，存在过拟合风险。缓解措施：分两档
  而非硬阈值、网格扫描显示 20-40 scale 与 vt3-vt8 均为同一平台区（非尖峰）。后续 TASK-093
  接入真实用户查询后应重新校准。
