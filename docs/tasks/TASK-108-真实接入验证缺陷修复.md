# TASK-108：真实接入验证暴露的缺陷修复（客户端契约 / 装填闸门 / 测试抑制 / 控制台展示）

> 状态：review ｜ 阶段：Phase 5+（质量）｜ 硬依赖：TASK-107 ｜ soft 依赖：TASK-109
> 分支：`main`（用户授权直接改，真实环境验证）
> 交付物所有权：`client/src/{remote,tools}.rs`、`core/zace_core/retrieval/rerank.py`、
> `core/zace_core/contextpack/{assembly,render}.py`、`service/zace_service/{audit,config}.py`、
> `service/zace_service/routers/auth.py`、`service/zace_service/metadb.py`、`web/src/**`、
> `docs/handbook/部署指南.md`

## 背景

2026-09-15 用真实 MCP 客户端（Codex）对 cockpit-agents-py 做 6 次调用（3 search + 3 ask）
并逐项对照本地源码，暴露 4 类问题。本卡修其中 3 类；第 4 类（召回覆盖）转 TASK-109。

## 修复清单

### A. 客户端契约 bug（可用性，影响面最大）

**现象**：`ask_project` 在 `answerable=false` 时连续失败，报
`ask 响应不是合法 JSON: missing field 'answer'`，Agent 拿不到任何可用输出。

**根因**：服务端在 D-24 短路时返回
`{status, bestEffortContext, missingEvidence, nextQueries, meta}`（契约
`docs/contracts/openapi.yaml` 明写 `answer` **"insufficient_evidence 时不出现"**），
但 `client/src/remote.rs` 的 `AskResponse.answer` 写成了必填 `String`。

**修复**：`answer` 改 `Option<String>`，并新增 `bestEffortContext`/`missingEvidence`/`nextQueries`
字段与 `into_text()`——四个契约分支都产出可用文本，短路时回退到尽力而为的上下文包。

**验证**：新增契约回归测试 `ask_response_accepts_every_contract_branch`（覆盖 4 个分支）；
用本地编译产物真实调用，从 `isError: true` 变为 `isError: None` + 完整缺口说明。

### B. 装填闸门语义修正

**现象一（TASK-108 初版改错，已纠正）**：把 `score_ratio` 硬闸门改成"降级排序"
（不丢弃、预算允许就装），结果包被打满 10K，但后半是 `0.00`/`-0.24` 这类噪音
（tier3 图扩展邻居恒为固定分 0.70，不反映相关性）。**实测否决该方案，恢复硬闸门。**

**现象二（真实缺陷）**：闸门默认值 `0.50` 下，ask 类问题只装 3 条代码证据就把
`InvocationRegistry`（候选池 rank 10）挡在包外，LLM 因此报告"缺少源码证据"——
而**预算只用了 16%**。

**修复**：默认值 `0.50 → 0.40`。实测同一问题代码证据 3 → 10 条，且仍无 0.70 噪音组。

### C. 测试夹具常态抑制

**现象**（S3 题）：查"Gateway 如何保证幂等/验证/重试"，包内 **20 条测试 + 8 条代码**，
真正的 `capability/gateway.py` **一条都没有**。查询词恰好是测试函数名里的高频词
（`test_read_only_retry_reuses_identity_and_idempotency_key`），BM25 把测试顶上来。

**修复**：`test_fixture` 从"仅非测试意图时生效"改为**常态抑制**，权重 `-0.5 → -1.5`；
查询**明示**测试意图时不降（那时用户要的就是测试）。

**效果**：S3 包内测试 20 → 1 条，token 9912 → 4698。
**诚实边界**：`gateway.py` 仍未进包（其候选排 rank 72）——**噪音抑制 ≠ 召回补检**，
后者转 TASK-109。

### D. 控制台展示修复

1. **模型元数据空缺**：`_llm_model_metadata` 硬编码了一个**已废弃的模型名**
   （`deepseek/deepseek-v4.1-flash`），与实际使用的不一致 → 页面恒为空。
   改为显式配置驱动（`ANSWER_MAX_CONTEXT_TOKENS` / `ANSWER_PROVIDER` / `EMBED_TPM` / `EMBED_RPM`），
   未配置显示 `—`，**不猜**。
2. **历史页 Tool 输出不完整**：`evidence_json` 一直有写，但 `to_json` 未解析。
   现已输出 `symbol` / `group` / `reason`（分组与 Agent 看到的 Markdown **同源**，
   共用 `render.evidence_group`），仍不含源码正文（Module/04 §8）。
3. **详情弹窗排版**（用户定稿）：`信心：` / `Token：` / `证据数量（代码/文档/测试）：`；
   修掉重复的 `token` 行（`MetaRow` 曾同时渲染 `metrics` 与 `volume`）。

## 验收与实测数据

| 项 | 结果 |
|---|---|
| 三仓基准（ratio 0.40） | leveldb R@5 **1.000** / MRR 0.721；HA 0.842 / 0.754；LC 0.895 / 0.791；**合计 R@5 0.912、MRR 0.756、负例 3/3** |
| 对比基线（ratio 0.50） | 合计 R@5 0.895、MRR 0.746 → **无回退** |
| client 单测 | 全部通过（含新增契约回归） |
| A2 真实调用 | `isError: None`，返回缺口说明 + 建议查询 + 证据包 |
| S3 真实调用 | 测试 20 → 1 条，噪音清零 |

## 与设计的偏差

- **Module/04 §8**（审计不含源码内容）**未改动**：历史页展示的是证据结构与元数据，
  不含代码正文。用户确认接受这一取舍。
- **`score_ratio` 默认值**由 0.50 调为 0.40：属 TASK-015 校准面，有实测数据支撑。

## 未决问题

- **S1/S2/S3 的召回覆盖**未解决（目标候选未召回，非排序/装填问题）→ TASK-109。
- **npm 发布**：client 修复需推 tag 触发 release workflow 才能让 `npx zace-client` 用上；
  本地已用编译产物验证。

## 执行记录

### 2026-09-15

- 环境：WSL 固定测试环境（`~/.zace/live`，nginx + systemd，见 `docs/handbook/部署指南.md` 第二章）。
- 固定凭据：账户 `xuwenzheng`、Key `zace_123456`、URL `http://localhost/zace-service/`。
- 基准环境：`~/.zace/bench/voyage-4-lite-d1024`（持久化，见部署指南第三章）。
