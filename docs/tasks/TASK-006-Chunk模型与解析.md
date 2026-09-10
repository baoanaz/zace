# TASK-006：Chunk 模型 + unresolved 两阶段解析 + 配置指纹

> 状态：pending ｜ 阶段：Phase 1 ｜ 硬依赖：TASK-001 ｜ soft 依赖：TASK-002..005（解析器用 fake `ParsedFile` 即可先行，合并前对齐真实输出）
> 建议分支：`feature/task-006_<你的缩写><MMDD>`
> 交付物所有权：`core/zace_core/chunking/`、`core/tests/chunking/`

## 目标

把 `ParsedFile`（CF-08）变成可入库的 `ChunkDef`（切块规则 + 三通道输入 + hash + id），
并交付 unresolved_refs 的 pending → resolved/failed 生命周期算法与三级配置指纹检测。

## 输入文档（按序读）

1. `docs/design/Module/01-切片存储.md` §2.3、§2.4（chunk 细节）、§4.1、§4.2（增量与分层失效）
2. `docs/contracts/index-schema.sql`（unresolved_refs / index_config 表）
3. `core/zace_core/types.py`、`core/zace_core/hashing.py`
4. `docs/design/Background/02-codegraph.md` §4（unresolved 两阶段模式：pending→resolved(删)/failed(保留重试)）

## 交付内容

### 0. 可直接使用的上游原语（TASK-001 已合并，不要重写）

两阶段解析使用 `Store` 的：`upsert_unresolved` / `unresolved_refs` / `resolve_refs(RefResolution[])` / `mark_refs_failed` / `unresolved_edges` / `retarget_edges` / `add_spec_refs` / `apply_deletions`（已含级联 stale）。语义口径见 `docs/plan/contracts.md` §3.2 R4/R5。

### A. Chunk 切分（输入 ParsedFile → 输出 ChunkDef 列表）

| 语言 | 规则 |
|---|---|
| 通用 | 符号 = 1 chunk（`symbol_kind` 取 function/method/class_skeleton/spec_block/fallback_block）；`chunk_id = {path}:{fqn}:{start_line}`；`content_hash = chunk_content_hash(content)` |
| Python | 函数（装饰器+签名+docstring+体）；类 = 骨架 chunk + 每方法 1 chunk；模块级代码 = 兜底 chunk |
| C/C++ | 函数/结构体/枚举/typedef/宏各 1 chunk；类/结构体带方法 = 骨架 + 方法 chunk |
| Markdown | 每个 `SpecBlockDef` = 1 chunk（symbol_kind='spec_block'，symbol_fqn=heading_path） |
| 兜底 | `fallback=True` 或无解析器：递归字符切分（800 行上限）标 `fallback_block` |
| 三通道 | 存储/FTS 用全文；embedding 输入 = `embedding_text(chunk)` = signature + docstring + 截断体（组装逻辑在此，最终 token 截断由 EmbeddingProvider 按 `max_input_tokens` 执行） |

### B. unresolved 两阶段解析（消费 Store，算法归本卡）

```text
resolve_pending(store)   # 索引后调用
  对每个 pending ref：按 name_tail / name 匹配 symbols
    唯一命中           → 写 edges 行（provenance='parsed'）+ 删 unresolved 行
    多命中             → 同文件优先 → is_exported 优先 → 仍多义：全连（provenance='synthesized'）
                         并在 ResolveReport.ambiguous 记录（供 Missing Evidence 复用）
    无命中             → status='failed'（保留，name_tail 索引）
retry_failed(store, new_symbol_names)   # 新符号出现时只重试相关 failed
```

### C. 配置指纹（D-07 / Module/01 §4.2）

- `parser_config_hash`：解析器版本/配置字典 → sha256；`embedding_profile`：`model_id@dim`。
- `check_fingerprint(store, current) -> Invalidation`（`none / reembed / full_reparse`）与写入函数；
  语义：parser 变 → 全量重解析+重嵌；embedding 变 → 只重嵌；都没变 → 走增量（执行归 TASK-007）。

### D. spec_references 匹配写库（属本卡"解析"职责）

- `mentioned`（TASK-005 产出）→ 与 symbols 表匹配 → 写 `spec_references` 行：fqn 精确匹配优先；同名歧义全挂（宁多勿漏）；`provenance` 永远 `'inferred'`（D-06）；符号删除/改名时级联 `stale=1`（与 TASK-001 的级联路径对齐）。

## 交付物（文件所有权）

| 路径 | 内容 |
|---|---|
| `core/zace_core/chunking/__init__.py` | 导出 |
| `core/zace_core/chunking/splitter.py` | ParsedFile → ChunkDef（含 embedding_text / 兜底切分） |
| `core/zace_core/chunking/resolver.py` | 两阶段解析算法 + ResolveReport + spec_references 匹配 |
| `core/zace_core/chunking/fingerprint.py` | 三级指纹计算与检测 |
| `core/tests/chunking/` | 测试 |

## 验收标准（DoD）

- [ ] `uv run pytest core/tests/chunking -q` 全绿，必须覆盖：
  - chunk_id 格式与重载消歧（同名不同 start_line → 两个 id）；
  - 类 = 骨架 + 方法 chunk；Python 模块级兜底 chunk；
  - `content_hash` 复用语义：改函数体 → hash 变；改文件别处 → 该 chunk hash 不变；
  - **兜底切分**：给一个 fallback ParsedFile（>800 行）→ 切分不超限、块间不重叠错误；
  - 解析器生命周期：pending →（造符号）resolved 边生成 + 行删除；无匹配 → failed 保留；新增符号后 retry_failed 命中；
  - 多义规则：同名两符号（一 same-file、一 exported）→ 连边策略与 ResolveReport 符合上文口径；
  - 指纹矩阵：三组变化（parser 变 / embedding 变 / 均不变）→ 返回正确 Invalidation。
- [ ] 与 TASK-001 的 Store 集成走真实 SQLite（临时目录），不用 mock DB。
- [ ] 基线三条命令全绿。

## 参考源码锚点（只读）

- `source/codegraph/src/resolution/`（name-matcher 可见性规则、import-resolver；见 Background/02 §4）
- `source/codegraph/src/db/schema.sql`（unresolved lifecycle 的表设计对照）
- `source/notace-tool-rs/src/index.rs`（chunking config_hash 思想，仅思想层面对照）

## 明确不做

- 不做向量/检索（007/010）；不做 skeleton 渲染格式（TASK-012 消费 `elidedLines` 语义）；
- 不做跨代 id 稳定性（D-04）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

（实施 AI 在此填写。多义连接规则与 spec_references 匹配口径的最终实现必须记录。）
