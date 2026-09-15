# TASK-008：Embedding Provider 双实现（本地 ONNX 默认 + API 可选）

> 状态：done ｜ 阶段：Phase 1 ｜ 硬依赖：无 ｜ soft 依赖：无
> 建议分支：`feature/task-008_<你的缩写><MMDD>`
> 交付物所有权：`core/zace_core/embedding/`、`core/tests/embedding/`
> 依据：D-44（本地默认 + API 可选双实现）、D-07（embedding 变更触发二级失效）。

## 目标

交付 `EmbeddingProvider`（CF-09）两个实现：本地 ONNX（默认，源码不出本机）与
OpenAI-compatible API（可选配置）；两者的 `EmbeddingProfile` 写入 `index_config` 作为指纹。
最终默认模型由 TASK-015 bake-off 决定，本卡提供候选注册表与统一接口。

## 输入文档（按序读）

1. `docs/design/Module/01-切片存储.md` §2.4（embedding 截断 2048 token 假设）、§4.2（指纹）
2. `core/zace_core/interfaces.py`（`EmbeddingProvider` / `EmbeddingProfile` 冻结）
3. `docs/design/Background/04-gitnexus.md` §3（arctic-embed-xs 384D 本地 ONNX 先例）、
   `docs/design/Background/05-implications-for-zace.md` §7（本地 embedding 选型证据）

## 交付内容

### A. 通用

- 输出**单位向量**（L2 归一化后返回；向量库按余弦检索，冻结此行为）。
- `profile.model_id` 命名：`local:<model_slug>` / `api:<model_name>`；`dim` 与 `max_input_tokens` 来自模型注册表。
- 批量：`embed(texts)` 内部按 batch_size（本地默认 16、API 默认 64）分批；对空输入返回空列表。

### B. 本地实现（`local.py`，默认）

- onnxruntime + tokenizers；模型文件经 `huggingface-hub` 下载到缓存目录（支持离线本地目录配置）。
- **模型适配注册表**（候选，供 TASK-015 对比选择）：
  | slug | 维度 | 池化 | 前缀约定 |
  |---|---|---|---|
  | `multilingual-e5-small`（暂定默认） | 384 | mean | `query: ` / `passage: `（e5 系列必须，否则质量明显下降） |
  | `bge-small-zh-v1.5` | 512 | CLS | 无 |
  | `arctic-embed-xs` | 384 | CLS | 无（英文对照基线） |
- 截断：按 `profile.max_input_tokens`（候选模型默认 512 原生上限；zace 侧 2048 假设见 Module/01 §2.4，最终由 TASK-015 校准）。
- 会话对象可注入（便于测试用 stub session，CI 不依赖网络与大模型文件）。

### C. API 实现（`api.py`，可选）

- OpenAI-compatible `POST {base_url}/v1/embeddings`（httpx）：配置 `EMBED_BASE_URL/EMBED_API_KEY/EMBED_MODEL`，失败重试 ≤2（指数退避）、超时（连接 10s / 整体 60s）；错误分类清晰（鉴权/限流/网络）。
- 不得在日志/异常中出现 API key。
- 说明：此实现下文本会发往第三方（设置页文案由 Phase 4 负责；本卡在 docstring 中注明隐私语义）。

### D. 工厂

- `create_provider(config) -> EmbeddingProvider`：`mode=local|api`、model、路径/URL/KEY 注入；未配置本地模型文件且无网络时给出可读错误。

## 验收标准（DoD）

- [ ] `uv run pytest core/tests/embedding -q` 全绿，**不依赖网络**：
  - 本地：stub ONNX session + 真实 tokenizer 逻辑（可用微型 tokenizer.json fixture）→ 归一化正确（模长≈1）、批大小切分正确、profile 正确；
  - API：mock httpx transport → 请求体（model/input 批）、响应解析、重试与超时路径、key 脱敏；
  - e5 前缀：断言 passage/query 两种输入前缀被正确注入；
  - 空输入、超长输入（超 `max_input_tokens` → 截断不报错）。
- [ ] 手动冒烟（不要求 CI，写入卡内执行记录）：真实下载 `/tmp` 校准模型并 embed 一句中文 + 一句代码，打印维度与耗时。
- [ ] 基线三条命令全绿。

## 参考源码锚点（只读）

- `source/GitNexus/gitnexus/src`（本地 ONNX embedding + 内容 hash 缓存；见 Background/04 §3）
- `source/ragcode/src/semantic/`（可插拔 provider 与 deterministic fallback 的下限保障）

## 明确不做

- 不做 query 侧短期缓存（TASK-010 的职责）；不做 rerank 模型（V1.5）；
- 不做 embedding 缓存落盘（LanceDB 以 content_hash 复用即缓存，TASK-009 负责）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

### TASK-008 完成报告

- **状态**：2026-09-10 完成，本地分支交付（未 push，评审/合并由编排者执行）。
- **分支**：`feature/task-008_xwz0910`（基于本地 `main` = `a0ec2b2`）。
- **关键产物**（均在文件所有权内，未改契约、设计文档与 `core/pyproject.toml`）：
  - `core/zace_core/embedding/__init__.py`：导出面（工厂、双实现、错误类型、注册表）。
  - `core/zace_core/embedding/base.py`：错误分类（`EmbeddingError.kind`）、`iter_batches`、
    `with_prefix`、`l2_normalize`（零向量保持零，不产生 NaN）。
  - `core/zace_core/embedding/registry.py`：`LocalModelSpec` / `ApiModelSpec` + `LOCAL_MODELS` /
    `API_MODELS` + `DEFAULT_LOCAL_SLUG = "multilingual-e5-small"`（暂定，待 TASK-015 校准）。
  - `core/zace_core/embedding/local.py`：`LocalOnnxEmbeddingProvider`（onnxruntime + tokenizers
    + huggingface-hub，惰性加载、可注入 session/tokenizer、离线 `model_dir`/`cache_dir`）。
  - `core/zace_core/embedding/api.py`：`OpenAiCompatibleEmbeddingProvider`（httpx，重试 ≤2/
    指数退避、连接 10s/整体 60s、错误分类、key 全链路脱敏）。
  - `core/zace_core/embedding/factory.py`：`EmbeddingConfig`（含 `from_env`）+ `create_provider`。
  - `core/tests/embedding/`：`conftest.py`（微型 tokenizer + stub ONNX 会话 + 带 padding 夹具）
    与 5 个测试文件；`test_smoke_local_model.py` 为真机冒烟（`ZACE_EMBED_SMOKE=1` 才跑）。
- **契约影响**：无。CF-09（`EmbeddingProvider` / `EmbeddingProfile`）签名/字段/语义未变；
  测试断言 `isinstance(provider, EmbeddingProvider)`。
  实现层新增 `embed_query()` **不在协议内**：E5 系列 query/passage 前缀不同，而 CF-09 的
  `embed(texts)` 没有侧别参数。约定：TASK-007 用 `embed()`（passage 侧），**TASK-010 的向量
  通道必须调 `embed_query()`**（否则查询侧会带上 `passage: ` 前缀、召回质量下降）。
  若编排者希望把侧别写进契约，属于 L2 扩展，建议在 TASK-010 开卡前裁决。
- **与设计偏差**：无（两处口径按卡内执行，另有一处候选仓库选择需知晓）：
  1. `model_id` 命名按卡内 §A `local:<model_slug>`；`interfaces.py` 注释示例写的是
     `local:onnx:<slug>`，两处不一致，实现从卡内（见未决问题 2）。
  2. 卡内 §B 的 `bge-small-zh-v1.5`：官方 `BAAI/bge-small-zh-v1.5` 仓库**没有 ONNX 导出**
     （只有 config/tokenizer），注册表指向 transformers.js 镜像 `Xenova/bge-small-zh-v1.5`
     （含 `tokenizer.json` 与 `onnx/model.onnx`，95MB）；512 维 / CLS 池化的约定不变。
  3. 本地候选的原生上限均为 512（三个仓库 `max_position_embeddings=512`），与 Module/01 §2.4
     的 2048 token 假设不冲突：卡内已写明"候选模型默认 512 原生上限，最终由 TASK-015 校准"。
- **未决问题**：
  1. `embed_query()` 是否升格为契约 L2（影响 TASK-010 调用面），需编排者裁决。
  2. `local:onnx:<slug>` 与 `local:<slug>` 二选一：这是写入 `index_config` 的指纹字符串，
     一旦有项目落库，改命名会触发 D-07 全量重嵌；建议合并前定稿。
  3. 未登记的 API 模型必须显式给 `dim`（未给则报可读错误，避免 `profile.dim` 失真）；
     TASK-015 若用 `api:bge-m3` 以外的模型需先在注册表登记。

### 验收命令与结果

| 命令 | 结果 |
|---|---|
| `uv run pytest core/tests/embedding -q` | **74 passed, 1 skipped** in 0.62s（skip = 真机冒烟，默认不进 CI） |
| `uv run ruff check .` | All checks passed |
| `uv run python scripts/check_dependency_direction.py` | 依赖方向检查通过（core 纯库 / service 不上探） |
| `uv run pytest` | **75 passed, 1 skipped** in 0.87s（含 `core/tests/test_smoke.py`） |
| 真机冒烟 `ZACE_EMBED_SMOKE=1 ... pytest core/tests/embedding/test_smoke_local_model.py -q -s` | 两个候选模型各 1 条用例通过（详见下节） |

用例分布：`test_api_provider.py` 21、`test_local_provider.py` 22、`test_factory.py` 16、
`test_registry.py` 9、`test_base.py` 6。CI 全程不联网：stub ONNX 会话 + 微型 `tokenizer.json`
（`tokenizers` 现场构造）+ `httpx.MockTransport`；离线/缺文件错误路径用 `offline=True` 走本地判定。

### 真机冒烟（不要求 CI；模型/维度/耗时记录，供 TASK-015 复用）

- **机器规格**：WSL2（内核 5.15.167.4-microsoft-standard-WSL2）/ Ubuntu 24.04.3 LTS；
  CPU 12th Gen Intel i9-12900H（WSL 可见 6 vCPU）；RAM 15GiB；Python 3.12.3、
  onnxruntime 1.29.0、tokenizers 0.23.2、numpy 2.5.3。
- **样本**：中文 `token 过期后在哪里刷新`、代码 `def refresh_token(self) -> str:`。
- **模型缓存**：`/tmp/zace-embedding-cache`（**未进仓库**；`git status` 仅含交付物两个目录）。

| slug | 仓库 / 文件 | 大小 | 冷启动（含下载） | 热加载 | 批 2 passage | 单条 query | 维度 | 池化 | 前缀生效 |
|---|---|---|---|---|---|---|---|---|---|
| multilingual-e5-small（暂定默认） | `intfloat/multilingual-e5-small` `/onnx/model.onnx` | 470,268,510 B | 360.5s | 2.54s | 18ms | 6ms | 384 | mean | 是（passage/query 余弦 0.958215） |
| arctic-embed-xs（英文对照） | `Snowflake/snowflake-arctic-embed-xs` `/onnx/model.onnx` | 90,387,631 B | 99.8s | 1.37s | 9ms | 6ms | 384 | CLS | 无前缀约定（余弦 1.000000） |

两个模型的"单条 vs 批内"余弦均为 **1.000000**（批组合不影响向量，见下条回归）。

### 真机发现并修复的回归（重要，TASK-015 请留意）

`Snowflake/snowflake-arctic-embed-xs` 的 `tokenizer.json` **自带 padding 与 truncation**
（`padding={pad_id:0,...}`、`truncation={max_length:512}`），`encode_batch` 返回的 `ids` 尾部
已含 pad；最初实现按 `len(ids)` 重建全 1 掩码，导致 pad 被当作真实 token：CLS 池化下同一文本
"单条 vs 批内"余弦只有 0.945203（向量随批组合漂移）。改为沿用 tokenizer 自带的 `attention_mask`
后恢复 1.000000；新增 `padded_tokenizer` 夹具与回归单测锁定行为。
对照：`intfloat/multilingual-e5-small` 的 `tokenizer.json` 无 padding/truncation（ragged 输出，
由 provider 自行 padding），mean 池化下同样稳定在 1.000000。
→ 建议 TASK-015 对比候选时逐仓库检查 `tokenizer.json` 的 padding/truncation 配置。

### 实现口径补充（供下游卡片）

- `EmbeddingProfile.model_id`：`local:multilingual-e5-small` / `api:bge-m3`；`dim` 与
  `max_input_tokens` 全部来自 `registry.py`（TASK-015 改默认值只需改该文件）。
- 截断：按 `profile.max_input_tokens` 对 token 序列硬截断（超长不报错）；真实 e5 样本
  13 token 未触发截断，边界由单测覆盖。
- API 错误分类：`ApiAuthError`(401/403，不重试) / `ApiRateLimitError`(429 重试耗尽，
  尊重 `Retry-After`，上限 30s) / `ApiNetworkError`(超时/传输) / `ApiResponseError`(状态码、
  结构、行数、非 JSON) / `EmbeddingDimMismatchError`(维度不符)；key 在异常、`repr`、
  响应体片段中均被脱敏（有单测断言）。
- 无新增依赖：`onnxruntime` / `tokenizers` / `huggingface-hub` / `httpx` / `numpy` 已在
  `core/pyproject.toml` 预置，本卡未改任何 pyproject。

### 建议复核点

1. `embed_query()` 的对外语义与 TASK-010 的调用约定（未决问题 1）；
2. `model_id` 命名定稿（未决问题 2）——影响 `index_config` 指纹稳定性；
3. `registry.py` 的候选仓库坐标与 `bge-small-zh-v1.5` 走镜像仓库的选择；
4. `_encoding_row` 沿用 tokenizer 自带掩码这条不变量是否有遗漏场景（已用真机 + 单测双覆盖）。
