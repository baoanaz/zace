# TASK-088：ask_project 接入 LLM 总结（可配置 + Citation 回验 + 设置页展示）

> 状态：pending ｜ 阶段：Phase 3（M2c）｜ 硬依赖：无 ｜ soft 依赖：TASK-087（渲染补齐，可并行）
> 建议分支：`feature/task-088-llm-answer_<你的缩写><MMDD>`
> 交付物所有权：
> - `service/zace_service/answer.py`（**新建**：AnswerProvider + Grounded Prompt + Citation 回验）
> - `service/zace_service/config.py`（新增 `ANSWER_*` 配置）
> - `service/zace_service/routers/query.py`（`ask` 端点的 `answerable=true` 分支）
> - `service/zace_service/routers/ops.py`（**仅** `/api/meta` 或新只读端点，用于设置页展示）
> - `service/tests/test_answer.py`（**新建**）
> - `.env.example`（补 `ANSWER_*` 说明）
> - `web/src/pages/SettingsPage.tsx` + `web/src/app/{App,Layout}.tsx` + `web/src/api/{client,types}.ts`（设置页）
>
> 清单外文件不得改。**特别提醒：不要改 `core/zace_core/**`（TASK-087 的领地）；
> 不要改 `packmeta.py` 的字段集（CF-05 冻结）。**

## 目标

把设计文档 `docs/design/Module/04-AI总结.md` **§2/§4/§5/§6/§7/§8** 落地：
`ask_project` 在证据充足时调用 LLM 做 grounded 总结，并回验引用。

**用户口径（2026-09-14 明确）**：

> 代码针对于 ask 的 LLM 要配置，不要写代码里面，要可配置的，因为未来可能会改模型。

> 全部走环境变量，其中 `ANSWER_TIMEOUT_S` / `ANSWER_MAX_TOKENS` / `ANSWER_TEMPERATURE`
> 不需要用户配置，用户只需要给 URL/KEY/MODEL，其他我们写好就行不会经常变的，
> 然后设置页面也做展示，展示当前的 embedding 模型和 LLM 模型。

## §A 配置（`config.py`，照 `EMBED_*` 的既有模式扩展）

**用户只需配三个**（其余有内置默认值，仍允许环境变量覆盖）：

| 环境变量 | 必填 | 说明 |
|---|---|---|
| `ANSWER_BASE_URL` | ✅ | 如 `http://154.12.34.214:8080/v1`（OpenAI-compatible `/chat/completions`） |
| `ANSWER_API_KEY` | ✅ | 密钥（**绝不进日志/响应/仓库**） |
| `ANSWER_MODEL` | ✅ | 如 `deepseek/deepseek-v4.1-flash` |

**内置默认值（用户不用管，但可覆盖）**：

| 环境变量 | 默认 | 依据 |
|---|---|---|
| `ANSWER_TIMEOUT_S` | `60` | 文档 §2 参数表（连接 10s） |
| `ANSWER_MAX_TOKENS` | `3072` | 文档 §2 |
| `ANSWER_TEMPERATURE` | `0.2` | 文档 §2（调查要事实不要创意） |

**未配置 `ANSWER_*` → `ask_project` 走 D-26 降级包（不报错、不崩）**，`search_context` 完全不受影响。
这是文档 L5 的硬要求（开源产品冷启动体验）。

## §B AnswerProvider（`service/zace_service/answer.py`，新建）

照文档 §2 的接口：

```python
class AnswerProvider(Protocol):
    def complete(self, *, system: str, user: str, max_tokens: int, temperature: float) -> str: ...
```

- **`httpx` 已在依赖里**（embedding 用的就是它），**不要引入新依赖**（不加 openai SDK）；
- **重试**：≤2 次（文档 §6）；
- **超时/错误/未配置** → 抛可识别异常，由 `query.py` 转成降级包（**绝不 500**，D-26）；
- key 绝不进日志（用 `redact_text`；若它不覆盖裸 key，本卡内自建兜底，参考 TASK-084 的 `redact_query_text`）。

## §C Grounded Prompt（文档 §4，**逐条落实**）

System prompt 必须包含**七条规则**（原文照抄文档 §4）：

1. 只能依据 Evidence 回答；不得使用外部知识推测仓库内容
2. 引用格式：`[E1]` 代码/文档证据，`[F1]` 调用链证据；每个重要结论必须附引用
3. Code 证据代表当前实现，Doc 证据代表设计意图；两者冲突时必须显式指出"实现与设计可能不一致"
4. 调用关系只信 `[F*]` 与证据内容；禁止虚构任何调用关系
5. 证据不足时明确回答"证据不足"并说明缺什么，不要猜测
6. 直接回答问题；不要复述全部证据
7. 用与 `<question>` 相同的语言回答

User prompt 结构（文档 §4）：`<question>` + `<context_meta>`（confidence/freshness）+ `<evidence>`
（按 `[Docs]` / `[Code]` / `[Flows]` 分组，带 `[E*]` 编号与 `文件:行号`）。

回答模板（空节自动省略）：`## Answer` / `## Code Flow` / `## Key Evidence` /
`## Spec vs Implementation` / `## Missing Evidence`。

## §D Citation 回验（文档 §5，确定性、成本为零）

- 从 answer 正则抽取 `\[E\d+\]` / `\[F\d+\]`；
- **id 存在于 ContextPack → 保留**；不存在（虚构）→ **删除该标记**（保留原文，不改写句子），
  并在 `Missing Evidence` 节追加「回答中 N 处引用无效已移除」；
- `citationCoverage = 有效引用数 / 结论段落数` → 存审计（**不惩罚输出，先观察分布**）。

## §E 审计（文档 §8）

`ask` 成功后落审计，**新增字段**：`llmLatencyMs`、`answerTokens`、`citationCoverage`。
（TASK-084 已建 `query_audit` 表；若需加列，走 migration 并在报告里说明。）
**不存源码内容**，只存 evidence id/path/score（文档 §8 明确）。

## §F 设置页（用户明确要求）

新增只读设置页，展示**当前实际生效**的配置（**不显示 key 明文**）：

| 展示项 | 来源 |
|---|---|
| embedding 模型 / mode / provider | 现有 `EMBED_*` 生效值 |
| **LLM 模型 / baseUrl / 是否已配置** | 新增 `ANSWER_*`（key 只显示"已配置/未配置"） |
| 超时 / maxTokens / temperature | 只读展示 |

- 后端：**扩展现有 `/api/meta`**（它已免鉴权、已有 `version`/`localMode` 等）
  **或**新增只读端点（你自己判断哪个更合适并说明理由）；
  **不要把 key 的任何部分（含前缀/长度）返回给前端**；
- 前端：新增 `/settings` 路由与导航项（放在导航最后一位），
  风格与既有页面一致（`Card` / `KeyValue` 组件已存在，直接复用）；
- 文案要求：未配置 LLM 时明确显示"未配置（ask_project 返回检索结果）"，不要显示空白。

## 验收标准（DoD）

- [ ] `uv run pytest service/tests/test_answer.py -q` 全绿，**必须覆盖**：
  - [ ] 未配置 `ANSWER_*` → `ask` 返回**降级包**（200，`status` 非 LLM 结果），**不报错**（L5）；
  - [ ] 配置了但 API 报错/超时 → 降级包 + 前置说明（D-26 故障矩阵）；
  - [ ] **mock LLM 返回虚构引用**（如 `[E99]`）→ 该标记被删除，且 Missing Evidence 有注记；
  - [ ] 有效引用（`[E1]` 且存在于 pack）→ **保留**；
  - [ ] `citationCoverage` 计算正确（构造 2 段结论 / 1 个有效引用 → 0.5）；
  - [ ] **key 不进日志**：断言日志/响应里搜不到 key 明文（用真实形态的假 key 构造）；
  - [ ] 模型名/超时来自**配置**（改 env → 行为变），**不是硬编码**（这是用户的核心要求）。
- [ ] **真实调用验收（贴真实输出）**：用 `xiugou-deepseek` 配置对 `HelloAgents` 提问
      「流式输出在哪个文件实现」，贴出 `answer` 全文 + `citationCoverage` + `llmLatencyMs`。
      配置（**key 从 `~/.bashrc` 取，不要写进仓库/报告**）：
      ```
      ANSWER_BASE_URL=http://154.12.34.214:8080/v1
      ANSWER_API_KEY=$XIUGOU_DS_API_KEY      # ~/.bashrc:148
      ANSWER_MODEL=deepseek/deepseek-v4.1-flash
      ```
- [ ] 设置页验收：截图或贴 DOM，确认展示 embedding 与 LLM 模型、且**无 key 泄露**。
- [ ] `cd web && npm run lint && npm test && npm run build` 全绿。
- [ ] 基线三条命令全绿（用 `-o addopts=""` 看数字）。
- [ ] 任务卡"执行记录"已回填；任务板状态改为 `review`。

## 明确不做

- 不做多轮 LLM（文档 §10）；
- 不做流式输出（文档 §10）；
- 不做回答缓存（文档 §10）；
- 不做 LLM rerank（归 Module 02）；
- 不改 core 的检索/装填/渲染（TASK-087 与 R29/R30 冻结）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板。**必须包含**：真实 LLM 回答全文、citationCoverage、
以及"改 env 即改模型"的实测证明（贴两次不同 `ANSWER_MODEL` 的调用结果）。

## 执行记录

（实施 AI 在此填写。）
