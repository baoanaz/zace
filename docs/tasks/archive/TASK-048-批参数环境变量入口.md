# TASK-048：批参数环境变量入口（`EMBED_BATCH_TOKEN_BUDGET`）

> 状态：done（2026-09-13 编排者直接完成，commit `42587cf`）｜ 阶段：Phase 2（M2b / W6 收口）
> 归属：**由编排者实现**（属 TASK-046 的漏接项，非独立实现卡）

## 背景（TASK-046 的遗留缺口）

TASK-046 §D 引入了 `OpenAiCompatibleEmbeddingProvider(batch_token_budget=...)` 构造参数，
但 **`EmbeddingConfig.from_env` 没有读任何对应环境变量**，导致：

- 该参数**只能通过代码传参**，用户无法从配置调整；
- 编排者在性能标定时设了 `EMBED_BATCH_TOKEN_BUDGET=65536` 跑全量索引，
  结果**耗时与默认完全相同**（231s vs 230.9s）——因为环境变量被静默忽略。

这属于"配置入口缺失"，不是设计变更。

## 交付内容

1. `EmbeddingConfig` 新增字段 `batch_token_budget: int | None = None`；
2. `from_env` 读取 `EMBED_BATCH_TOKEN_BUDGET`（非法值报错，`< 1` 报错）；
3. `create_provider` 的 API 分支把该值传给 provider（**None 时不传**，保持 provider 自带默认）；
4. 测试 3 条：
   - env 解析生效；
   - 未配置时保持 `None`（不得写成 0），且显式配置能到达 provider（`batch_token_budget == 24576`）；
   - 非正值报 `EmbeddingConfigError`。

## 验收结果

```console
$ uv run pytest core/tests/embedding -o addopts="" -q
102 passed, 1 skipped

$ uv run pytest -o addopts="" -q          # 全仓
727 passed, 2 skipped

$ uv run ruff check .
All checks passed!
$ uv run python scripts/check_dependency_direction.py
依赖方向检查通过（core 纯库 / service 不上探）。
```

实测配置生效：

```text
EmbeddingConfig.from_env({... EMBED_BATCH_TOKEN_BUDGET=24576, EMBED_BATCH_SIZE=128})
→ batch_token_budget=24576, batch_size=128
provider.batch_token_budget == 24576   （默认应为 8192）
```

## 重要的实测结论（写在卡内以免误用）

**调大该参数在本机没有稳定收益，且可能更快触发限流**：

| 实验 | 结果 |
|---|---|
| 环境变量调参跑全量（硅基流动） | 231s，与默认 230.9s 无差别（**当时变量未生效**） |
| 进程内传参（budget=65536/bs=256） | **直接 429 失败** |
| 固定 2000 条样本、只改批大小 | 93.6 → 122.8 chunk/s（**1.31×**，非理论推算的 4×） |

**结论**：真实瓶颈是配额与响应体传输（详见 `benches/results/index-performance-w6.md` §4.4、
`docs/tasks/TASK-049-embedding架构整理.md` §8）。本卡的默认值**保持现状**，
调参能力留给 TASK-049 的"按模型配置"体系使用。

## 未决问题

无（并发能力的落地归 TASK-049）。

## 执行记录

**日期**：2026-09-13 ｜ **提交**：`42587cf` ｜ **实施**：编排者（非子 AI）

- 交付：`core/zace_core/embedding/factory.py`（+字段/+env/+透传）、`core/tests/embedding/test_factory.py`（+3 测试）
- 基线：727 passed / ruff clean / 依赖方向通过
- 偏差：无（补齐 TASK-046 的配置入口，未改任何契约与默认值）
