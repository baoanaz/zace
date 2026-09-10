# TASK-018：兜底切分行号修复（U1，阻断级）+ chunk id 唯一性防御 + 单文件失败隔离

> 状态：review ｜ 阶段：Phase 1（W3c，**阻断 M1**）｜ 硬依赖：无 ｜ soft 依赖：无
> 建议分支：`feature/task-018_<你的缩写><MMDD>`（从最新 main）
> 交付物所有权：`core/zace_core/parsing/fallback.py`、`core/tests/parsing/test_fallback.py`、
> `core/zace_core/chunking/splitter.py`、`core/tests/chunking/`、`core/zace_core/pipeline/indexer.py`、`core/tests/pipeline/`
> 其它文件不得改动（尤其 `core/zace_core/contextpack/`，那是 TASK-019 的范围）。

## 背景（编排者实测确认，2026-09-10；TASK-013 自举时发现）

**真实仓库索引直接崩溃**（不是理论风险）：

```console
$ uv run zace-core ingest --repo . --data /tmp/zace-u1
sqlite3.IntegrityError: UNIQUE constraint failed: chunks.id
```

根因已定位（两层）：

### A. 根因 1：`fallback.py::_split` 递归时丢失基准偏移

```python
# 现状（错误）：_split_keep 返回的偏移是相对 text 的，_group 却当绝对偏移用
for index, separator in enumerate(separators):
    parts = _split_keep(text, separator)      # parts 偏移基准 = text 起点（0）
    if len(parts) < 2: continue
    _group(parts, max_lines, max_chars, out, separators[index + 1:])   # ← offset 参数被忽略
    return
```

顶层调用时 `offset == 0`，相对偏移恰好等于绝对偏移，所以既有测试全绿；一旦经 `_group` 分支进入
`_split`（offset ≠ 0）再按下级分隔符切分，第二部分的行号就回跳到文件开头。最小复现（主干实测）：

```python
split_fallback("1\n2\n3\n4\n5\n6\n\n7\n8\n9\n10\n11\n12\n", max_lines=5)
# 实测：start=1, 6, 1(应为 8), 7(应为 12)   ← 第 3、4 块行号回跳
```

### B. 根因 2：chunk id 撞车 → 整次 ingest 崩溃

兜底块 fqn 为 `(module)`，行号回跳后两个块都得到 `{path}:(module):1` → 违反 `chunks.id` 主键 →
`sqlite3.IntegrityError` 直接冒泡，**整个仓库的索引任务失败**（`zace-core ingest --repo .` 对
zace 自身仓库必崩：`uv.lock` 是 1518 行的无解析器文件，正好走多级兜底切分）。

## 修复要求

### A. 根因修复（`fallback.py`）

- 在 `_split` 的分隔符分支中把基准偏移补上（例如 `_group([(off + offset, piece) for off, piece in parts], ...)`）；
- 复核 `_group` 内对超限片段调用 `_split(part, part_offset, ...)` 时 `part_offset` 已是绝对偏移（修复后应成立）；
- 复核 `_split_keep` 的"块拼回 = 原文"不变量仍然成立；
- **回归测试（必须）**：`max_lines` 小到强制多级递归（如 5）且输入含段落空行（迫使 `"\n\n"` → `"\n"` 两级），
  断言：所有块 `start_line` **严格递增**、块内容与原文对应行一致、拼接可还原原文。

### B. chunk id 唯一性防御（`chunking/splitter.py`）

兜底块与同名同起始行的 id 撞车不应再以 sqlite 主键错误的形式暴露：

- 在切分产物出口处检测重复 id；命中时**抛带明细的 ValueError**（列出冲突 id 与文件），
  而不是让 sqlite 抛出难以定位的 `IntegrityError`；
- 严禁静默去重/静默丢弃（诚实纪律：宁可显式失败，不可隐藏数据丢失）；
- 测试：构造人为重复（或直接对 §A 修复前的输入）断言抛出的是带明细的 ValueError。

### C. 单文件失败隔离（`pipeline/indexer.py`）

一个文件的问题不应让整个项目索引失败（Module/01 §4.3 的 per-file 韧性）：

- `_index_file` 的 `split_file` / `apply_file_change` 调用纳入异常保护：捕获后写
  `acc.errors.append(f"{path}: {type(exc).__name__}: {exc}")` 并跳过该文件（**不**计入 added/modified）；
- 保持"解析失败走 fallback"的既有路径不变；本项只兜住"切分/落库"阶段的意外；
- 测试：注入一个必然失败的文件（可用 monkeypatch 让 `apply_file_change` 抛异常），断言
  ① ingest 不抛异常；② `report.errors` 含该文件；③ 其它文件正常入库。

## 验收标准（DoD）

- [ ] `uv run pytest core/tests/parsing core/tests/chunking core/tests/pipeline -q` 全绿
- [ ] 全仓 `uv run pytest` 全绿（472 既有用例零回归）
- [ ] `uv run ruff check .`、`uv run python scripts/check_dependency_direction.py` 通过
- [ ] **阻断解除实证（必须贴进执行记录）**：`uv run zace-core ingest --repo . --data /tmp/zace-u1-check`
      在 **zace 仓库本体（不剔除 uv.lock/.git）** 上跑通，输出 IngestReport（含 files/chunks 数）。
      这是本卡的核心验收，不允许用"副本剔除某些文件"代替。
- [ ] 回归护栏：§A 的最小复现变成一条永久测试（断言行号严格递增）
- [ ] 任务卡"执行记录"回填 + 任务板状态改 review

## 参考

- `docs/plan/contracts.md` §3.3 R11-R13（集成期裁定纪律）
- TASK-013 执行记录 U1（发现者，含原始复现资料 `/tmp/zace-self-ingest`）

## 明确不做

- 不改兜底切分的分隔符优先级与上限常量；不改 chunk id 格式（D-04）；
- 不改 `contextpack/`（TASK-019 范围）；不做并发/性能优化。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写；执行记录必须含**zace 仓库本体 ingest 成功**的输出。

## 执行记录

### 1. 交付概览

- 日期：2026-09-10｜分支：`feature/task-018_xwz0910`（从 `main` @ `8a454c1`）｜提交：`task-018: fix fallback offset, reject duplicate chunk ids, isolate per-file failures`
- 改动文件（全部在卡内“交付物所有权”清单内，未动 `contextpack/`）：
  - `core/zace_core/parsing/fallback.py`（§A）：`_split` 分隔符分支进 `_group` 前给片段相对偏移补上本层基准
    `offset`；模块 docstring 增记“偏移基准是全原文”不变量。
  - `core/zace_core/chunking/splitter.py`（§B）：出口新增 `_reject_duplicate_ids`；
    构建路径从 `dict` 静默去重改为 list + 出口校验（`_structural_chunks` 抽出）。
  - `core/zace_core/pipeline/indexer.py`（§C）：`_index_file` 的 `split_file`/`apply_file_change`
    与 `_rebuild_vectors` 的存量枚举统一 `try/except` → `report.errors` + 跳过该文件。
  - `core/tests/parsing/test_fallback.py`（+2）、`core/tests/chunking/test_splitter.py`（+2）、
    `core/tests/pipeline/test_indexer.py`（+3）。

### 2. 实现口径

1. **§A 根因**：`_split_keep` 返回的偏移恒相对 `text`，而 `text` 在原文中的起点就是 `_split` 的
   `offset`；`_group` 必须收到**绝对偏移**[^1]，否则它把相对偏移写进 `out`、再由原文偏移反算行号时回跳。
   顶层 `offset=0` 使既有测试全绿，只有多级递归（`"\n\n"` → `"\n"`）才暴露。
2. **§B 唯一性是硬不变量**：出口统计 `id → 出现次数`，出现 >1 即抛 `ValueError`，消息形如
   `{path}: 切分产物出现重复 chunk id（禁止静默去重/丢弃）：{id} × {n}; ...`；不静默去重、不静默丢弃，
   chunk id 格式（D-04）与分隔符优先级/上限常量均未动。
   该出口同时覆盖“单行 > `FALLBACK_MAX_CHARS` 硬切出的多个兜底块同 `start_line`”这类先天同 id
   （fqn 恒为 `(module)`）：现在显式失败 + §C 隔离，不再变成 sqlite 崩溃。
3. **§C 单文件隔离**：切分/落库阶段任何异常只写 `report.errors`（`{path}: {ExcType}: {msg}`）并跳过该文件，
   **不**计入 added/modified；解析失败走 fallback 的既有路径未动；`apply_file_change` 本身是单事务，
   跳过不会留半写状态。

[^1]: `_split` 的硬切分支（`offset + index`）本来就是绝对偏移，说明“绝对偏移”是本模块的既有约定，
   分隔符分支只是漏补了。

### 3. 验收命令与结果

```text
$ uv run pytest core/tests/parsing core/tests/chunking core/tests/pipeline -q
159 passed in 2.52s   （EXIT=0）

$ uv run pytest
479 passed, 2 skipped in 11.32s   （基线 472 既有用例零回归，新增 7 条）

$ uv run ruff check .
All checks passed!

$ uv run python scripts/check_dependency_direction.py
依赖方向检查通过（core 纯库 / service 不上探）。
```

### 4. 阻断解除实证（本卡核心，zace 仓库本体，未剔除 uv.lock/.git）

```console
$ uv run zace-core ingest --repo . --data /tmp/zace-u1-check
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN ...
warning: core/tests/parsing/samples/c/broken/broken.c: L3: syntax error near 'int broken( { return 1; }'
warning: core/tests/parsing/samples/c/macros/macros.h: L6: macro CONCAT uses token pasting; not expanded; L7: macro LOG uses variadic; not expanded
warning: core/tests/parsing/samples/cpp/broken/broken.cpp: L3: syntax error near 'namespace app { class Broken : public {'
warning: core/tests/parsing/samples/cpp/templates/templates.hpp: L26: missing identifier; L26: explicit template instantiation skipped (not modeled)
warning: core/tests/parsing/samples/cpp/unresolved/macro_gen.cpp: L10: missing ;; L24: missing ;; L5: macro DECLARE_ACCESSOR uses token pasting; not expanded
project: adfdd1a626db62b7 (created)
repo: /home/xuwenzheng/2_github/AI/ACE/zace-lane-a
identity: git remote git@github.com:baoanaz/zace.git (path .)
mode: incremental (invalidation=none)
files: added=214 modified=0 deleted=0 parsed=214
chunks: new=2370 reused=0 removed=0
vectors: upserted=2370 deleted=0
graph: edges_retargeted=1353 unresolved_resolved=20 spec_refs=2251 ambiguous=207
elapsed: 335.1s

EXIT=0
```

- 两次全新数据根实测（`rm -rf` 后重跑）除 `elapsed` 外**逐字段一致**（`added=214`、`parsed=214`、
  `new=2370`、`chunks` 库行数 2370、`EXIT=0`）—— 修复后既是可复现的，也不再有 `sqlite3.IntegrityError`。
- 顶部 5 条 warning 是 `core/tests/parsing/samples/**` 里**故意损坏的样本**的解析告警（既有行为，非本卡引入）；
  无“另有 N 条解析/读取告警”行，即本次 ingest 的 `report.errors` 恰为这 5 条。
- 原始崩溃输入 `uv.lock`（1518 行、无解析器 → 多级兜底切分）已正常入库，行号严格递增（直连索引库核对）：

```text
sqlite> select count(*) as chunks, count(distinct id) as distinct_ids from chunks;
2370|2370
sqlite> select file_path, count(*), min(start_line), max(end_line) from chunks where file_path='uv.lock';
uv.lock|11|1|1518
sqlite> select id, start_line, end_line from chunks where file_path='uv.lock' order by start_line;
uv.lock:(module):1|1|203
uv.lock:(module):204|204|499
uv.lock:(module):500|500|637
uv.lock:(module):638|638|818
uv.lock:(module):819|819|878
uv.lock:(module):879|879|1021
uv.lock:(module):1022|1022|1224
uv.lock:(module):1225|1225|1310
uv.lock:(module):1311|1311|1436
uv.lock:(module):1437|1437|1439
uv.lock:(module):1440|1440|1518
```

### 5. 反向验证（护栏确实锁住缺陷）

把 `core/zace_core/parsing/fallback.py` 单独回退到 `HEAD`（`git stash push -- <file>`）后：

```text
$ uv run pytest core/tests/parsing/test_fallback.py -q
FAILED test_nested_separators_keep_absolute_line_numbers
FAILED test_recursive_split_line_ranges_map_back_to_source
E   AssertionError: assert 1 > 6
E    +  where 1 = FallbackBlock(index=3, start_line=1, end_line=5, ...).start_line
2 failed
```

旧代码在最小复现上的块行号为 `1, 6, 1, 7`（第 3、4 块回跳），修复后为 `1, 6, 8, 13`；测试对
“`start_line` 严格递增 + 块内容 = 原文对应行子串 + 拼接可还原原文”三条同时断言。

### 6. 契约影响 / 与设计偏差 / 未决问题

- **契约影响**：无。`docs/contracts/**`、`types.py`、`interfaces.py` 未动；`IngestReport.errors` 的语义
  由“解析/读取失败”扩为“解析/切分/落库失败”（字段类型与调用方口径不变，只更新注释），
  `split_file` 签名与返回类型不变，新增的异常是契约内既有的 `ValueError`。
- **与设计偏差（说明，非静默）**：§C 卡内只点名 `_index_file`；实现时把同一口径也放到了
  `_rebuild_vectors` 的存量枚举循环（那里同样逐文件调用 `split_file`）。理由：否则 §B 新增的显式失败
  会让 `--full` / `reembed` 档位重新变成“单文件拖垮整次 ingest”，与本卡“per-file 韧性”的意图相反。
  影响面：`--full` 下该文件会被写入 `report.errors` 且其向量不被重嵌（与既有的“读文件失败即 continue”
  行为一致，SQLite 行不变）。
- **未决问题**：
  1. 单行 > `FALLBACK_MAX_CHARS`（40000 字符）的文件，其硬切兜底块天生同 `start_line` → 现在每次都
     显式失败、不入库（走 `report.errors`）。让这类文件可索引需要给 chunk id 引入段内序号，属 D-04
     id 格式变更，超出本卡；建议编排者决定是否单开卡。本仓库当前无此类文件（最大单行 < 40000）。
  2. `--full` 中失败文件的向量会缺失（SQLite 行仍在），检索侧只会有“向量通道少召回”，
     属既有的 read-failure 行为，本卡沿用未改。
