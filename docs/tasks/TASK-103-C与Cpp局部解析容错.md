# TASK-103：C/C++ 局部解析容错

> 状态：review ｜ 阶段：Phase 5 ｜ 硬依赖：TASK-091 ｜ soft 依赖：无
> 建议分支：`feature/task-103-parser-recovery_<你的缩写><MMDD>`
> 交付物所有权：`core/zace_core/parsing/{base,c,cpp}.py`、`core/zace_core/chunking/fingerprint.py`、`core/tests/{parsing,chunking}/`

## 目标

修复 C/C++ 文件存在局部 tree-sitter ERROR/MISSING 时整文件降级的问题。保留不受错误区间影响的可信符号与关系，错误区域继续生成 fallback chunk；解析器异常或没有可信结构时仍整文件 fallback。

真实回归锚点：leveldb `7ee830d` 的 `db/db_impl.cc` 仅 L1063-L1065 三处宏注解触发 ERROR，当前却丢失 `DBImpl::Get`、`DBImpl::Write`、`DBImpl::CompactMemTable`、`DBImpl::WriteLevel0Table` 等全部结构化符号（见 `benches/results/qa-audit-2026-09-15.md` §5/§6.1）。

## 输入文档

1. `docs/design/INDEX.md`：D-02、D-07、D-08、D-41。
2. `docs/design/Module/01-切片存储.md` §2.2、§2.4、§4.2。
3. `benches/results/qa-audit-2026-09-15.md` §5、§6.1。
4. `docs/tasks/TASK-002-Parser基座与Python.md`、`TASK-003-C抽取器.md`、`TASK-004-Cpp抽取器.md`。

## 参考源码锚点（只读）

- `source/GitNexus/gitnexus/src/core/tree-sitter/safe-parse.ts`：恢复树降级但继续返回；诊断独立保留。
- `source/GitNexus/gitnexus/src/core/ingestion/utils/ast-helpers.ts#hasRecoveredSyntax`：事实抽取遇恢复子树时 fail closed。
- `source/GitNexus/gitnexus/src/core/ingestion/languages/cpp/captures.ts`：C++ ERROR 形态的窄范围恢复与单文件预算。
- `source/codegraph/codegraph-kernel/src/ccpp/mod.rs` + `source/codegraph/src/extraction/tree-sitter.ts`：快路径遇错切换到宽容抽取器，宽容路径继续遍历恢复树。
- `source/ragcode/src/indexing/analyzers/tree-sitter-base.ts`：只有 parser 抛异常才 fallback，恢复树继续抽取。

## 实施边界

- 不改 `core/zace_core/types.py`、`interfaces.py` 或 `docs/contracts/**`。
- 不修改 `docs/design/**`；本卡记录与 TASK-002“任何语法错误整文件 fallback”的实现漂移，交编排者评审后决定是否回记 Module 01。
- 不做宏白名单预处理，不放宽为“允许固定 N 个错误”，不修改 rerank/ContextPack 参数。
- Python 语法错误仍保持整文件 fallback。

## 验收标准

- [x] C/C++ 局部错误前后的正常函数仍进入 `ParsedFile.symbols`，错误区间内伪恢复符号不进入。
- [x] `parse_errors` 保留 ERROR/MISSING 诊断，局部恢复结果 `fallback=False`。
- [x] 无可信结构的损坏文件仍 `fallback=True`。
- [x] chunker 为可信符号产结构化 chunk，为错误/未覆盖区间产 fallback chunk。
- [x] leveldb `db_impl.cc` 的四个目标方法均进入 symbols，L1063-L1065 仍有诊断和 fallback 覆盖。
- [x] parser fingerprint 改变，旧索引触发 `full_reparse`。
- [x] `uv run pytest core/tests/parsing core/tests/chunking -q`、ruff、依赖方向、全仓 pytest 全绿。

## 执行记录

- 日期：2026-09-15 ｜ 分支：`feature/task-103-parser-recovery_xwz0915` ｜ 实施：泳道 B 会话
- 关键产物：C/C++ 单次解析局部恢复、ERROR/MISSING 区间过滤、错误区间 fallback、parser fingerprint v2、C/C++/chunker 回归测试。

### 验收命令与结果

| 命令 | 结果 |
|---|---|
| `uv run pytest core/tests/parsing core/tests/chunking -q` | 147 passed |
| `uv run ruff check .` | All checks passed |
| `uv run python scripts/check_dependency_direction.py` | 依赖方向检查通过 |
| `uv run pytest -o addopts="" -q` | 1026 passed, 2 skipped |
| 真实 leveldb parser/chunker 探针 | `fallback=False`；60 symbols / 590 edges；四个目标方法均恢复；L1063-L1065 三条诊断保留并形成单独 fallback chunk |

### 实施口径

1. `TreeSitterParser` 默认仍是整文件 fallback；仅 C/C++ 显式启用局部恢复，Python 行为不变。
2. C/C++ 只 parse 一次。对恢复树先运行既有抽取器，再删除与 ERROR/MISSING 行区间相交的非 namespace 符号、错误行事实及来自被删除符号的关系；没有可信符号时整文件 fallback。
3. C++ 既有“仅 MISSING 且不超过 5 条”的宏缺分号容忍保持原样，不过滤其 unresolved 证据。
4. namespace 是结构容器且不产 chunk，允许保留；class/struct 若覆盖 ERROR 区间则删除，使 chunker 能把错误区间作为 fallback，而不是被父容器 chunk 吞掉。
5. `PARSER_CONFIG_VERSION` 从 1 升到 2，旧索引按 D-07 必须全量重建。

### 参考项目结论

- GitNexus：恢复树是降级结果而非整文件丢弃，同时对受恢复语法污染的事实 fail closed。
- codegraph：C/C++ 快路径遇错误树会切到更宽容的抽取路径，且对特定 ERROR 形态做窄恢复。
- ragcode：只有 parser 抛异常才整文件 fallback，tree-sitter 恢复树继续参与抽取。
- notace-tool-rs：未使用 tree-sitter，不提供局部 AST 恢复参考。

### 与设计的偏差

修订 TASK-002/TASK-004 的“任何 ERROR 整文件 fallback”实现口径，但不改变 D-08“尽力而为 + unresolved 如实标注”，也不修改冻结契约。建议编排者评审后把此漂移回记 Module 01。

### 未验证项

当前用户无权读取 `/etc/zace/zace.env`，无法在本机新建 Voyage embedding 索引并复跑 `leveldb-v1` 端到端分数。旧持久索引不能用于验证新 parser；需在具备 embedding 配置的环境全量重建后复跑 v2，不能增量复用旧索引。
