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
| WSL 三仓持久索引 | leveldb 36.9s / HelloAgents 46.0s / langchain 331.1s；均使用 `api:voyage-4-lite@1024` 与 parser fingerprint v2 |
| leveldb 重复 ingest | `invalidation=none`；0 files parsed / 0 vectors upserted；0.3s |

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

### WSL 持久索引与 v2 对照

数据根：`~/.zace/bench/voyage-4-lite-d1024`；环境文件：`~/.config/zace/benchmark.env`（仓库外，权限 `0600`，仅保存 embedding 配置）。

| 靶场 | project id | files | chunks | symbols | 磁盘 |
|---|---|---:|---:|---:|---:|
| leveldb | `3ed886ce58bc0e47` | 152 | 2642 | 2202 | 17 MiB |
| HelloAgents | `06078cc80c7ce7d7` | 236 | 2729 | 1082 | 28 MiB |
| langchain | `ca2050db0db5b1e2` | 2950 | 20673 | 15735 | 179 MiB |

三仓总占用约 223 MiB。三个 `index.db` 的 `parser_config_hash` 均为 v2 同一值，query vector 通道无降级。

| QA 指标 | v2 旧索引 | TASK-103 新索引 | 结论 |
|---|---:|---:|---|
| leveldb search R@5 / R@10 | 0.6429 / 0.6429 | 0.6429 / 0.6429 | 持平 |
| leveldb search MRR | 0.4607 | 0.4179 | 排名仍需后续路由/rerank 处理，本卡不调参 |
| leveldb ask pack any | 1/5 | 4/5 | L-10/L-14/L-16 恢复证据，P0 修复生效 |
| leveldb ask pack complete | 1/5 | 3/5 | L-10/L-14 完整，L-16 覆盖 2/4 |
| HelloAgents search / pack / complete | 0.8462 / 0.9231 / 0.7418；5/6；3/6 | 完全一致 | Python 无回归 |
| langchain search / pack / complete | 0.7143 / 0.7143 / 0.6429；5/5；4/5 | 完全一致 | Python 无回归 |

leveldb L-14（显式查询 `DBImpl::Get`）从 pack miss 变为 top-1；L-19 的 README 正例从 `answerable=false` 修正为 true。L-09 目标实现虽已入库，但仍未进入 pack，属于候选排序/路由问题而非索引缺失。

### 与设计的偏差

修订 TASK-002/TASK-004 的“任何 ERROR 整文件 fallback”实现口径，但不改变 D-08“尽力而为 + unresolved 如实标注”，也不修改冻结契约。建议编排者评审后把此漂移回记 Module 01。

### 未验证项

WSL 无法访问 VPS 的 `127.0.0.1:8080` AnswerProvider 网关，因此本轮 QA probe 只比较 search 与 ContextPack，未重跑实际 LLM 答案、引用命中率和 ask 延迟。该限制不影响 parser、索引与 pack coverage 的验证。
