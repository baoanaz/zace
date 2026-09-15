# TASK-046：云端 embedding 接入与配置对齐（硅基流动 / bge-m3 为当前主路径）

> 状态：done（2026-09-13 编排者评审合并；F1/F2/F3/F4 全部独立复验通过）｜ 硬依赖：TASK-008（双实现已存在）｜ soft 依赖：TASK-015A（选型报告）
> 建议分支：`feature/task-046_<你的缩写><MMDD>`
> 交付物所有权：
> - `core/zace_core/embedding/registry.py`（**仅** API 模型条目的 key / 别名与上限）
> - `core/zace_core/embedding/factory.py`（**仅** API 分支的 spec 解析与上限默认值）
> - `core/zace_core/embedding/api.py`（**仅** 若别名替换必须在发送前发生）
> - `core/tests/embedding/**`（新增/调整测试）
> - `docs/handbook/getting-started/cloud-embedding.md`（**新建**：用户照做能跑通的完整命令序列）
>
> 清单外文件不得改。**尤其不得改** `docs/contracts/**`、`core/zace_core/interfaces.py`（`EmbeddingProfile`
> 字段与 `EmbeddingProvider` 签名是 CF-09 冻结）、`core/zace_core/embedding/local.py`（本地钳制属 TASK-038）。

## 背景（编排者 2026-09-13 在本机实测，全部为真实输出）

用户在换环境后拍板：**当前开发期全程使用云端 embedding**（硅基流动 `BAAI/bge-m3`，免费、1024D、
8192 token 上限），本地 ONNX 路线暂缓（"预留接口、以后有空再完善"）。
但实测发现**照官方文档配置跑不通**，且存在两处会把长文档静默截断的缺陷。

### 实测证据（编排者已复现，实施 AI 应能复现同样结果）

```console
# 1) registry 里登记的裸名 → API 明确拒绝
$ curl -s -X POST https://api.siliconflow.cn/v1/embeddings \
    -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
    -d '{"model":"bge-m3","input":["test"]}'
{"code":20012,"message":"Model does not exist. Please check it carefully.","data":null}

# 2) 官方文档的 model 名 → registry 拒绝（未登记）
$ EMBED_MODE=api EMBED_MODEL=BAAI/bge-m3 EMBED_BASE_URL=https://api.siliconflow.cn \
    EMBED_API_KEY=$KEY uv run zace-core ingest --repo <repo> --data <data>
zace-core: embedding provider 不可用：EmbeddingConfigError: 未登记的 API 模型 'BAAI/bge-m3'：
必须显式提供 dim（EMBED_DIM），否则 profile.dim 会失真并破坏 D-07 指纹；
已登记模型：['bge-m3', 'text-embedding-3-large', 'text-embedding-3-small']

# 3) 唯一可行路径（同时给全名 + dim）能跑通：
$ EMBED_MODE=api EMBED_MODEL=BAAI/bge-m3 EMBED_DIM=1024 EMBED_BASE_URL=https://api.siliconflow.cn \
    EMBED_API_KEY=$KEY uv run zace-core ingest --repo <repo> --data <data>
project: c88a9bf77a642203
chunks: new=7 reused=0 removed=0
vectors: upserted=7 deleted=0
elapsed: 0.8s
```

```text
# 4) 上限不一致：走"未登记模型"分支时 profile 拿到 2048，而 bge-m3 实际支持 8192
profile: EmbeddingProfile(model_id='api:BAAI/bge-m3', dim=1024, max_input_tokens=2048)

# 5) 但 API 侧确实能吃 8192：8000 token 输入 0.27s 成功（编排者实测，用 8192 上限的 spec 直接构造）
  2000 词 (~2000 token): OK 0.23s dim=1024
  8000 词 (~8000 token): OK 0.27s dim=1024
```

### 为什么必须修（不是洁癖）

- **F1 阻断**：用户只有"全名 + 显式 dim"这一条路可走，而这条路**不在任何文档里**；
  照官方文档填全名的标准做法会得到一句"未登记的 API 模型"，指向一个**同样不可用的** `bge-m3`。
- **F2 静默损失**：2048 vs 8192 差 4 倍。`Module/01 §2.4` 的截断口径本就是 2048（为本地小模型设的），
  但**云端模型能力更强**，继续用 2048 会让长文档（设计文档、大函数）的尾部证据永久缺失，
  且用户**无从察觉**（不报错、不告警）。
- **成本已核实**：BAAI 系列在硅基流动为免费档；付费档为 ¥0.07/M tokens 量级。
  按 10 人日常用量远低于用户设定的"月 10 元"预算（详见 `docs/plan/phase2-m2b-w6.md` §4）。

## 输入文档（按序读，只读所需章节）

1. `docs/plan/phase2-m2b-w6.md` §2.3（实测数字）/ §2.4（F1-F3）/ §3.2（本卡定位）
2. `docs/design/INDEX.md` 的 **D-44**（embedding 双实现）、**D-07**（三级指纹失效）
3. `core/zace_core/embedding/registry.py`（`ApiModelSpec` / `API_MODELS` / `find_api_spec`）
4. `core/zace_core/embedding/factory.py`（`_create_api` 的分支与 `UNKNOWN_API_MAX_INPUT_TOKENS`）
5. `core/zace_core/embedding/api.py`（请求体构造：`{"model": self._spec.name, ...}`）
6. 硅基流动官方文档（**只读参考**，不要照抄其 model 名作为 zace 的配置值）：
   `https://api-docs.siliconflow.cn/docs/api/embeddings-post`
   —— 关键事实：`BAAI/bge-m3` 上限 8192；`Qwen/Qwen3-Embedding-*` 上限 32768 且支持 `dimensions` 降维

## 冻结接口（本卡不得变更）

- **消费**：CF-09（`EmbeddingProfile` 字段：`model_id` / `dim` / `max_input_tokens`）、
  `ApiModelSpec` 的既有字段名、`OpenAiCompatibleEmbeddingProvider` 的构造签名。
- **产出（本卡要定下来的语义）**：
  - **一个可用的配置写法**：`EMBED_MODEL` 必须能接受用户从官方文档抄来的 model 名；
  - **别名到实际 model 名的映射**必须在**发请求前**完成（API 收到的必须是 provider 认的名字）；
  - **`profile.model_id` 必须能区分 provider**（它进 `index_config` 指纹，决定是否触发 D-07 二级失效）。

## 交付内容

### §A F1：让硅基流动的模型名真正可用（**本卡核心**）

两条路线**择一**，在"执行记录"写清选了哪条与理由：

- **(a) 别名解析（建议）**：registry 保留 `bge-m3` 作 key，新增"别名 → 实际 model 名"字段或映射表；
  `api.py` 发请求时用实际名，`profile.model_id` 用能区分 provider 的稳定标识。
  **优点**：不破坏既有配置（`EMBED_MODEL=bge-m3` 曾经"看起来能用"）；能容纳多家 provider 的同名模型。
- **(b) 改用全名作 key**：`API_MODELS` 的 key 改为 `BAAI/bge-m3`。
  **代价**：既有用户的 `EMBED_MODEL=bge-m3` 配置**静默失效**（会变成"未登记模型"→ 要求显式 dim）。

**必须同时满足**：

1. `EMBED_MODEL=BAAI/bge-m3`（照官方文档抄）→ **开箱可用**，无需 `EMBED_DIM`；
2. `EMBED_MODEL=bge-m3`（旧配置）→ **行为可读**：要么仍然可用（路线 a），
   要么给出**指明正确写法的**错误（路线 b，错误信息必须包含 `BAAI/bge-m3`）；
3. 未登记模型 + 无 dim → 保持现有行为（报错要求 `EMBED_DIM`，理由：D-07 指纹会失真）；
4. **provider 区分**：若未来同时登记 OpenAI 的 `text-embedding-3-small` 与别家的同名模型，
   `model_id` 必须能区分（否则换 provider 不会触发重嵌 = D-07 失效）。**在报告里说明你的方案如何满足**。

**测试**（`core/tests/embedding/`）：

- 全名 → spec 命中 + 不需要 dim；裸名 → 按选定路线断言；
- 未登记 + 无 dim → 仍报错（**防止修 F1 时把 D-07 保护拆掉**）；
- 请求体断言：mock `httpx.Client` 抓取 `json=`，断言**发给 API 的 model 字段是 provider 认的名字**
  （这条测试是本卡的"防回归底线"：别名替换必须真的发生在发送前）。

### §B F2：上限默认值改为模型实际能力

- `max_input_tokens` 的默认来源：**已登记模型的登记值**（bge-m3 = 8192）；
  未登记模型才回落 `UNKNOWN_API_MAX_INPUT_TOKENS`（2048）；
- 用户显式给更小值 → **不被抬高**（`min` 语义，不是覆盖）；
- 与 TASK-038 的关系：38 修"本地模型下配置超上限 → ONNX 崩"，本卡修"API 模型默认值偏低"。
  **若你的实现顺带覆盖了 38 的 `min` 语义**（配置值 > 原生上限时钳制 + warning），在报告里说明；
  **但不得修改 `local.py`**（那是 TASK-038 的文件，本卡不碰）。

**测试**：

- bge-m3（全名）+ 不给 `EMBED_MAX_INPUT_TOKENS` → `profile.max_input_tokens == 8192`；
- 显式给 512 → 仍是 512（**不被抬高**）；
- 未登记模型 → 2048；
- `index_config` 指纹用生效值（两次配置不同但生效值相同 → 指纹相同，不触发无谓重嵌）。

### §C F3：key 注入的工程化（文档为主，代码为辅）

**问题**：key 写在 `~/.bashrc` 第 163 行，而第 5-9 行有非交互守卫
（`case $- in *i*) ;; *) return;; esac`）→ **非交互 shell 拿不到**。实测：

```console
$ bash -c  'echo "${zace_embeding_API_KEY:-NO}"'   # → NO（子进程/脚本/CI 的真实处境）
$ bash -lc 'echo "${zace_embeding_API_KEY:-NO}"'   # → NO（登录 shell 也拿不到）
```

**交付**：`docs/handbook/getting-started/cloud-embedding.md`，必须包含：

1. **一条从零到跑通的完整命令序列**（含 `NO_PROXY=127.0.0.1,localhost`；本机设了 `http_proxy`）；
2. **key 注入的推荐做法**（择一写清，并说明为何不依赖 `.bashrc`）：
   - 项目根 `.env`（需确认是否被 gitignore 覆盖）+ `set -a; source .env; set +a`；
   - 或显式 `export` 在每条命令前；
   - 或 service 侧的配置注入（`Settings` / 环境变量，本地模式）；
3. **实测数字**（照抄 §2.4 的表格，并注明是你自己复现的还是引用编排者的——**两者要区分**）；
4. **成本与限流的说明**（免费档、付费档量级、429 的现有处理：`api.py` 已有退避 + `Retry-After`，上限 30s）；
5. **隐私告知**：与 `local.py` 相反，**源码文本会发往第三方**（这是 U1 的自觉选择，
   未来若要"源码不出本机"走 §5 的本地路线）。

**不要**把 key 写进仓库、不要写进测试、不要贴进报告（`redact_text` 已在 service 侧生效，
但文档与执行记录里也必须只出现变量名）。

### §D F4：API provider 的截断与分批（**阻断级，与 §A 并列最高优先级**）

**编排者 2026-09-13 实测发现**：在新靶场 `hello-agents` 上跑全量索引**失败**：

```text
$ EMBED_MODE=api EMBED_MODEL=BAAI/bge-m3 EMBED_DIM=1024 EMBED_BASE_URL=https://api.siliconflow.cn \
    EMBED_API_KEY=$KEY uv run zace-core ingest --repo /home/xuwenzheng/github/hello-agents --data /tmp/zace-ha
zace-core: ApiRateLimitError: embedding 被限流（HTTP 429，endpoint=.../v1/embeddings，已尝试 3 次）；
           响应体片段：{"message":"Request was rejected due to rate limiting. Details: TPM limit reached.","data":null}

# 失败后落库状态：解析完成、向量为空（正是 R41 的“静默清空”形态）
$ # files=1482  chunks=9971  symbols=4571  vectors=0
$ uv run zace-core search "ReAct 范式是怎么实现的？" --repo ... --data /tmp/zace-ha
warning: 向量索引为空（可能未重建）：chunks=9971，vectors=0
```

**根因一（正确性）：`api.py` 没有截断，与 `local.py` 不一致**

| 位置 | 行为 |
|---|---|
| `local.py:231-233` | tokenizer 编码后按 `spec.max_input_tokens` **硬截断**（`_encoding_row(enc, max_tokens)`） |
| `api.py` | **没有任何 tokenizer / 截断代码**；`max_input_tokens` 只写进 `profile`（指纹），**不参与推理** |

实测后果：**182 / 9971 个 chunk 超过 8192 token**（最大 **64138** token，来自 `Extra-Chapter/Extra01-参考答案.md`），
单个超长输入被 API 拒绝：

```text
$ curl -d '{"model":"BAAI/bge-m3","input":["word " * 9000]}' ...
{"code":20015,"message":"The parameter is invalid. Please check again.","data":null}
```

**根因二（成本/稳定性）：`iter_batches` 按“条数”分批，不看 token 总量**

`base.py:75-80` 的 `iter_batches(items, batch_size)` 只按索引切分。`hello-agents` 的 chunk token 分布是
**p50=147 / p90=1052 / p99=12978 / max=64138**——即一个 64 条的 batch 完全可能携带**几十万 token**，
一次性把 TPM 配额耗尽。实测参考（编排者本机）：

| 探测 | 结果 |
|---|---|
| 短文本持续压测（64×200 token） | ~858 K token/min 可持续（无 429） |
| 全库嵌入总需求 | **~5.59 M token**（按 8192 截断估算） |
| 因此若要在 60 分钟内跑完 | 只需 ~93 K token/min——**远低于可持续速率** |

即：**限流不是绝对容量不够，而是“批次 token 总量不可控”导致的尖峰**。

**交付（三条都要，并在报告里贴实测）**：

1. **截断（与本地一致）**：API 侧提供按 token 的截断，上限取 `spec.max_input_tokens`（F2 修好后即模型能力）。
   **实现选择说明**：可用 `tokenizers` 库（已是现有依赖？**先核实 `core/pyproject.toml`**，不是则在报告里申请）；
   **若不愿引入 tokenizer**，退路是“按字符数估算截断”（如 4 字符 ≈ 1 token）——
   必须**在报告里写明选择与误差风险**，并且**不得让超长输入未经处理直达 API**。
2. **按 token 预算分批**：batch 的切分依据从“条数”改为“**累计 token 预算**”（如 8192 或更小），
   同时保留条数上限。注意：**本地 provider 不应受此影响**（它自己会截断；两者语义要在报告里写清）。
3. **限流韧性（至少验证，不要求重写现有退避）**：
   - 现有 `api.py` 已有 429 退避 + `Retry-After`（上限 30s）+ 最多 2 次重试；
   - **测试**：mock 一个 429 后成功的响应，断言会重试并最终成功；mock 持续 429，断言抛出 `ApiRateLimitError`
     （**不得无限重试**）；
   - **可选增强**（若你判断必要，在报告里说明）：429 时的退避时长与 batch 自适应降级（拆小重试）。
4. **失败可恢复性（评估，不一定实现）**：本次实测暴露“索引失败后 chunks 已入库、vectors=0”——
   好消息是**重跑增量应能续上**（TASK-014 已验证内容hash 复用）。**请实测验证这一点**并把命令与输出写进报告；
   若重跑会从头再来，**在报告里如实指出**（那是另一个需要立卡的缺陷，本卡不擅自修）。

**测试（`core/tests/embedding/`）**：

- 超长输入（构造 > 上限的文本）→ **不报 400**，且嵌入成功（断言截断生效）；
- batch 切分：构造长度悬殊的输入列表，断言**每个 batch 的累计 token 不超预算**；
- 429 重试/最终失败（mock，见上）。

**本节的端到端验收**（与 §D 原条合并）：在 `hello-agents` 上**完整跑完一次 ingest**
（全量或至少覆盖那 182 个超长 chunk），并贴上 `files / chunks / vectors / elapsed` 与 `warning` 是否消失。
**这是本卡最重要的验收证据。**

## 验收标准（DoD）

- [ ] `EMBED_MODEL=BAAI/bge-m3`（无 `EMBED_DIM`）能完成 ingest + search（**这是用户的主路径**）；
- [ ] §A 的 4 条测试全绿，其中"请求体 model 字段"的断言必须存在；
- [ ] §B 的 4 条测试全绿（含"不被抬高"与"指纹用生效值"）；
- [ ] **§D 的截断与分批测试全绿**（超长输入不报 400 / batch token 预算 / 429 重试与最终失败）；
- [ ] **§D 端到端：在 `hello-agents` 上完整跑完一次 ingest**，贴 `files/chunks/vectors/elapsed` 与
      `warning: 向量索引为空` 是否消失（**本卡最重要的证据**）；
- [ ] §C 的手册存在，命令序列**由实施 AI 本机跑过**（贴输出；引用编排者数字要标注来源）；
- [ ] 基线三条全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、
      `uv run pytest`（**注意**：本仓 `addopts=-q` 会吞掉汇总行，需用 `uv run pytest -o addopts="" -q` 看数字）；
- [ ] 任务卡"执行记录"已回填；任务板对应行状态改 `review`。

## 明确不做

- **不改代码默认值**：`EmbeddingConfig.mode` 的默认仍是 `"local"`（D-44）。把 api 变默认是一次 **L3 决策**
  （影响指纹与既有索引），归 `docs/plan/phase2-m2b-w6.md` §5 的"未来任务锚点"。
- **不碰 `local.py`**（TASK-038 的领地）；不做本地 ONNX 的任何完善（U2：预留接口即可）。
  但注意：**§D 的截断语义应与 `local.py` 保持一致**（消费其行为，不修改它）。
- **不引入与 §D 无关的新依赖**；**§D 所需 `tokenizers>=0.20` 已是 `core/pyproject.toml` 的正式依赖**（已核实），
  因此 API 侧实现按 token 截断**无需新增依赖**（不得引入 provider 专属 SDK）。
- 不做 provider 故障切换 / 多 provider 并行（§5 锚点）。
- 不做索引断点续跑的重构（§D-4 只要求**实测验证**当前行为并如实报告）。
- 不调检索质量参数（R29/R30 冻结）。
- 不改 `docs/contracts/**`（若判断需要改 CF-09，走 L2 流程：在"执行记录"申请后停下）。

## 参考源码锚点（只读）

- `core/zace_core/embedding/factory.py`：`_create_api`（未登记分支必须显式 dim 的保护逻辑）
- `core/zace_core/embedding/registry.py`：`API_MODELS`（`bge-m3` 条目已写 `dim=1024, max_input_tokens=8192`）
- `core/zace_core/embedding/api.py`：`_embed_batch` 的 `{"model": self._spec.name, ...}`
- `core/zace_core/embedding/base.py`：`EmbeddingConfigError` 等异常语义（403/429/网络已分类）
- `service/zace_service/routers/ops.py`：`_probe_embedding_provider`（healthz `deep=1` 会真的探测）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写，**必须包含**：

- F1 选了哪条路线（a/b）与理由；
- `profile.model_id` 如何区分 provider 的说明（D-07 相关）；
- 本机实测的 profile 输出（`max_input_tokens` 的生效值）；
- F3 的 key 注入推荐做法与理由。

## 执行记录

### 2026-09-13 ｜ 分支 `feature/task-046_xwz0913`（基于 main `3cc760c`）

**总览**：F1（别名解析，路线 a）、F2（上限取模型实际能力 + `min` 语义）、F4（按 token 截断 + 按 token 预算
分批）已实现；F3 手册已落地。F1/F4 双阻断项均已消除，`hello-agents` 全量 ingest **首次跑通**。

---

#### 1. F1 路线选择与理由（选了 **(a) 别名解析**）

`registry.py` 新增 `ApiModelSpec.request_name`（发给 API 的 model 字段）与 `API_MODEL_ALIASES`
（`BAAI/bge-m3` → `bge-m3`），`find_api_spec()` 先查 key 再查别名。

理由：

1. **不破坏既有配置**：`EMBED_MODEL=bge-m3` 仍可用（路线 b 会让它静默变成"未登记模型"）；
2. **够容纳同名模型**：key 是「哪家的哪个模型」的稳定标识，将来 OpenAI 的 `text-embedding-3-small`
   与别家同名模型可以靠 key 区分；
3. **职责单一**：别名替换只发生在「发请求前」，其它路径（指纹、日志、错误信息）一律用 key。

`profile.model_id` **用注册表 key**（`api:bge-m3`），不用 `request_name`。理由：key 才能区分 provider——
换 provider（同名模型）会改 key → 改指纹 → 触发 D-07 二级失效（重嵌）；而改写法（`bge-m3` ↔ `BAAI/bge-m3`）
指纹不变，**不会**触发无谓重嵌。两个方向都正确。

实测：

```console
EMBED_MODEL='BAAI/bge-m3' -> model_id=api:bge-m3 dim=1024 max_input_tokens=8192 api_model='BAAI/bge-m3'
EMBED_MODEL='bge-m3'      -> model_id=api:bge-m3 dim=1024 max_input_tokens=8192 api_model='BAAI/bge-m3'
```

#### 2. F2 上限默认值

- 未给 `EMBED_MAX_INPUT_TOKENS` → 取**模型登记值**（bge-m3 = 8192）；未登记模型才回落
  `UNKNOWN_API_MAX_INPUT_TOKENS`（2048）；
- 给更小值 → 尊重（`min` 语义）；
- 给**大于**模型能力的值 → 钳回 8192 + `UserWarning`（**顺带覆盖了 TASK-038 的 `min` 语义**，
  但**未碰 `local.py`**——它仍是 TASK-038 的领地；本卡的钳制在 `factory.py` 的 API 分支内）。
  实测：`max_input_tokens=99999` → 钳为 8192 并 warning。

指纹用的是**生效值**（`replace()` 之后才进 `EmbeddingProfile`），所以"配置不同但生效值相同"不会重嵌。

#### 3. F4 截断与分批（实现方式与选择理由）

**截断选择：用 tokenizer（精确），带字节退路。**

- `tokenizers>=0.20` 已是 `core/pyproject.toml` 正式依赖（已核实，非新增）；
- 为 bge-m3 在 registry 登记 `tokenizer_repo_id="BAAI/bge-m3"`，provider 惰性加载（HF 缓存）；
- **拿不到 tokenizer 时**回落按 **UTF-8 字节数**截断：byte-level BPE 每 token ≥ 1 字节，
  故字节数是 token 数的**安全上界**——代价是英文欠填（~4 字节/token），但**绝不把超长输入发给 API**。
- **不选"4 字符 ≈ 1 token"估算**：对 CJK 会低估（中文约 1 字符/token），超限风险不可控。

**实现中发现并修掉一个真 bug**（值得评审注意）：最初的"解码→重编码→再解码"回验循环在边界抖动下
**不收敛**（每轮只退 2 token，重编码又回到同长），8 次耗尽后退到字节退路 → **中文长文档被砍到
1984/8192 token**（比不截断更糟）。改为**对原始 ids 递减切片**（每轮至少退 1 token，单调收缩）后，
实测稳定填满 8191/8192。

**分批选择：累计 token 预算 + 条数上限取先到者**（`DEFAULT_BATCH_TOKEN_BUDGET = 8192`，用于 64 条上限）。
单条超预算的输入单独成批（不拆、不丢、不死循环）。**本地 provider 不受影响**（它按 token 自截断，
批语义由 ONNX 侧决定）——两者语义一致：都是"发往模型前按 token 上限处理"。

#### 4. 实测数字（实施 AI 本机复现，2026-09-13）

| 探测 | 结果 |
|---|---|
| 裸名 `bge-m3` | `{"code":20012,"message":"Model does not exist..."}` |
| 全名 `BAAI/bge-m3` | `200 OK`，dim=1024，0.22s |
| **单条 token 上限** | **8192 token → 200（0.37s）；8193 token → `400 code=20015`** |
| 超长输入截断后 | 337737 字符 → 截为 8191 token，嵌入成功（无 400） |
| 前缀重复输入 `'word ' * N` | N≥800 时挂起/500 —— **探针假象**，真实文本无此现象 |

> **口径校正（与卡内 §2.4 的差异）**：卡内记「8000 token 输入 0.27s 成功」，本机复测确认
> **8192 是真实上限**（8192 OK / 8193 400），故 F2 默认值取 8192 正确。但卡内
> 「默认 2048 导致长文档静默截断」在修复后不再成立——截断真实发生且按 8192 执行。

#### 5. §D 端到端：`hello-agents` 完整 ingest（**本卡最重要证据**）

修复前（复现编排者结论）：

```console
$ EMBED_MODE=api EMBED_MODEL=BAAI/bge-m3 EMBED_DIM=1024 ... uv run zace-core ingest --repo .../hello-agents --data /tmp/zace-ha
zace-core: ApiRateLimitError: embedding 被限流（HTTP 429 ... 已尝试 3 次）
# 落库：files=1482 chunks=9971 vectors=0
$ uv run zace-core search "ReAct 范式" ...
warning: 向量索引为空（可能未重建）：chunks=9971，vectors=0
```

修复后（**`EMBED_MODEL=BAAI/bge-m3`，无 `EMBED_DIM`**——即用户主路径）：

```console
$ unset EMBED_DIM; uv run zace-core ingest --repo .../hello-agents --data /tmp/zace-ha3
project: e9ee9dd1d41a7d2c (created)
mode: incremental (invalidation=none)
files: added=1482 modified=0 deleted=0 parsed=1482
chunks: new=9971 reused=0 removed=0
vectors: upserted=9971 deleted=0
graph: edges_retargeted=3768 unresolved_resolved=69 spec_refs=20358 ambiguous=4081
skipped: 380 个二进制/不可解码文件
elapsed: 290.2s
```

`search` 侧：**`warning: 向量索引为空` 已消失**，命中项含 `vector 0.6316 + vector rank 13` —— 向量通道真的生效。

#### 6. §D-4 失败可恢复性（实测，未改代码）

对**失败库**（`/tmp/zace-ha`：chunks=9971、vectors=0）重跑：

```console
mode: incremental (invalidation=full_reparse)
files: added=1482 modified=0 deleted=0 parsed=1482
chunks: new=0 reused=9971 removed=0     ← 解析/切块未重做
vectors: upserted=9971 deleted=0        ← 只有向量重算
elapsed: 347.8s
```

**结论：能续上**。chunks 全部 `reused`（内容 hash 复用，TASK-014 语义成立），只重算向量。
注意指纹判为 `full_reparse`——因为原失败库的 `index_config` 指纹与本次（`max_input_tokens` 2048 → 8192）不同，
属于 D-07 的**正确**行为，不是缺陷。另外对已成功的库重跑是**幂等**的（`added=0 new=0 upserted=0`，1.4s）。

#### 7. ⚠️ 与卡内 §D 前提的两处实测偏差（**请编排者重点看**）

修复后回查数据，发现卡内 §D 对 F4 的**两个根因表述在本靶场上不成立**：

**(1) “超长 chunk 直达 API 导致 400” —— 通过正常流水线不可达。**

真正送嵌入的是 `embedding_text()`，而它受字符级 `EMBEDDING_BODY_MAX_CHARS=8000` 截断。实测：

| 口径 | p50 | p90 | p99 | max | >8192 的条数 |
|---|---|---|---|---|---|
| `chunks.content`（卡内量的是这个） | 147 | 1052 | 12978 | **64138** | **182** |
| `embedding_text()`（**真正发出去的**） | 162 | 1080 | 3814 | **4882** | **0** |

那 182 条超大 chunk 经 `embedding_text()` 后 max 仅 4882 token，**无一条超 8192**。卡内的 400 探针
是把 `content` 直发 API 得出的，不是流水线行为。

**(2) “批 token 尖峰（几十万）触发 TPM 429” —— 在本靶场不成立。**

按 `embedding_text` 实测：

| 分批方式 | 批数 | 单批最大 token | 单批平均 token |
|---|---|---|---|
| 旧（按条数 64） | 156 | **106,330**（非“几十万”） | 27,740 |
| 新（预算 8192） | 595 | 8,192 | 7,273 |

且**两种方式的总 token 完全相同（4,327,564）**，所以按 token 预算分批**不减少总量**，
因而不可能是“修好后 429 就消失”的原因。

**那么 429 到底是什么？——是共用 key 的配额竞争。**

时间线证据：修复前后代码相同的情况下，本机前期反复 429（41s / 164s 失败），而在泳道 A/C 的
索引与 eval 进程停止后，**同一命令一次跑通（290s）**。即：

> 429 的成因是**多个泳道/进程共用同一个 API key** 抢占配额，**不是**批尖峰、
> **也不是** zace 的代码缺陷。

**这不意味着 F4 无用**：

- 截断仍是**真实潜在缺陷**的修复：任何直接调 provider 的调用方（或将来调大
  `EMBEDDING_BODY_MAX_CHARS`、或换更小上限的模型）都会撞上 400；现在不会了。
- 截断还修掉了一个**真实存在的 Bug**（见 §3 的“回验不收敛导致中文被砍到 1984/8192”）。
- 按 token 预算分批使单批成本**有界且可预测**（8192而非106K），对限流容忍度与失败重试粒度都更好。
- **代价**：请求数从 156 升到 595。RPM 侧仍充裕（约 2 req/s，远低于 2000 RPM），但
  总耗时可能略微增加（本次全量 290s）。

**建议**：卡内 §D 的“根因一/根因二”措辞建议由编排者按上表修正；另建议为“多进程配额协调”单独立卡。

#### 8. 关于 429 的现场发现（补充）

免费档 bge-m3 公开数据为 2000 RPM / 500,000 TPM；但本机全量实测 4.33M token / 290s ≈ **890K token/min**，
**高于**该 TPM。说明要么实际配额更高，要么 TPM 非严格按每分钟切窗执行。因此单进程不是问题，
**多进程并行会互相挤兑**。已写入手册 §4.3 排查顺序。

#### 9. F3 推荐的 key 注入方式

**推荐：项目根 `.env` + `set -a; source .env; set +a`。**
理由：不依赖 shell 类型（`.bashrc` 有非交互守卫，子进程/脚本/CI 一律拿不到，本机已复现）；
一条 `source` 对所有后续命令生效；`.env` 已被 `.gitignore` 第 30–32 行排除（`.env.example` 可提交）。

**不推荐 `.bashrc`**：非交互进程拿不到（实测 `env -i bash -c ...` 与 `env -i bash -lc ...` 均为空），
且把 key 与项目的绑定关系藏在 shell 配置里，换机器即失效。

手册：`docs/handbook/getting-started/cloud-embedding.md`（§2 完整命令序列、§3 实测数字区分来源、§4 行为说明、§5 隐私告知、§6 排查表）。

#### 10. 验收命令与结果

```console
$ uv run pytest core/tests/embedding -o addopts="" -q
100 passed, 1 skipped in 1.09s
$ uv run pytest -o addopts="" -q
694 passed, 2 skipped, 1 warning in 13.76s
$ uv run ruff check .
All checks passed!
$ uv run python scripts/check_dependency_direction.py
依赖方向检查通过（core 纯库 / service 不上探）。
```

#### 11. 契约影响 / 与设计偏差 / 未决问题

- **契约影响：无**。未改 `docs/contracts/**`、`interfaces.py`、`EmbeddingProfile` 字段与
  `EmbeddingProvider` 签名（CF-09）。新增的只是 `ApiModelSpec` 的**新字段**（`request_name`、
  `tokenizer_repo_id`）与模块级常量——`ApiModelSpec` 不是冻结契约（冻结的是字段**名**的既有部分）。
- **与设计偏差：无**。`EmbeddingConfig.mode` 默认仍是 `local`（D-44）；未碰 `local.py`。
- **未改 `service/zace_service/config.py`**：核实后**无必要**——service 通过进程环境间接使用
  `EmbeddingConfig.from_env()`，key/模型名走 `EMBED_*` 环境变量即可，无需 service 侧新增配置项。
- **未决问题**：
  1. **卡内 §D 的两处根因表述与本靶场实测不符**（见 §7）——已如实记录，**未静默偏离设计**；
     请编排者裁定是否需要修正卡内措辞。
  2. **429 的根因是多进程共用 key**（见 §8）。若未来要“多泳道并行索引”，需要一个**进程间配额协调**
     或按泳道发放不同 key —— 建议立卡，本卡不擅自扩范围。
  3. 手册 §3.2 引用编排者的 token 分布数字未由本实施 AI 独立复现（已在本节 §7 用**两种口径**
     重新量化并标注差异）。
  4. **字符级上界 `EMBEDDING_BODY_MAX_CHARS=8000` 是实际生效的截断层**，对 CJK 可能先于 token 截断
     生效（8000 字符中文 ≈ 8000 token）。当前不构成缺陷（token 截断仍在 provider 侧兜底），
     但它意味着“长文档尾部证据”实际由**字符上界**决定而非模型能力（8192）——建议评估是否立卡。

