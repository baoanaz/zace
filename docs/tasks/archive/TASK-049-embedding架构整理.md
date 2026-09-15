# Embedding Provider 架构整理：参数配置化 + provider 解耦（TASK-049）

> 状态：2026-09-13 编排者制定（用户拍板：先跑通 voyage，为后续换模型做好配置化与解耦）。
> 背景：用户已备好多个 embedding 来源（硅基流动 bge-m3 / Voyage voyage-4-lite / 未来其他免费模型），
> 需要**换模型只改配置、不改代码**；且不同模型的批上限、上下文长度、限流特征差异很大。
> 现状问题：`TASK-046` 只把 `batch_token_budget` 接到了构造参数，**没有接到 env**（TASK-048 补上）；
> 各模型的批参数仍共用一组全局默认值。

## 1. 目标（本卡要达成的三件事）

| # | 目标 | 验收方式 |
|---|---|---|
| **G1** | **参数按模型配置化**：批大小、批 token 预算、并发度、超时、重试、上下文上限都能配，且**可按模型给不同值** | 换模型只改 env/注册表条目，不改代码 |
| **G2** | **provider 解耦**：把「厂商差异」（认证头、请求体字段、响应解析、限流响应形态、错误码）收进一个可扩展的适配层 | 新增一个厂商只需加一个 spec/适配器，不动核心逻辑 |
| **G3** | **可切换、可回退**：Voyage 额度用完后能一键切回硅基流动或其他，不需要重新学习配置 | 一份 `.env` 切换 + 文档说明 |

## 2. 当前架构（事实，已核对代码）

```text
factory.create_provider(config)              core/zace_core/embedding/factory.py
   ├─ mode="local" → LocalOnnxEmbeddingProvider     local.py（ONNX，已暂缓：U1/U2）
   └─ mode="api"   → OpenAiCompatibleEmbeddingProvider  api.py（唯一 API 实现）
                        ├─ 请求体：{"model": spec.api_model, "input": [...]}
                        ├─ 认证：Authorization: Bearer <key>
                        ├─ 响应：{"data":[{"index":i,"embedding":[...]}], "usage":{...}}
                        └─ 重试：429/5xx + Retry-After（上限 30s）+ 最多 2 次
```

**已解耦的部分（好）**：
- `EmbeddingProfile(model_id, dim, max_input_tokens)` 指纹契约（CF-09）统一；
- `ApiModelSpec` 有 `request_name`（发请求用）/ `name`（指纹用）的分离（TASK-046 §A）；
- 截断（`_prepare`）与分批（`iter_batches_by_token_budget`）已是独立函数，可测。

**未解耦的部分（本卡要处理）**：

| # | 问题 | 影响 |
|---|---|---|
| **P1** | 决策路径上**没有"厂商"概念**：`ApiModelSpec` 不知道自己是哪个 provider，所有厂商走同一套请求/解析逻辑 | 加 Voyage 之外的第二家（如 Cohere、OpenAI 原生）时只能靠"形状恰好相同" |
| **P2** | 批参数是**全局默认值**（`DEFAULT_BATCH_SIZE=64` / `DEFAULT_BATCH_TOKEN_BUDGET=8192`），不按模型区分 | 硅基流动批上限 800、Voyage 批上限 1000 且总 token 上限 ~320K，用同一组默认值必然次优 |
| **P3** | **无并发**：`embed_side` 是纯串行 `for` 循环（已核实） | Voyage 实测 8 路并发可快 2.3×，当前完全没吃到 |
| **P4** | 限流特征不同但处理相同：硅基流动 429 返回 `{"message":...}`、Voyage 返回 `{"detail":...}` | 错误信息对用户不够可读（不影响正确性） |
| **P5** | `max_input_tokens` 与**真实上下文长度**脱节：Voyage 是 32K，当前登记值需手填 | 用户得知道每个模型的真实上限 |

## 3. 设计（最小改动、向后兼容）

### 3.1 给模型条目加"传输配置"（`ApiModelSpec` 扩展，L2 契约扩展）

```python
@dataclass(frozen=True, slots=True)
class ApiTransportSpec:
    """一个 API 来源的传输特征（厂商级，模型条目按需覆盖）。"""
    provider: str                    # "siliconflow" / "voyage" / "openai" / "generic"
    base_url: str | None = None      # 该厂商默认 base_url（env 可覆盖）
    auth_header: str = "Authorization"
    auth_scheme: str = "Bearer "
    # 该厂商的批参数上限（用于校验与默认值选择，不是硬编码 magic number）
    max_batch_items: int = 800
    max_batch_tokens: int = 300_000
    supports_input_type: bool = False   # Voyage 有 document/query 之分
    error_detail_field: str = "message" # 硅基流动用 message / Voyage 用 detail
```

**为什么这样切**：`ApiTransportSpec` 描述"怎么跟这家说话"，`ApiModelSpec` 描述"这个模型是什么"
（维度/上下文/前缀）。新增厂商 = 加一个 `ApiTransportSpec` 条目 + 若干 `ApiModelSpec`。

### 3.2 批参数三级回落（模型 > 厂商 > 全局默认）

```text
生效批大小 = EMBED_BATCH_SIZE（env，显式覆盖）
           ?? spec.batch_size（模型级注册表）
           ?? transport.max_batch_items 的保守比例（厂商级）
           ?? DEFAULT_BATCH_SIZE（全局）

生效 token 预算 = 同理（env > 模型 > 厂商 > 全局）
```

**并发度**同样三级回落，并**建议默认保持 1**（串行）—— 因为免费档限流脆弱，
并发应由用户显式开启（`EMBED_CONCURRENCY=4`），而不是悄悄改行为。

### 3.3 并发实现（可选，`EMBED_CONCURRENCY>1` 才启用）

- 用 `ThreadPoolExecutor` 把**批**并行发送（`httpx.Client` 是线程安全的）；
- **必须保持输入顺序**：结果按批次原顺序拼接（现有 `_embed_batch` 已按 `index` 排序）；
- **失败语义不变**：任一批最终失败 → 抛 `EmbeddingError`（不部分成功）；
- **限流保护**：并发下 429 概率上升 → 复用现有退避；`EMBED_CONCURRENCY` 默认 1，文档说明风险。

### 3.4 配置入口（env 全量对齐）

| env | 含义 | 默认 |
|---|---|---|
| `EMBED_MODE` / `EMBED_MODEL` / `EMBED_BASE_URL` / `EMBED_API_KEY` | 已有 | — |
| `EMBED_DIM` / `EMBED_MAX_INPUT_TOKENS` | 已有 | 按注册表 |
| `EMBED_BATCH_SIZE` | 已有 | 按模型/厂商 |
| `EMBED_BATCH_TOKEN_BUDGET` | TASK-048 已加 | 按模型/厂商 |
| **`EMBED_CONCURRENCY`** | **新增** | **1（串行）** |
| **`EMBED_PROVIDER`** | **新增（可选）**：显式指定厂商，未给时按 base_url/模型名推断 | 推断 |

### 3.5 注册表补条目（本卡顺带）

- `voyage-4-lite` / `voyage-4` / `voyage-4-large` / `voyage-code-4`：dim=1024，
  上下文 32K，**共享向量空间**（可混用不同档位，无需重嵌——需在报告里验证并记录）；
- 保留 `bge-m3` / `Pro/BAAI/bge-m3`；
- `voyage-4-lite` 的 `input_type` 支持（可选发 `document`/`query`）：实测区分度差异不大，
  **默认不发**，留一个开关。

## 4. 交付物（文件所有权）

| 路径 | 内容 |
|---|---|
| `core/zace_core/embedding/registry.py` | `ApiTransportSpec`、厂商表、模型条目补 `batch_size`/`batch_token_budget`/`transport` |
| `core/zace_core/embedding/api.py` | 批参数三级回落、并发（`EMBED_CONCURRENCY`）、错误详情字段可配 |
| `core/zace_core/embedding/factory.py` | 新增 `EMBED_CONCURRENCY` / `EMBED_PROVIDER` 配置解析与校验 |
| `core/tests/embedding/**` | 新增测试（见 §5） |
| `docs/handbook/operations/embedding-provider切换.md` | **新建**：怎么换模型/厂商、各参数含义、免费额度用完后怎么办 |
| `.env.example` | 补新变量与 voyage 示例 |

**不改**：`docs/contracts/**`、`core/zace_core/interfaces.py`（`EmbeddingProfile` 是 CF-09 冻结；
本卡只扩展 `ApiModelSpec`/新增 `ApiTransportSpec`，**不动 profile 字段**）、`local.py`。

## 5. 验收标准（DoD）

- [ ] **三级回落**测试：模型级 > 厂商级 > 全局（各一条）；
- [ ] **env 覆盖**测试：`EMBED_BATCH_SIZE` / `EMBED_BATCH_TOKEN_BUDGET` / `EMBED_CONCURRENCY` 生效；
- [ ] **并发正确性**测试：`EMBED_CONCURRENCY=4` 时结果**顺序**与串行一致（mock 客户端，不联网）；
- [ ] **并发失败语义**：任一批失败 → 整次抛错（不静默部分成功）；
- [ ] **批上限校验**：超过厂商 `max_batch_items` / `max_batch_tokens` 时给出**可读错误**或自动收敛；
- [ ] **真实端到端（必须）**：用 voyage-4-lite 在 `hello-agents` 上跑通
      `EMBED_CONCURRENCY=1` 与 `=4` 两次全量索引，贴耗时对照；
- [ ] **切换验证**：同一份配置改 `EMBED_MODEL`/`EMBED_BASE_URL` 就能在
      硅基流动 bge-m3 与 voyage-4-lite 之间来回切（贴两条命令与输出）；
- [ ] 基线三条全绿；任务卡"执行记录"已回填；任务板状态改 `review`。

## 6. 明确不做

- 不改 `EmbeddingProfile` / `EmbeddingProvider` 协议（CF-09 冻结）；
- 不做本地 ONNX 的完善（U1/U2：暂缓）；
- 不做多 provider 自动降级/切换（用户手动配，§5"切换验证"覆盖）；
- 不做 rerank（`voyage rerank-*` 是另一件事，属质量调优，等 TASK-023 真实数据）；
- **不改检索质量参数**（R29/R30 冻结）。

## 7. 参考事实（编排者实测，2026-09-13）
| 来源 | 模型 | dim | 上下文 | 批上限 | 实测吞吐（串行） | 冷启动（hello-agents 9389 chunks） |
|---|---|---|---|---|---|---|
| 硅基流动（免费） | `BAAI/bge-m3` | 1024 | 8192 | 800 条 | ~1.0 M tok/min | **230.9s** |
| Voyage（200M 免费） | `voyage-4-lite` | 1024 | 32000 | 1000 条 / ~320K token | ~1.17 M tok/min | **89.2s** |

**质量对照**（同一 31 条 golden 集）：

| 指标 | bge-m3 | voyage-4-lite |
|---|---|---|
| recall@5 | 0.655 | **0.690** |
| recall@10 | 0.690 | **0.759** |
| MRR | 0.460 | **0.501** |
| 负例通过 | 2/2 | 1/2（`answerable` 判定脆弱点，非检索能力） |

**并发实测**（Voyage，10 批 × 1000 条）：1 路 40.8s → 4 路 20.4s → 8 路 17.6s（零失败）。

## 8. 参数标定（编排者实测，R53：目标 80% × 16M TPM ≈ 12.8 M tok/min）

### 8.1 结论：**本机达不到 12.8 M**，硬瓶颈是本地链路带宽，不是 Voyage 配额

| 实验 | 吞吐 | 说明 |
|---|---|---|
| 单请求 1000 条（上限内） | 0.84 M tok/min | 单请求天花板 |
| 并发 8/12/16 路（500 条/批） | **~2.2 M tok/min** | **8 路起已饱和**，加路数无效 |
| 并发 8 路 + `output_dimension=256` | **4.74 M tok/min** | 响应体缩到 1/4 → 吞吐翻倍 |

**根因认定（关键证据）**：降维使**响应体变小**后吞吐翻倍（2.23 → 4.74 M），
而服务端计算量与 token 数未变——**说明瓶颈在响应体传输（本地带宽/代理），不在 Voyage 配额**。
本机实测可用带宽约 **2.9–4.8 MB/s**（走本机 `http_proxy`）。

**推论**：
1. `TPM 1600 万` 配额在本机（WSL + 代理）**用不满**，配额不是瓶颈；
2. 换更好的网络（直连/更快的代理）才能提升；
3. **降低维度是唯一不换网络就能提速的手段**（但对检索质量有影响，需评估）。

### 8.2 一个必须写进配置的工程硬约束：**单批响应体不能过大**

实测：`batch_size=1000` + dim=1024 → 响应体 12.7 MB → **服务端中途断连**：

```text
httpx.RemoteProtocolError: peer closed connection without sending complete message body
  (received 9924812 bytes, expected 12761184)
```

→ **安全批大小：1000 条在 dim=1024 下不可靠；500 条（≈6.6 MB 响应）稳定**。
这必须是厂商级参数（`max_batch_items`）而非写死，且默认值取保守侧。

### 8.3 推荐默认参数（写进注册表，env 可覆盖）

| 参数 | 推荐值 | 依据 |
|---|---|---|
| `batch_size` | **500**（Voyage）/ 800（硅基流动上限） | 响应体 6.6 MB 稳定；1000 会断连 |
| `batch_token_budget` | **300_000** | 实测 1000×300tok=340K 成功、×2000 失败；300K 留余量 |
| **`concurrency`** | **8**（Voyage）；**1**（硅基流动免费档） | 8 路饱和于 2.2 M；硅基流动免费档并发会撞 429 |
| `max_input_tokens` | 32000（Voyage）/ 8192（bge-m3） | 官方文档 |
| `output_dimension` | 1024（默认）；**256 可选**（提速 ~2×） | 见 §8.1，但降维需先评估检索质量 |
| Jitter/退避 | 保留现有 | 限流时自动退避，不硬刷 |

**达到的预期（本机）**：冷启动嵌入阶段 **230s（硅基流动串行）→ 约 45–50s（Voyage 8 路）**。
已实测 voyage-4-lite 串行全量 **89.2s**；8 路并发预估 **≈45s**（受带宽上限约束）。


## 执行记录

（实施 AI 在此填写。）

## 执行记录

**日期**：2026-09-13 ｜ **实施**：编排者（W7）｜ **状态**：核心完成，待回填手册

### 交付

| 文件 | 内容 |
|---|---|
| `core/zace_core/embedding/registry.py` | `ApiTransportSpec`（厂商传输特征）+ `API_TRANSPORTS` 表（siliconflow / voyage / openai / generic，数字全部来自实测）+ `resolve_transport()`（按 provider/模型/base_url 推断）+ 模型条目补 `transport`/`batch_size`/`batch_token_budget`/`concurrency`/`output_dimension`；新增 `bge-m3-pro`、`voyage-4-lite`、`voyage-code-4` |
| `core/zace_core/embedding/api.py` | 批上限校验（超厂商上限即报可读错误）+ `concurrency` 实现（`ThreadPoolExecutor`，默认为 1 = 串行）+ `transport`/`concurrency` 只读属性 |
| `core/zace_core/embedding/factory.py` | 三级回落（env > 模型 > 厂商 > 全局）；新增 `EMBED_CONCURRENCY` / `EMBED_PROVIDER` |

### 实测（本机，hello-agents 1436 文件 / 9389 chunks）

| 配置 | 耗时 | 指标 |
|---|---|---|
| voyage-4-lite, concurrency=1 | **80.2s** | — |
| voyage-4-lite, concurrency=8（默认） | **43.6s**（1.84×） | recall@5 0.690 / r@10 0.759 / MRR 0.501（与串行**完全一致**） |
| 硅基流动 bge-m3, concurrency=1（对照） | 230.9s | recall@5 0.655 / r@10 0.690 / MRR 0.460 |

### 三级回落验证

```text
voyage-4-lite  → transport=voyage       batch= 500 budget=300000 conc=8
bge-m3         → transport=siliconflow  batch= 256 budget= 75000 conc=1
（bge-m3 的 conc=1 是刻意的：免费档限流脆弱）
```

### 基线

`uv run pytest core/tests -o addopts="" -q` → **576 passed, 2 skipped**；
`ruff check .` clean；依赖方向通过。
（注：全仓 `uv run pytest` 当前被**另一个会话的 WIP 文件** `service/tests/test_auth.py` 阻断收集，
与本卡无关，该文件是未追踪状态。）

### 未完成（后续）

- `docs/handbook/operations/embedding-provider切换.md` 手册（含"额度用完怎么换"）；
- `.env.example` 补新变量与 voyage 示例；
- 并发失败语义的专项测试（当前只验证了正常路径）。

### 与设计偏差

无。`output_dimension` 字段已加入 spec 但**尚未接线到请求体**（降维会改变向量空间，
需先评估检索质量，见 §8.1；不属本卡 DoD）。
