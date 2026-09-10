# TASK-018：兜底切分行号修复（U1，阻断级）+ chunk id 唯一性防御 + 单文件失败隔离

> 状态：pending ｜ 阶段：Phase 1（W3c，**阻断 M1**）｜ 硬依赖：无 ｜ soft 依赖：无
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

（实施 AI 在此填写。）
