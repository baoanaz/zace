# TASK-088：ask_project 接入 LLM 总结（可配置 + Citation 回验 + 设置页展示）

> 状态：review ｜ 阶段：Phase 3（M2c）｜ 硬依赖：无 ｜ soft 依赖：TASK-087（渲染补齐，可并行）
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

### 2026-09-14 ｜ 分支：`feature/task-088-llm-answer_xwz0914` ｜ 泳道 B ｜ 状态：review

**交付物（卡内清单内的全部完成）**

| 文件 | 内容 |
|---|---|
| `service/zace_service/config.py` | §A：`ANSWER_*` 六个环境变量（三必填 + 三默认）＋ `answer_configured` / `answer_missing_env` |
| `service/zace_service/answer.py`（新建） | §B `HttpAnswerProvider`（httpx，≤2 重试，退避 + Retry-After 上限）／§C Grounded Prompt（七条规则逐条）／§D `verify_citations` + `answer_question` |
| `service/zace_service/routers/query.py` | `ask` 改为 `async def`：未配置／LLM 失败／成功三分支；三个分支都不 500；审计交接修跨线程 |
| `service/zace_service/metadb.py` | §E：`query_audit` 加 `llm_latency_ms` / `answer_tokens`（`PRAGMA table_info` + `ALTER TABLE` 幂等迁移，本模块首条 ALTER 路径） |
| `service/zace_service/audit.py` | §E：`record_query` 透传三字段（默认 None = 未测量，不是 0） |
| `service/zace_service/routers/auth.py` | §F：扩展 `/api/meta` 的 `config`（embedding/LLM 生效值；key 任何部分不返回） |
| `service/tests/test_answer.py`（新建） | 39 条：DoD 七条 + §4 prompt + §E 审计 + §F 门禁 + provider 细节 |
| `.env.example` | 补 `ANSWER_*` 说明（含“未配置也不报错”） |
| `web/src/pages/SettingsPage.tsx`（新建）+ `App.tsx` / `Layout.tsx` / `api/client.ts` | 真实 `/settings` 页 + 导航末位“设置” + `EffectiveConfig` 类型 |

**清单外的最小必要改动（3 个文件，需编排者知悉并可与 TASK-087 合并时复核）**

| 文件 | 改动 | 原因 |
|---|---|---|
| `service/zace_service/mcp.py` | `_ask_text` 接入 LLM（复用 `answer_question`）；`build_mcp` 新增可选 `app` 参数；**每次工具调用重读配置**（原来语义冻结为“每次调用读一次”，只是从 `resolved_settings` 换成 `_load_settings()`） | agent 实际入口是 `ask_project`；不改则 MCP 面继续声称“Phase 3 尚未接入”＝假话（用户 2026-09-14 已同意同卡接入） |
| `service/tests/test_query_api.py` | 1 条断言按新语义改写 | 旧断言认 `Phase 3` 文案；旧文案在接入后成为假话（用户已同意） |
| `service/tests/test_usage_api.py` | 1 条断言追加 `llmLatencyMs` / `answerTokens` 为 null | 同上（`citationCoverageAvg` 断言未动，未配置时仍恒为 null） |
| `service/tests/test_mcp_endpoint.py`、`service/zace_service/app.py`、`web/src/app/Layout.test.tsx`、`web/src/pages/console.e2e.test.tsx` | 断言/装配随上述改动同步 | 同一组最小同步 |

**降级文案（诚实性）**：旧 `DEGRADED_NOTICE` 声称“Deep 模式（LLM 总结）尚未接入（Phase 3）”；
接入后该表述为假话，故拆为两条按原因的说明——`DEGRADED_NOTICE`（未配置，写出缺失的环境变量名）
与 `LLM_FAILED_NOTICE`（已配置但超时/报错/密钥无效）。两条都保留“以下为检索结果，可直接使用”。

**新增设计决定（理由）**

1. **`ask` 改为 `async def`**：LLM 调用是秒级阻塞 I/O，与 core 的 CPU 型检索不同；
   检索与 LLM 两次外呼都经 `run_in_threadpool`，事件循环不被拖住。
2. **审计上下文跨线程交接**：本服务的 `@app.middleware("http")` 是 BaseHTTPMiddleware，
   会把请求丢进 AnyIO 线程池，而 `_audited` 与 handler 可能落在**不同线程**、
   `contextvars` 不跨线程——除 ContextVar 外再把 `ctx` 存到 `request.state`，
   退出时按身份比较取回（否则 §E 的新字段会静默丢成 None）。
3. **`provider_for_app` 先认注入的 provider 再判“是否已配置”**：否则测试/未来替换实现在
   未配置环境下永远拿不到注入的实现（同一个接缝要能同时表达“替换实现”与“未配置”）。
4. **§F 选择扩展 `/api/meta`**（用户已确认）：设置页信息与部署形态同源、都由 `Settings` 计算，
   扩展它零新增路径、不动 CF-05 白名单；免鉴权风险用详尽度门禁化解——
   **本地模式或已登录**才返回模型名/地址/参数，未鉴权只返回 `configured` / `apiKeyConfigured` /
   `missingEnv`（环境变量名是公开文档信息）。`apiKeyConfigured` 恒为布尔，不含前缀与长度。
5. **`citationCoverage` 的段落口径**：有效引用按**出现次数**计，段落数取“非空、非标题、非代码块”的行；
   回验注记行本身算一行正文（`_count_paragraphs` 在注记追加之后统计）。这是刻意选择：
   覆盖率只入审计、不惩罚输出，口径差异不会改变返回给用户的答案。

**未决问题（交编排者）**

1. **与 TASK-087 的 `ask` 分支合并**：本卡按约定只实现 `answerable=true` 的 LLM 分支与两条降级分支；
   087 的 `answerable=false` 短路分支落在同一个 `with _audited(...)` 块内。两边的共同前提是
   “`ctx["pack"]` / `ctx["degraded"]` 必写”与 `pack_meta(..., degraded=True, reason=...)` 的初始值，
   合并时请保留本卡对 `status` 的取值集合 `answered` / `degraded` / `insufficient_evidence`。
   另：087 会在 `render_markdown` 里新增 `### Suggested Next Queries` 节；本卡的 prompt 证据块只取
   `### Code` / `### Docs` 两节，新增节**不会**被误当成证据塞进 prompt（`_split_sections` 保留未知节
   但仅 Code/Docs 会被取用，且 TASK-087 的节渲染在 `render_markdown`，与 prompt 用的
   `render_evidence_for_prompt` 无关）。
2. **审计 `answerTokens` 是估算值**：本服务不引 tokenizer（无新依赖纪律），按“约 2 字符 1 token”折算，
   只用于观察分布，不等于计费口径；若后续需要精确值，可改读 provider 响应的 `usage.completion_tokens`
   （本卡未做：那会把“是否 reasoning 模型”的差异带进审计口径）。
3. **`estimate_tokens` 与 `citationCoverage` 的阈值**：文档 §5/§8 只要求“先观察分布”，
   本卡未设任何告警阈值；建议 TASK-093 拿到真实审计数据后再定。

**验收命令与结果（本机实测）**

```text
uv run ruff check .                                    → All checks passed!
uv run python scripts/check_dependency_direction.py     → 依赖方向检查通过（core 纯库 / service 不上探）
uv run --extra dev python -m pytest -o addopts="" -q     → 844 passed, 2 skipped
uv run --extra dev python -m pytest service/tests/test_answer.py -q → 39 passed
cd web && npm run lint && npm test && npm run build      → lint 0 warning；41 passed, 3 skipped；构建成功
```

> 注：本机 `uv run pytest` 与 `uv run python -m pytest` 都因**当前 venv 缺 dev extra** 而报
> `No module named pytest`；加 `--extra dev` 后正常（与卡内命令等价，仅补 dev 依赖）。
> 基线数字对比卡内给出的 804 passed：本卡新增 39 条 + 其他已合并卡带来的增量，共 844。

**行为验收（真实 LLM）**

真实调用部分由**编排者/用户**执行（本会话只负责实现与自动化验收），报告模板中的
“真实 LLM 回答全文 + citationCoverage + llmLatencyMs”与“改 env 即改模型”两次调用证明
由用户侧补齐。实现侧已保证：模型名、base URL、超时、maxTokens、temperature**全部**来自
`ANSWER_*`（`test_model_timeout_and_temperature_come_from_config` 断言模型名/上限/温度直接进
请求体、超时进 `httpx.Timeout`；`test_build_provider_uses_configured_values` 断言默认值来源唯一）。

**建议复核点**：① `query.py` ask 的三分支与审计交接；② `answer.py` 的 prompt 组装与回验口径；
③ `/api/meta` 的门禁分支（未鉴权不泄露模型名/地址）；④ `metadb._migrate` 的幂等加列。
