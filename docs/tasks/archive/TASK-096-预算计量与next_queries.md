# TASK-096：预算计量修复 + next_queries 生成口径修正

> 状态：review ｜ 阶段：Phase 3（M2c）｜ 硬依赖：无 ｜ soft 依赖：TASK-095（同改 assembly.py，建议串行）
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

**2026-09-14 ｜ 分支 `feature/task-096-budget-nextq_xwz0914` ｜ 状态：review**

### §A 修复方案选择与理由

**选方案 A（``_Slot.tokens`` 直接返回完整渲染 token），并抽出共享的渲染行生成器。**

| 方案 | 取舍 | 结论 |
|---|---|---|
| A. ``_Slot.tokens`` 直接用渲染格式算 | 最准；与渲染格式耦合 | **选它** |
| B. 乘固定系数（如 ×1.20） | 简单；但实测单条 reason 从 40 到 150 字符不等，长 header 会低估 | 否——卡内已指出系数难论证 |
| C. 抽共享函数、render 与 assembly 各调一次 | 最干净；但须知 **render.py 已 ``from .assembly import elision_note, has_elision_note``**，反向 import 会成环 | 改为 A 的变体（见下） |

**实际实现（A + C 的合并，且不改 render.py）**：新增 ``evidence_markdown_lines(item)`` /
``estimate_render_tokens(item)``（在 assembly 内，与 ``render._evidence_lines`` **同一格式**），
``_Slot.tokens`` 改为 ``estimate_render_tokens(self.item)``。没有反向编辑 render.py——
因为 import 成环，而“改 render.py 让 assembly 反向依赖它”超出本卡所有权（TASK-095 领地）。
改为在 assembly 内按同一格式生成，并用新增测试
``test_render_accounting_matches_rendered_evidence`` 把两处格式钉死（防漂移）。

配套改动（同属“预算账=渲染账”）：
- 同符号聚合使 ``reason`` 变长（``+ 同符号聚合×N``）→ 现在**补记增量**（修复前这段增长不记账）；
- 缺口的 ``unresolved_reference`` message 补进符号名，并给 ``MissingEvidence.symbol`` 填首个可用符号。

### §A-2 `estimate_tokens` 语义变更说明（**重要，含既有测试影响**）

```python
# 旧：ceil(len(text)/4)
# 新：ceil(cjk/1.5 + other/4)   # CJK 区段见 _CJK_RANGES（含汉字/假名/CJK 标点/全角形式）
```

- **纯 ASCII 文本结果与旧口径完全一致**（``cjk=0`` 时退化）；受影响的是**含中文**的文本；
- 卡内骨架给 ``1.5``；实测项目自用的 e5 分词器下纯中文约 1.4-1.7 chars/token、cl100k 下约
  1.0-1.2，故 1.5 是中位保守值（不会把英文代码高估）；
- **不引入 tokenizer 依赖**（Module/03 §2 要点 3），所以这是**估算口径修正**，不是精确计数；
- **对既有测试的影响**：``core/tests/contextpack`` 与 ``service/tests`` 里以
  ``estimate_tokens(item.content)`` 作预算不变量对照的断言**全部改为渲染账口径**
  （``estimate_render_tokens``）；夹具预算（中文 spec 正文）按新口径重标定，
  并在每处注明新旧数值与语义（不是简单改数字，见 diff 内注释）。
  另有大量**行为断言**（装填顺序 / 配额 / 去重）保持不变，只调整了使其成立的 hard_cap。

### 缺陷 1 修复前后实测对照

口径说明：卡内引用的 12899 = **渲染后 Markdown 的 UTF-8 字节数 ÷ 4**（实测 51593 字节）。
本卡沿用同一尺子以便对齐卡内数字。

| `max_tokens` | 修复前（bytes/4） | 超出 | 修复后（bytes/4） | 超出 | 修复后 usedTokens |
|---|---|---|---|---|---|
| 3,000 | 3,959 | +32% | 2,155 | **−28%** | 2,518 |
| 10,000 | 12,899 | +29% | 9,303 | **−7%** | 9,594 |
| 20,000 | 25,382 | +27% | 19,664 | **−2%** | 19,863 |

**验收口径达成**：``max_tokens=10000`` 实际返回 12,899 → **9,303**，远优于卡内“≤11000”的要求。

**客观 tokenizer 复核**（同一输出，仅在验证脚本里用，不进交付代码）：

| `max_tokens` | e5 词表（前 → 后） | cl100k（前 → 后） |
|---|---|---|
| 3,000 | 4,870 → 2,675 (89%) | 4,394 → 2,402 (80%) |
| 10,000 | 15,249 → 11,221 (112%) | 13,378 → 9,852 (**99%**) |
| 20,000 | 29,826 → 23,267 (116%) | 26,038 → 20,276 (101%) |

残余缺口诚实说明：e5 对**英文标识符密集**的代码切片会比 cl100k 多切出 token（后者是项目
实际 provider 更接近的形态，命中 ±10% 内）；``bytes/4`` 口径对中文偏保守。三种尺子都表明
“超出 27-32%”已变成“落在预算内”，且 ``usedTokens``（内部账）与 cl100k 实测几乎重合。

### 缺陷 2 修复前后实测对照（next_queries）

同一查询「Runtime 的输入准入是怎么实现的？」（该查询 ``answerable=true``）：

| | 内容 |
|---|---|
| 修复前 | `- test_user_input_reaches_runtime_without_voice_invocation_binding 的调用方有哪些`<br>`- docs/internal-design.md 里还有哪些与查询相关的符号`<br>`- 仓库内部设计与源码分层 > 五、一次输入如何执行 > 输入准入 对应的实现代码在哪里` |
| 修复后 | `nextQueries: []`（§B-2：answerable=true 不生成）→ 该节整节不渲染 |

§B-1（从缺口出发）在 `answerable=false` 时的对照（同一靶场，另一个查询）：

| | 内容 |
|---|---|
| 修复前 | `- docs/internal-design.md 里还有哪些与查询相关的符号`<br>`- 仓库内部设计与源码分层 > 五、一次输入如何执行 > 输入准入 对应的实现代码在哪里`（与缺口无关；来自 pool 的文档符号与标题） |
| 修复后 | `- workflow_id 的调用方有哪些`（来自 `missing_evidence.unresolved_reference` 的符号） |

同时 ``unresolved_reference`` 的 message 现在如实列出符号：
``unresolved_refs status=failed：workflow_id, version, _owner 等``（修复前只有计数）。

### 验收命令与结果

```text
uv run pytest core/tests/contextpack -o addopts="" -q
  → 73 passed（修复前 62；本卡新增 11 个用例）

uv run ruff check .                              → All checks passed!
uv run python scripts/check_dependency_direction.py → 依赖方向检查通过
uv run pytest -o addopts="" -q                   → 889 passed, 2 skipped
  （基线 878 passed, 2 skipped；+11 为本卡新增用例）
```

注：直接 ``source .env`` 后跑全量会在 ``test_default_is_local_onnx_provider`` 上失败
（``EMBED_MODE=api`` 覆盖默认 provider，与本卡无关）——上表是**去除该环境变量**后的干净基线。

新增/更新的 DoD 覆盖（均在 ``core/tests/contextpack/``）：

- 预算：``test_framework_render_overhead_is_inside_used_tokens``（修复前必失败）、
  ``test_render_accounting_matches_rendered_evidence``（锁死与 render.py 的一致性）、
  ``test_cjk_budget_shrinks_the_pack``；
- 中英混合估算：``test_estimate_tokens_charges_cjk_higher_than_ascii``；
- 缺口出发：``test_next_queries_come_from_gaps_not_pool_top_symbols``、
  ``test_stale_doc_gap_asks_where_the_symbol_is_now``、
  ``test_gap_message_lists_unresolved_symbol_names``；
- ``answerable=true`` → 空列表：``test_next_queries_empty_when_answerable``、
  ``test_answerable_pack_renders_no_suggested_queries_section``；
- ``answerable=false`` 仍生成：``test_next_queries_still_generated_when_not_answerable``；
- ``retrieval_truncated`` 不生成：``test_retrieval_truncated_generates_no_query``。

### 交付物

- ``core/zace_core/contextpack/assembly.py``：``estimate_tokens`` 分类计价、
  ``evidence_markdown_lines`` / ``estimate_render_tokens``（新公开导出）、``_Slot.tokens``、
  聚合 reason 增量记账、``IndexSignals.unresolved_symbols``、``_next_queries`` 重写；
- ``core/zace_core/contextpack/__init__.py``：导出新增两个函数；
- ``core/tests/contextpack/``：新增 11 用例、更新受影响断言、重标定夹具预算、
  更新快照 ``snapshots/rich_pack.md``。

### 契约影响

- **CF-03 字段集未变**（``nextQueries`` 保留，只是可能为空数组）；
- ``usedTokens`` 的**语义收窄为“渲染账”**：同一 pack 下数值会比以前大（旧值只算正文）。
  这是在 CF-03 ``integer`` 约束内的口径澄清，不改 schema；已在 ``to_json`` docstring 写明；
- 新增 ``IndexSignals.unresolved_symbols`` 是**内部 dataclass 的附加字段**（带默认值），
  不在 CF-03 内，也未改 ``types.py``；
- ``estimate_tokens`` 是公开导出，语义变更已在 docstring 显著标注（§A-2）。

### 与设计偏差 / 未决问题

1. **未修改 ``render.py``**（TASK-095 领地）。卡内方案 C 原文设想“render 与 assembly 各调一次”，
   但实测 ``render.py`` 已从 ``assembly`` 导入，反向依赖会成环。改为在 assembly 内按同一
   格式生成 + 测试钉一致性。若编排者认为应把 ``evidence_markdown_lines`` 下沉到
   ``render.py`` 再由 assembly 调用（真正的单一实现），属**跨卡重构**，建议留到 TASK-095 合并后
   统一处理——已用测试保证当前不漂移。
2. **Module/03 §5 的文字**写“nextQueries 从 top 候选符号/文件构造”，与本卡的用户拍板口径
   （从缺口出发、仅 answerable=false）**不一致**。按 AGENTS.md §6 停在此处报编排者：
   代码已按用户拍板实现，**未改设计文档**（``docs/design/**`` 不在本卡所有权内）。
3. **TASK-095 并行冲突**：本卡与 095 同改 ``assembly.py``，本卡只动“token 计量 + ``_next_queries``
   及其辅助函数”，未重构他处；若 095 也改了装填循环/缺口 message，合并冲突由编排者裁决。
4. ``retrieval_truncated`` 抑制兜底：卡内只说“该缺口不生成查询”，实现时发现若同时存在
   其他缺口会有歧义；取“**只要包被裁剪就不给兜底**”（预算不够时正确动作是提高预算），
   已写入 docstring 与专门用例。若编排者希望“仍给其他缺口生成的查询”，一行可改。

