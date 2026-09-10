# TASK-008：Embedding Provider 双实现（本地 ONNX 默认 + API 可选）

> 状态：pending ｜ 阶段：Phase 1 ｜ 硬依赖：无 ｜ soft 依赖：无
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

（实施 AI 在此填写。真实冒烟的模型/维度/耗时/机器规格必须记录，供 TASK-015 复用。）
