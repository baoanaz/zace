# TASK-038：本地 embedding 的 max_input_tokens 钳制与友好报错

> 状态：pending ｜ 阶段：Phase 2（M2b）｜ 硬依赖：无 ｜ soft 依赖：TASK-015A（发现者）
> 建议分支：`feature/task-038_<你的缩写><MMDD>`
> 交付物所有权：`core/zace_core/embedding/{local.py,factory.py,registry.py}`、`core/tests/embedding/**`
> 清单外文件不得改（尤其 `docs/contracts/**`、`core/zace_core/interfaces.py`）。

## 背景（TASK-015A 实测发现，2026-09-10）

泳道 B 在做截断 A/B（`--max-input-tokens 2048`）时实测崩溃：

```text
zace_core.embedding.base.EmbeddingError: 本地 ONNX 推理失败（model=local:multilingual-e5-small）：
Fail("[ONNXRuntimeError] : 1 : FAIL : Non-zero status code returned while running Add node.
Name:'/embeddings/Add_1' ...
Attempting to broadcast an axis by a dimension other than 1. 512 by 947")
```

**根因**：`EmbeddingConfig.max_input_tokens` 覆盖了 `ModelSpec.max_input_tokens`，而本地 provider
按配置值做 token 硬截断（`local.py` 的 `_embed_batch` 用 `self._spec.max_input_tokens`），
**不检查该值是否超过模型原生上限**。e5-small / bge-small-zh / arctic-xs 的原生上限都是 **512**
（`registry.py` 第 73-77 行已注明），给它们配 2048 就会把 947 token 的序列喂进只有 512 位置的模型 → ONNX 崩。

**为什么必须修（不是理论问题）**：
- `docs/design/Module/01-切片存储.md` §2.4 的**假设就是 2048**；用户照设计文档设
  `EMBED_MAX_INPUT_TOKENS=2048`（或未来 TASK-015A 推荐更长的截断）就会踩中；
- 崩溃发生在**索引期批量嵌入**，不是单文件隔离路径 → 会拖垮整次 ingest（TASK-018 §C 的隔离覆盖不到这里）；
- 报错是 ONNX 原始文本，用户无从知道"该模型只支持 512"。

## 交付内容

### §A 钳制（默认行为）

- provider 构造时计算**生效上限** = `min(配置值, 模型原生上限)`（原生上限来自 `ModelSpec`）；
- 生效值与配置值不一致时记一条 **warning 日志**（含模型、配置值、生效值、原因）；
- `EmbeddingProfile.max_input_tokens` 必须是**生效值**（它会写入 `index_config` 指纹 CF-01/D-07）——
  配置 8192 但模型只支持 512 时，指纹里应是 512，这样"改配置不改实际行为"不会触发无谓的 `reembed`。
- 原生上限**不得写死在 local.py**：`registry.py` 已是唯一事实来源（该文件头注释已这么规定）。

### §B 报错友好化（兜底）

- 即使钳制失效（例如未来接入未登记的模型），ONNX 抛错时必须包装成可读信息：
  **模型名 + 原生上限 + 实际序列长度 + 建议**（"该模型原生上限 N，请设置 max_input_tokens ≤ N"）；
- 不得吞掉原始 ONNX 摘要（保留在 message 尾部，便于排查）；
- 批量嵌入失败时，错误里要能看出**是哪个文件/批次**（若上层能提供上下文则透传，否则至少在
  `IngestReport.errors` 里定位到文件——与 TASK-018 的单文件隔离口径一致）。

### §C 单文件隔离复查

核对：**嵌入期**失败是否会被 `Indexer` 的单文件隔离接住？若不会（整次 ingest 中断），
在卡内说明现状并评估是否要修（修则限于 `pipeline/indexer.py`，但**先申请**——那是 TASK-036 的领地）。

## 验收标准（DoD）

- [ ] 测试：`EmbeddingConfig(max_input_tokens=2048)` + e5-small spec → provider 的
      `profile.max_input_tokens == 512`，且有 warning（`caplog` 断言）；
- [ ] 测试：配置值小于原生上限时**不**被抬高（`min` 语义，不是覆盖）；
- [ ] 测试：`index_config` 指纹用生效值（两次配置 512 与 2048 在 e5 上产生**相同**指纹）；
- [ ] 测试：伪造一个超限输入触发 ONNX 失败 → 断言报错文本含模型名、原生上限、建议（**不要求真实跑崩**，
      可用 monkeypatch 让 session 抛错）；
- [ ] 端到端：对 e5-small 配 `EMBED_MAX_INPUT_TOKENS=2048` 跑一个小仓库 ingest **成功**（钳制生效）；
- [ ] 基线三条全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest`
- [ ] 任务卡"执行记录"已回填；任务板对应行状态改 `review`。

## 明确不做

- 不改 `ModelSpec` 的既有数值（原生上限是事实，不是配置）。
- 不动 `EmbeddingProfile` / `EmbeddingProvider` 的字段与签名（CF-09 冻结）。
- 不为 API provider（`api.py`）做同样钳制（它由服务端决定上限，本卡只处理本地 ONNX）；
  但要在报告里说明这一点。
- 不改 `index_config` 的表结构（CF-01）。

## 参考源码锚点（只读）

- `core/zace_core/embedding/local.py`（`_embed_batch` / `profile`）
- `core/zace_core/embedding/registry.py`（第 73-77 行的原生上限事实与"不得写死"纪律）
- `core/zace_core/chunking/fingerprint.py`（`EmbeddingProfile` 如何进指纹）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

（实施 AI 在此填写。）
