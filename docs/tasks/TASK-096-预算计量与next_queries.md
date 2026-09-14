# TASK-096：预算计量修复 + next_queries 生成口径修正

> 状态：pending ｜ 阶段：Phase 3（M2c）｜ 硬依赖：无 ｜ soft 依赖：TASK-095（同改 assembly.py，建议串行）
> 建议分支：`feature/task-096-budget-nextq_<你的缩写><MMDD>`
> 交付物所有权：
> - `core/zace_core/contextpack/assembly.py`（token 计量、next_queries 生成）
> - `core/tests/contextpack/`（新增/更新断言）
>
> 清单外文件不得改。**特别提醒**：
> - **不得改** `docs/contracts/**`（CF-03 冻结）；
> - **不得改** `retrieval/rerank.py` 特征分值（R30 冻结）；
> - **不得改** `contextpack/render.py`（TASK-095 的领地，若并行则避免同文件）。

## 背景（编排者在真实仓库上的实测发现两个真实缺陷）

靶场：`/home/xuwenzheng/4_AIBOX/gitlab/minicpm/cockpit-agents-py`
（287 文件 / 3416 chunks；gitlab 车载 Agent 服务；索引数据根 `~/.zace/cockpit-agents`）

### 缺陷 1：预算控制失效，实际返回超预算约 30%（🔴 真实缺陷）

实测（同一查询，不同 `max_tokens`）：

| `max_tokens` 参数 | 实际返回 | 超出 |
|---|---|---|
| 3,000 | 3,959 token | **+32%** |
| 10,000 | 12,899 token | **+29%** |
| 20,000 | 25,382 token | **+27%** |

**根因（已定位）**：

```python
# core/zace_core/contextpack/assembly.py
@dataclass(slots=True)
class _Slot:
    @property
    def tokens(self) -> int:
        return estimate_tokens(self.item.content)   # ← 只算 content！
```

装填主循环用 `slot.tokens` 做预算判定，但**渲染时每条证据还会输出**：

| 输出项 | 实测占比（10K 预算的一次真实查询） |
|---|---|
| 证据 header（`[E*] xxx — path:line`） | 6.0% |
| **reason 行** | **5.9%** |
| 节标题等 | 1.4% |
| 源码内容 | 86.8% |

**框架开销合计 16%**，全部不计入预算。

**叠加第二个偏差**：`estimate_tokens` 用 `ceil(len(text)/4)`，但
**中文实际约 `chars/1.5`**（一个汉字通常 1-2 token）。该仓库的查询与注释含大量中文，
`reason` 行也是中英混合。

### 缺陷 2：`next_queries` 从 top-3 候选生成，继承了排序问题（🟡 质量问题）

实测输出（查询「Runtime 的输入准入是怎么实现的？」）：

```
### Suggested Next Queries
- test_user_input_reaches_runtime_without_voice_invocation_binding 的调用方有哪些   ← 测试函数
- docs/internal-design.md 里还有哪些与查询相关的符号
- 仓库内部设计与源码分层 > 五、一次输入如何执行 > 输入准入 对应的实现代码在哪里
```

**当前实现**：

```python
def _next_queries(pool, evidence, docs):
    top = list(pool[:3])                                   # ← 只看池内前 3 条
    named = next((c for c in top if c.symbol_fqn and c.kind != "spec"), None)
    if named is not None:
        queries.append(f"{named.symbol_fqn.rsplit('.', 1)[-1]} 的调用方有哪些")
    ...
```

**三处问题**：
1. 生成源是"池里前 3 条**符号**"——若 top-1 是测试函数，就建议查测试函数；
2. 模板固定 3 种，与**实际缺口**无关；
3. **`answerable=true` 时也生成**——证据已足够，还建议"换个方式再问"是噪音。

**用户拍板口径**（2026-09-14）：
> 改为从缺失信号出发（`missing_evidence` 里的符号），而不是从 top-3 符号出发；
> 只在 `answerable=false` 时生成（证据够了就别打扰）。

## 目标

1. **修预算计量**——让 `max_tokens` 真正生效（±10% 以内）；
2. **改 `next_queries` 生成口径**——从缺口出发 + 仅 `answerable=false` 时生成。

## §A 预算计量修复

### §A-1 把框架开销计入预算

在装填时，`_Slot.tokens` 需包含该条证据的**全部渲染开销**（header + reason + 行号前缀），
而不只是 `content`。建议实现方式（**你评估后选一个并说明理由**）：

| 方案 | 做法 | 权衡 |
|---|---|---|
| A. `_Slot.tokens` 直接返回完整渲染 token | 复用 render 的 header/reason 格式计算 | 最准；但 coupling 到渲染格式 |
| B. 加固定系数 | `int(content_tokens * 1.20)` | 简单；但不精确（长 header 会低估） |
| C. 抽出共享的"渲染开销估算"函数 | render 与 assembly 各调一次 | 需动 render.py（**属 TASK-095 领地**，若并行则协调） |

**倾向 A 或 C**：B 的系数难以论证，且不同查询的 header/reason 长度差异大
（实测单条 reason 从 40 到 150 字符不等）。

### §A-2 修正中英混合的 token 估算

`estimate_tokens` 当前是 `ceil(chars/4)`。建议改为**按字符类别加权**：

```python
def estimate_tokens(text: str) -> int:
    """chars/4 近似（英文）+ 中日韩字符按 ~1.5 chars/token 计。"""
    cjk = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff' or '\u3040' <= ch <= '\u30ff')
    other = len(text) - cjk
    return max(1, math.ceil(cjk / 1.5 + other / 4))
```

**要求**：
- 该函数是 `contextpack` 的公开导出（`__all__` 已含 `estimate_tokens`），
  改语义要在 docstring 与执行记录里**明确标注**（有测试断言依赖它）；
- 若你认为精确 tokenizer 更合适（如 `tiktoken`），**先评估依赖成本**再决定——
  项目设计明确"不引入 tokenizer 依赖"（Module/03 §2 要点 3），如需变更要走契约流程。

### §A-3 验收口径

修复后要求：`max_tokens=10000` 的实际返回 **≤ 11000 token**（±10% 容差）。
**必须贴修复前后的实测对照**。

## §B `next_queries` 生成口径修正

### §B-1 从缺口出发（而非 top-3 符号）

**新的生成策略**（**确定性、无 LLM**）：

| 缺口类型（`missing_evidence.code`） | 生成的 next_query |
|---|---|
| `unresolved_reference` | `{symbol} 的调用方有哪些`（取 message 里提到的符号） |
| `stale_doc_reference` | `{symbol} 现在在哪里实现`（文档引用了已删除的符号 → 问新位置） |
| `graph_boundary` | `{symbol} 的调用链完整路径` |
| `retrieval_truncated` | 不生成（这是"预算不够"，改问也帮不上） |
| `symbol_ambiguous` | `{symbol_a} 还是 {symbol_b}`（消歧） |
| `no_context_match` | 无缺口可依据 → 退回"用文件名/路径构造"的兜底（保留现有逻辑） |

**要求**：
- 生成源优先用 `missing_evidence`，**不再从 `pool[:3]` 取符号**；
- 兜底逻辑（`if not queries and evidence`）保留；
- 最多 3 条，去重。

### §B-2 仅 `answerable=false` 时生成

`pack.next_queries` 在 `answerable=true` 时应为**空列表**。

**注意**：`render_markdown` 的行为是"空列表 → 整节不渲染"（TASK-087 已实现），
所以这一条改完，`answerable=true` 的返回里就不会再有 `### Suggested Next Queries` 节。

**契约影响**：CF-03 的 `nextQueries` 字段**保留**（只是内容可能为空数组）——
**不要删字段**。

## 验收标准（DoD）

- [ ] `uv run pytest core/tests/contextpack -q` 全绿，**必须覆盖**：
  - [ ] **预算**：构造一个"框架开销占比很高"的 pack（如很多短 chunk），断言
        `used_tokens` 包含了 header/reason 开销（修复前必然失败）；
  - [ ] **中英混合估算**：中文文本的 `estimate_tokens` 显著高于 `chars/4`；
  - [ ] **next_queries 从缺口出发**：构造带 `unresolved_reference` 的 pack →
        `next_queries` 包含该符号（而非 pool 的 top-3 符号）；
  - [ ] **`answerable=true` → `next_queries == []`**；
  - [ ] `answerable=false` 时仍生成（不误伤）；
  - [ ] `retrieval_truncated` 不生成查询。
- [ ] **真实仓库实测**（贴真实输出，两个缺陷各一份对照）：
      - 修复前后 `max_tokens=10000` 的实际 token 数（预期 12899 → ≤11000）；
      - 修复前后同一查询的 `Suggested Next Queries` 内容对比。
- [ ] 基线三条命令全绿：`uv run ruff check .`、
      `uv run python scripts/check_dependency_direction.py`、`uv run pytest -o addopts="" -q`
- [ ] 任务卡"执行记录"已回填；任务板状态改为 `review`。

## 明确不做

- **不改** CF-03 的字段集（`nextQueries` 字段保留，只改内容）；
- **不引入** tokenizer 依赖（除非你先论证并走契约流程）；
- **不改** rerank 特征分值（R30 冻结）；
- **不改** `render.py`（TASK-095 领地；若必须改，**先在执行记录里说明并等编排者确认**）；
- 不做 `next_queries` 的"有效性评估"（那是 TASK-091/093 的评测侧工作）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板。**必须包含**：

- §A 修复方案的**选择理由**（三个方案里为什么选它）；
- **修复前后实测对照**（token 数 + next_queries 内容）；
- §A-2 的 `estimate_tokens` 语义变更说明（含对既有测试的影响）。

## 执行记录

（实施 AI 在此填写。）
