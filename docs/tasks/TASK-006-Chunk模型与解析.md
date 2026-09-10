# TASK-006：Chunk 模型 + unresolved 两阶段解析 + 配置指纹

> 状态：review ｜ 阶段：Phase 1 ｜ 硬依赖：TASK-001 ｜ soft 依赖：TASK-002..005（解析器用 fake `ParsedFile` 即可先行，合并前对齐真实输出）
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

### 2026-09-10 ｜ 分支 `feature/task-006_xwz0910` ｜ 状态 review

**交付物**：`core/zace_core/chunking/{__init__,splitter,resolver,fingerprint}.py`、
`core/tests/chunking/{conftest,test_splitter,test_resolver,test_fingerprint}.py`（新增 42 个测试）。

**验收命令与结果**（均在本机 WSL 执行，uv workspace）：

| 命令 | 结果 |
|---|---|
| `uv run pytest core/tests/chunking -q` | 42 passed |
| `uv run pytest` | 262 passed, 2 skipped（原 220 passed 基线 + 42，无回归） |
| `uv run ruff check .` | clean |
| `uv run python scripts/check_dependency_direction.py` | 通过 |

**实现口径（评审重点，均已在模块 docstring 落地）**

1. **chunk_id / 双表同 id**：`{path}:{fqn}:{start_line}`；spec 块 id 与 `Store` 写 `spec_blocks`
   同源（`splitter.spec_block_id`），测试断言两表 id 一致（CF-01 规划期裁定 2）。
2. **signature / docstring 来源**：`SymbolDef` 无这两个字段（CF-08 冻结），由 splitter 从原文启发式提取
   ——Python 取「装饰器 + def/class 头」与紧随的字符串字面量（单行/多行/三引号/原始串）；C/C++ 取到
   `{` / `;` 之前的声明文本，**docstring 恒为空**；spec 块 `signature = heading_path`；兜底块两者皆空。
3. **类骨架 = 声明区**（`class` 恒骨架；`struct` 仅有直接成员时升格）：区间为「容器起始行 → 首个直接成员
   前一行」，**不含方法体**——这样改方法体不会让骨架 chunk 的 content_hash 变化，Module/01 §4.1
   「改 1 个函数只重嵌入 1 个 chunk」对方法成立（测试 `test_content_hash_reuse_semantics` 断言）。
4. **模块级/未覆盖代码 = 兜底 chunk**：不属于任何符号/spec 块的行按「最大连续段」递归字符切分
   （复用 TASK-002 `split_fallback`，≤800 行/块），伪 fqn 统一 `(module)`（与 TASK-005 `(preamble)`
   同风格）；纯空白段跳过。`namespace` 不成 chunk（Module/01 §2.2 语言规则表未列它为检索单元）。
5. **多义连接规则（卡内 B 的落地）**：候选 = fqn 精确 → 否则 `name_tail` 短名；收敛顺序
   **imports 路径推定 → 同文件 → is_exported**，任一阶段只剩 1 个即命中并写 `provenance='parsed'`；
   仍多个 → **全连**（`provenance='synthesized'`）并记入 `ResolveReport.ambiguous`（候选为符号 id）；
   无命中 → `mark_refs_failed`（`name_tail` 供重试）。
6. **imports 的 fqn 化（R8）**：由「末段是符号名、其余是模块路径」推定候选文件（相对导入按前导点回溯
   目录层数，`src/` 之类布局按路径后缀匹配）；推定命中为空即判 failed，**不跨文件猜同名符号**。
   C/C++ `#include` 边（target 是 `resolve_include` 产出的文件路径）、系统头（`<...>`）、通配符
   （`x.*`）与表达式形态名字（`obj.method()`）不参与解析，报告 `edges_skipped` / 判 failed。
7. **裸名边**：只有收敛到唯一 fqn 才 `retarget_edges`；多义时不猜（`retarget_edges` 是移动语义，
   一裸名边只能落一个 fqn），仅记入报告。全连语义只用于 pending ref。
8. **spec_references 匹配**：`mentioned` 归一化（去反引号/去调用括号、排除路径与表达式）后，fqn 精确
   优先，否则同名**全挂**（宁多勿漏）；`provenance` 恒 `inferred`（由 `Store.add_spec_refs` 强制）；
   符号删除/改名级联 `stale` 走 TASK-001 路径（测试验证删除后 `stale=1`）。
9. **指纹**：一级 `parser_config_hash` = 解析器注册表（扩展名 + 模块/类名）+ 切片规则版本 + 兜底上限
   + schema 版本 + 伪 fqn/kind 常量的 sha256；二级 `embedding_model` + `embedding_dim`（可读形态
   `model_id@dim`）。空库首建 → `none`；库内有文件但指纹缺失 → 保守 `full_reparse`；
   `full_reparse` 优先于 `reembed`。

**契约影响**：无（未改 `docs/contracts/**`、`types.py`、`interfaces.py`、`hashing.py`；
`chunking` 只读消费 `Store` 原语、`split_fallback`、`detect_language`、`EmbeddingProfile`）。

**与设计偏差**：无功能性偏差；两处口径属卡内未细化、已在此显式记录（其中第 3、5 条即为卡内要求
回填的「多义连接规则与 spec_references 匹配口径」）：

1. 类骨架取「声明区」而非整类区间（理由见上第 3 条）。
2. `(module)` 伪 fqn 用于兜底块（卡内只写了「模块级代码 = 兜底 chunk」，未定 fqn 形态）。

**未决问题**

1. **`Store` 原语不足以直接支撑「全连」**：`resolve_refs` 一条 ref 只落一条边（写边后删行），
   本模块用「重新播种同签名的 pending 引用再解析」绕过（净效果 N 条边 + 0 残留）。若需更干净的实现，
   建议 L2 扩展：`Store.add_edges(Sequence[EdgeDef])` 或让 `resolve_refs` 支持一 ref 多目标。
   ——请编排者裁决是否走契约扩展。
2. **类级语句落在最后一个成员之后时不成块**（本题 V1 取舍：不把方法体重复进骨架，也不为类级碎片
   造额外 kind）。典型类（常量在方法之前）不受影响；若评审要求覆盖，建议新增
   `class_level` kind 或让骨架覆盖「成员之外的类级行」。
3. **`EmbeddingProfile.max_input_tokens` 变化不触发失效**：D-07 只定义 model/dim 两级，
   截断上限变化实际会改变向量；当前按卡内口径（`model_id@dim`）处理，已知边界待评审。
4. **`symbols.chunk_id` 对 `namespace` 符号为 NULL**：`Store` 已有此分支，但 TASK-010..012 若假设
   「每个符号必有 chunk」，需在对应卡内确认（建议复核点）。
5. **跨语言假设待 TASK-007 实测**：imports 路径推定假设「仓库根 = 模块根」，无 `sys.path`/包根探测；
   非标准布局会如实判 failed（不猜）。

**建议复核点**：类骨架声明区口径（§3）、`(module)` 伪 fqn、`_match` 收敛顺序（§5）、
imports 的「宁缺勿假」（§6）、全连的 re-seed 实现（未决问题 1）。
