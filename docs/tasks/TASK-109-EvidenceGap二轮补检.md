# TASK-109：Evidence-Gap 驱动的二轮补检（D-19 落地）

> 状态：pending（**下一轮重点**）｜ 阶段：Phase 5+（质量）
> 硬依赖：TASK-108（已完成，提供基线）｜ soft 依赖：TASK-110（专项测试项）
> 交付物所有权：
> - `core/zace_core/retrieval/gap.py`（**新建**）
> - `core/zace_core/engine.py`（接线）
> - `core/tests/retrieval/test_gap.py`（**新建**）
>
> **本卡开工前请先读**：`docs/handbook/部署指南.md` 第三章（基准环境）——改检索代码必须跑基准。

## 一句话

当首轮召回的**候选池里已经有目标**、但它**没进 ContextPack**（或压根没进池）时，
用**确定性的定向补检**把缺口补上。**不预猜意图，不重复盲搜，不用 LLM。**

## 为什么需要它（真实失败驱动，非设计推演）

2026-09-15 用真实 MCP 客户端对 `cockpit-agents-py` 做 6 次调用并逐项对照源码，
暴露同一类系统性缺陷：**候选已正确索引，但没被召回/没进包**。

### 可复现证据（当前代码状态下实测，2026-09-15）

**用例 A（`cockpit-0035`，召回覆盖不足）**

```text
查询：能力网关 CapabilityGateway 如何实现幂等（idempotency）、参数验证（verification）、
      重试（retry）与 UNKNOWN 终态？
```

| 目标 | 索引状态 | 候选池排名 | 分数 | 是否进包 |
|---|---|---:|---:|---|
| `CapabilityGateway._reserve_idempotency` | ✅ 已索引（gateway.py:336） | 46 | 0.31 | ❌ |
| `CapabilityGateway._should_retry` | ✅ 已索引（gateway.py:487） | **不在池** | — | ❌ |
| `CapabilityGateway._normalize` | ✅ 已索引（gateway.py:442） | 49 | 0.30 | ❌ |
| `CapabilityGateway`（类骨架） | ✅ | 5 | 1.61 | ✅ |

**关键观察**：**类的骨架进了包，但它下面的方法没进**——而用户问的正是那些方法的行为。
类骨架（rank 5）与它的方法（rank 46/49）之间差 40 多名，说明"类被召回"没有帮助"方法被召回"。

**用例 B（`cockpit-0033`，调用链断裂）**

查询"普通 USER_REQUEST 从准入到执行 Agent 的路由链路"，目标是
`runtime.py`（`Runtime.admit`）→ `dispatcher.py`（`InputDispatcher`）→ `intent_router.py`。
实测：`intent_router.py` 进包（rank 靠前），但 `runtime.py`/`dispatcher.py` 的首个候选
只到 **rank 19**，包内没有完整链路。

### 已排除的可能（不要重复这些方向）

| 假设 | 实测结论 |
|---|---|
| 索引缺失 | ❌ 所有目标都正确索引（`gateway.py` 37 chunks 齐全） |
| 排序错误 | ❌ 不是排序问题——目标排在 rank 46-49，是**没被召回** |
| 预算截断 | ❌ 见下 |
| 测试夹具挤占 | ⚠️ TASK-108 已修（包内测试 20→1 条），但**目标仍未进包** |
| 阈值过严 | ⚠️ TASK-108 已把 0.50→0.40，仍不够（目标分 0.30） |

**TASK-108 的对照实验（很重要）**：测试夹具常态抑制让包内测试从 20 条降到 1 条、
token 从 9912 降到 4698，但 `gateway.py` 的方法**仍然没进包**。
这证明**"降噪"与"补召回"是两件独立的事**，后者必须靠本卡。

## 目标

落地 `docs/design/Module/02-检索策略.md` §4.7 的 **G1/G2/G3**，
让 `search_context` 与 `ask_project` **共用**同一条管线（D-10：不分叉成两套代码）。

## 输入与参考

| 类别 | 位置 |
|---|---|
| 设计规则表 | `docs/design/Module/02-检索策略.md` §4.7（G1-G5）、§4.8（共享管线） |
| 决策依据 | `docs/design/INDEX.md` D-19（Gap 二轮）、D-10（共用管线）、D-18（图双角色） |
| 复用能力 | `core/zace_core/retrieval/expand.py`（图扩展，**复用不新写**） |
| 冻结契约 | `docs/contracts/**`、`core/zace_core/types.py`、`interfaces.py` |
| 基准环境 | `docs/handbook/部署指南.md` 第三章 |
| 回归用例 | `benches/golden/cockpit-agents-py/`（38 题，含本卡要修的 `cockpit-0033`/`0035`） |

## 设计要点

### 1. 只做 G1/G2/G3

| 规则 | 本卡处理 | 说明 |
|---|---|---|
| **G1** 调用链断裂 | ✅ 核心 | 2-hop 定向图查询，只从 top 种子出发 |
| **G2** 设计意图缺失 | ✅ | spec evidence=0 时用首轮代码符号反查 `spec_references` |
| **G3** 无共识结果 | ✅ | top10 全单通道时，用 top3 的符号名/文件名构造扩展查询 |
| G4 文档过时 | ❌ 已有 | TASK-096 已实现（进 MissingEvidence，不触发二轮） |
| G5 预算富余 | ❌ 不适用 | 属组装层；TASK-108 已把闸门改为优先级语义 |

### 2. 针对本卡证据的新增候选规则（**需评审**）

上面的实测暴露了一个 §4.7 未覆盖的缺口：**"类骨架进包、其方法未进包"**。
建议新增一条规则（暂称 **G6**）：

> **G6 容器-成员断层**：包内已有某 class 的骨架（`class_skeleton`），但该 class
> 在候选池里的成员方法（同文件、行号落在类区间内）全部未进包，且查询含行为类词
> （"如何实现/怎么保证/流程"） → 对**该 class 在候选池里的成员**做一次定向补检。

判据必须确定性（不用 LLM），且**只在池里已存在成员时触发**（否则退化成盲搜）。

### 3. 二轮纪律（设计已定，不得放宽）

- 最多 **1 次**迭代；
- 二轮只补缺口对应通道（G1 只走图、G3 只重召回），**不做全量重跑**；
- 二轮结果**进同一 rerank**，不直接插队（否则破坏 D-16 的排序唯一性）；
- 全部 deterministic，**不引入 LLM**（R1 延迟预算）。

### 4. 与预算闸门的关系（TASK-108 的教训）

二轮候选进池后仍走同一套 `score_floor` 与预算装填。
**不得因为"是二轮来的"就绕过闸门**——TASK-108 实测过"不丢候选、预算允许就装"的后果：
包被填满 10K，但后半是 `0.00`/`-0.24` 的噪音（tier3 固定分 0.70 与负分候选）。

> 但要处理本卡的具体矛盾：目标方法分 **0.30** 而闸门是 `top1×0.40`。
> 可能的解法（需评审）：二轮候选用**独立的小预算**（如 ≤15% hard_cap），
> 且必须标记来源（`reason` 里写明"gap 补检"），让 Agent 能识别。

### 5. search 与 ask 都要有

- `search_context`：Fast 也触发（成本是本地查询，非 LLM）；
- `ask_project`：Deep 触发，效果叠加；
- 分叉点必须在**组装之后**（D-10）。

## 施工步骤（建议顺序）

1. **先写可复现的失败断言**：在 `core/tests/retrieval/test_gap.py` 里用
   `benches/golden/cockpit-agents-py` 的两题做集成测试（或先写最小单测）。
2. 实现 `gap.py`：纯函数，输入首轮候选池 + pack，输出"缺口类型 + 补检计划"。
   **不碰 I/O**（图查询由调用方执行）。
3. 在 `engine.py` 的 `search_with_trace` 里接线：一轮 → gap 检查 → 二轮 → 合并 → rerank → assemble。
4. 跑基准（三仓 + cockpit），确认无回退。
5. 回填本卡执行记录。

## 验收标准

- [ ] **用例 A**：`_reserve_idempotency` / `_should_retry` / `_normalize` 至少 2 个进入包
      （当前 0 个）。
- [ ] **用例 B**：`runtime.py` 或 `dispatcher.py` 进入包（当前首个候选 rank 19、包内无）。
- [ ] **三仓基准不回退**：TOTAL R@5 ≥ 0.912、MRR ≥ 0.756、负例 3/3。
- [ ] **cockpit 基准不回退**：R@5 ≥ 0.806、MRR ≥ 0.544、负例 2/2。
- [ ] **延迟不超标**：Deep 端到端 <10s（含 LLM），Gap 检查本身 <5ms。
- [ ] **二轮纪律**：单测证明最多 1 次迭代、结果必经 rerank、不绕过预算闸门。
- [ ] **G4/G5 不被重复实现**。
- [ ] 全仓 pytest、ruff、依赖方向检查全绿。

## 基准命令（回退判定用）

```bash
cd ~/2_github/AI/ACE/zace
set -a; source ~/.config/zace/benchmark.env; set +a
export no_proxy='*'

for t in leveldb-v1 helloagents-v1 langchain-v1 cockpit-agents-py; do
  uv run python benches/run.py --target $t \
    --data ~/.zace/bench/voyage-4-lite-d1024 --report /tmp/bench-$t.md
done
```

## 明确不做

- 不做 2-hop 常规扩展（只在 G1 触发时按需做，见 TASK-011 的"明确不做"）；
- 不做 HyDE / Multi-Query 查询改写（需额外 LLM 调用，违反 R1）；
- 不做 Cross-Encoder / LLM rerank（V1.5）；
- 不做固定轮数的盲搜（用户明确否决："不要重复检索 2-3 次"）。

## 待讨论项（开工前与编排者确认）

1. **G1 的触发条件**：设计写的是 "Structural 路由且 callPaths 平均长度 <2"，
   但**轻路由四分支尚未落地**（`engine.py` 恒走 Fast）。
   是否先用**路由无关**的条件替代：如"包内 ≥1 个符号但没有 `[F*]` flow 证据"？
2. **G6（容器-成员断层）是否纳入**：它是本卡实测暴露的新缺口，§4.7 没有。
   纳入则需在设计文档 §4.7 补一行（属设计面，要编排者裁决）。
3. **G3 的扩展查询构造**：用符号名还是文件名？两者权重？
4. **二轮候选的预算法**：独立小预算（标记来源）还是共用主闸门？

## 执行记录

### 2026-09-15 · 建档（未开工）

- 由 6 次真实调用驱动建卡；同批发现的两个缺陷中，
  **客户端契约 bug 已由 TASK-108 修复**，本卡只解决召回覆盖。
- 已确认与 TASK-108 的分工（见上文"已排除的可能"对照实验）。
- 回归用例已固化：`benches/golden/cockpit-agents-py/cockpit.jsonl` 的
  `cockpit-0033`（链路）、`cockpit-0035`（Gateway），详见同目录 `qa.md`。
