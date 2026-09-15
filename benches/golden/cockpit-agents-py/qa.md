# cockpit-agents-py 靶场 QA（真实失败现场）

> 本文件记录 **2026-09-15 真实接入验证**新增的 6 题（`cockpit-0033` ～ `cockpit-0038`）
> 的来源、源码真值与回归价值。前 32 题（`cockpit-0001` ～ `cockpit-0032`）的出处见 git 历史。
>
> **本靶场的特殊价值**：新增的 6 题不是人工设计的，而是**真实失败现场**——其中 2 题暴露了
> 真实缺陷，可直接作为回归护栏。

固定版本：`febac6d2273bbd8828e34b81bd9c1b50753255ab`（2026-09-09）。
源码路径：`/home/xuwenzheng/4_AIBOX/gitlab/minicpm/cockpit-agents-py`。

## 新增 6 题的首次实测记录（缺陷证据，勿删）

| ID | 工具 | 首次得分 | 症状 |
|---|---|---|---|
| `cockpit-0033` | search | 6.5/10 | 找到 `FixedIntentRouter` 与文档准入顺序，漏 `runtime.py` / `dispatcher.py` 的调用链 |
| `cockpit-0034` | search | 8.0/10 | 命中 `AnswerCommitBridge` 与关键测试；`_commit()` 与 Coordinator 调用位置不完整 |
| `cockpit-0035` | search | **3.5/10** | 只命中 `_verify()` 与少量测试，漏 `_reserve_idempotency` / `_should_retry` / `_normalize`，且返回大量无关 policy/context 证据 |
| `cockpit-0036` | ask | 9.0/10 | 正确区分"执行层支持多 Agent"与"意图分类固定 general_agent" |
| `cockpit-0037` | ask | **0/10 × 3 次** | `ask 响应不是合法 JSON: missing field 'answer'`——**客户端契约 bug** |
| `cockpit-0038` | ask | 9.0/10 | 结论与实现一致；正确指出最终回答冲突缺专项测试 |

### 两个真实缺陷（本靶场要守住）

1. **`cockpit-0037` = 客户端契约 bug**（已由 TASK-108 修复）
   服务端在 `answerable=false` 时返回 D-24 短路包（契约 `openapi.yaml` 明写 `answer`
   "insufficient_evidence 时不出现"），但 `zace-client` 把该字段写成必填 `String`
   → 反序列化失败 → Agent 拿不到任何可用输出。
   **回归护栏**：`client/src/remote.rs` 的 `ask_response_accepts_every_contract_branch`
   （四个契约分支逐个断言）。

2. **`cockpit-0035` = 召回覆盖不足**（待 TASK-109）
   `gateway.py` 的 37 个 chunk **全部正确索引**
   （`_reserve_idempotency` 336 行、`_should_retry` 487 行、`_normalize` 442 行），
   但首轮召回一条都没进包（`_reserve_idempotency` 在候选池 rank 98，另两个完全不在池）。
   这是**纯召回问题**：阈值调整与测试夹具抑制都解决不了。
   **回归护栏**：`cockpit-0035` 的 expected 就是这三个方法。

   > 对照实验（TASK-108 实测）：测试夹具常态抑制让包内测试从 20 条降到 1 条、
   > token 从 9912 降到 4698，但 `gateway.py` **仍未进包**——证明"噪音抑制"与
   > "召回补检"是两件独立的事。

## 逐题源码真值

### cockpit-0033 普通请求到 general_agent 的链路

```text
Runtime.admit()                     src/cvi_agent_core/runtime/runtime.py:43
  -> InputDispatcher.dispatch()     src/cvi_agent_core/runtime/dispatcher.py:45
  -> FixedIntentRouter              src/cvi_agent_core/runtime/intent_router.py:20
       GENERAL_AGENT_ID = "general_agent"   （同文件 :10）
```

`Runtime.admit()` 串行准入（`dispatcher.py:75` 用 `self._admitted` 按 input_id 去重）；
`InputDispatcher.__init__` 默认注入 `FixedIntentRouter()`（`dispatcher.py:65`）。

### cockpit-0034 最终回答的 exactly-once

- `answer_bridge.py:7-8` 模块 docstring：`identity` 用作 `HistoryStore.append_committed`
  的幂等键，replay/retry 不会重复产出；
- `answer_bridge.py:46` 定义 `OutputCommitConflictError`（"exactly-once identity 被用于不同文本"）；
- `answer_bridge.py:99` 的 `await self._commit(execution_id, text, identity, ...)` 是提交点；
- `coordinator.py:926-939` 从 LangGraph 结果取 `final_answer` 并构造 commit identity。

### cockpit-0035 CapabilityGateway 的四件事

| 能力 | 实现位置 |
|---|---|
| 幂等 | `gateway.py:336 _reserve_idempotency` |
| 验证 | `gateway.py:401 _verify`、`:421 _normalize_verification`、`:442 _normalize` |
| 重试 | `gateway.py:487 _should_retry` |
| UNKNOWN 终态 | `gateway.py:579 _accept_terminal` |

### cockpit-0036 多领域意图路由

`FixedIntentRouter`（`intent_router.py:20`）是**迁移占位实现**，固定返回 `general_agent`，
**不是**真正的多领域分类器。执行层（`RuntimeApplication`）确实支持多 Agent，
但意图分类这一环仍固定——两者必须分开陈述，不能混为一谈。

### cockpit-0037 内核与产品层的依赖边界

依赖方向只能是 `product -> core`（反向导入即违规），由两个静态检查保护：

- `tests/architecture/test_architecture_iron_rules.py:93`
  `test_runtime_layer_does_not_import_product`
- `tests/architecture/test_package_boundaries.py:11`
  `test_framework_kernel_does_not_import_aibox_product`

两者都用 `ast` 解析源码、收集 `Import` / `ImportFrom` 并断言 `violations == []`。

### cockpit-0038 最终回答与 ask_user 的 exactly-once

同 identity 同文本 → 幂等（返回既有结果）；同 identity 不同文本 → 抛
`OutputCommitConflictError`。`OutputCommitPort`（`output_commit.py`）是协议定义，
`AnswerCommitBridge` 是产品侧实现。该题还正确指出"最终回答冲突缺少专项测试"这一实现缺口。

## 数据持久化

| 项 | 位置 |
|---|---|
| 索引 | `~/.zace/bench/voyage-4-lite-d1024/projects/8e69da62f37e5783` |
| projectId | `8e69da62f37e5783`（由 git remote 决定） |
| 规模 | 287 文件 / 3416 chunks |
| 源码 | `/home/xuwenzheng/4_AIBOX/gitlab/minicpm/cockpit-agents-py`（commit `febac6d`） |
| role | `internal`（索引含公司内部源码，只能内网获得，不进默认流程） |

> **路径陷阱（已踩过，务必注意）**：`zace/benchmark/cockpit-agents-server` 与
> `4_AIBOX/.../cockpit-agents-py` **共用同一个 git remote**
> （`.../cockpit-agents-server.git`），因此**共用同一个 projectId 与索引**。
> 但前者 checkout 在更旧的 commit（`135ac28`，2026-07-20，53 文件），
> **不含**本靶场需要的大部分符号。误用它 ingest 会把索引覆盖成旧版本。
> 恢复：
>
> ```bash
> uv run zace-core ingest --repo /home/xuwenzheng/4_AIBOX/gitlab/minicpm/cockpit-agents-py \
>   --data ~/.zace/bench/voyage-4-lite-d1024 --full
> ```

## 运行

```bash
set -a; source ~/.config/zace/benchmark.env; set +a
export no_proxy='*'
uv run python benches/run.py --target cockpit-agents-py \
  --data ~/.zace/bench/voyage-4-lite-d1024 --report /tmp/bench-cockpit.md
```

6 题里有 3 题是 `tool=ask`（`cockpit-0036`／`0037`／`0038`），
端到端验证走 `benches/golden/qa_probe.py`（需配置 `ANSWER_*`）；
`search` 题（`cockpit-0033`～`0035`）在 `run.py` 里即可覆盖。
