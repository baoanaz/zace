# TASK-005：Markdown SpecBlock 抽取（doctype / 标题树 / mentioned）

> 状态：review ｜ 阶段：Phase 1 ｜ 硬依赖：无 ｜ soft 依赖：无
> 建议分支：`feature/task-005_<你的缩写><MMDD>`
> 交付物所有权：`core/zace_core/parsing/markdown.py`、`core/tests/parsing/samples/markdown/`、`core/tests/parsing/test_markdown.py`

## 目标

交付 Markdown 抽取器：SpecBlock（标题树下完整小节）为一等检索资产（D-13/D-42），
产出 doctype / heading_path / code_fences / mentioned 四类结构化信号，供 TASK-006 建 chunk 与 spec_references。

## 输入文档（按序读）

1. `docs/design/Module/01-切片存储.md` §2.2（Markdown/SpecBlock 全节，①doctype 表 ②切块 ③spec_references）
2. `core/zace_core/types.py`（`SpecBlockDef` / `CodeFence`）
3. `docs/design/Module/02-检索策略.md` §4.2-d（下游如何消费 doctype / spec_references）

## 抽取规则

| 项 | 规则 |
|---|---|
| 标题 | 仅 ATX（`#`..`######`）；setext 标题不识别（按正文处理，记录口径）；代码围栏内的 `#` 不算标题 |
| 切块 | 每标题起、至下一个同级或更高级标题前 = 1 个 SpecBlock；标题链 `heading_path`（`"A > B > C"`）为 fqn |
| id | `{path}:{heading_path}:{start_line}`；同名标题靠 start_line 唯一（D-04 精神） |
| front matter | YAML front matter 单独成块（heading_path 用 `"(front matter)"`，口径记录） |
| doctype | 按路径/文件名规则表（Module/01 §2.2-①）判定：agent-instructions（AGENTS.md/CLAUDE.md/.cursorrules）/ readme（README*）/ design（ARCHITECTURE*、docs/design/**）/ adr（docs/adr/**）/ api（API*.md、PROTOCOL*、openapi*）/ changelog（CHANGELOG*）/ guide（其余）；规则写成有序表，首个命中生效 |
| code_fences | 每个围栏 `{lang, content, line}`（含无语言标注的围栏，lang 空串）；V1 只存不解析 |
| mentioned | 行内 code（反引号）与符号形态词（camelCase / snake_case / `A::b` / 带扩展名路径）去重提取；**宁多勿漏**（下游是弱引用，错挂代价是多余候选，见 D-06） |
| 大小 | 不按 token 硬切小节（超长小节交给 TASK-008 的 embedding 截断） |

## 交付物（文件所有权）

| 路径 | 内容 |
|---|---|
| `core/zace_core/parsing/markdown.py` | Markdown 抽取器 |
| `core/tests/parsing/samples/markdown/` | 测试语料 |
| `core/tests/parsing/test_markdown.py` | 测试 |

## 验收标准（DoD）

- [x] `uv run pytest core/tests/parsing/test_markdown.py -q` 全绿，样本 ≥ 6 个文件，必须覆盖：
  - 多层标题嵌套（≥3 级）→ heading_path 链正确、块边界正确（到同级标题为止）；
  - 同名标题出现两次 → id 不同、都能被索引；
  - 中文标题 + 中英文混排正文；
  - 代码围栏（含 ```python 与无语言）→ code_fences 行号正确；围栏内 `# comment` 不产生标题；
  - front matter 单独成块；
  - doctype 判定：AGENTS.md / README.md / docs/design/x.md / docs/adr/y.md / CHANGELOG.md 各 1 例；
  - mentioned 提取：反引号符号、`Class::method`、带路径扩展名的词。
- [x] dogfood 冒烟：解析 `docs/design/Module/01-切片存储.md`，断言 SpecBlock 数量 > 10 且包含 heading_path 含 `"§2.2"` 语义的块（用宽松断言，不要依赖该文件精确内容）。
- [x] 确定性：同输入两次 `ParsedFile` 相等。
- [x] 基线三条命令全绿。

## 参考源码锚点（只读）

- `source/GitNexus/gitnexus/src`（markdown phase：Section 节点 + 交叉链接；见 Background/04）
- `source/ragcode/src/document/chunking/`（文档切块，反面参考：不要引入多格式/OCR 复杂度）

## 明确不做

- 不修改 `registry.py` / `base.py` / `__init__.py`（归 TASK-002）；测试直接 `from zace_core.parsing.markdown import MarkdownParser`；
- 不做段落级 parent-child 子块（V2 观察项）；不解析 code fence 内容成符号调用（V1 只存）；
- 不做非 Markdown 文档格式（rst/docx 等）；不做链接图分析。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

### 2026-09-10 / feature/task-005_xwz0910（泳道 C，本地分支交付）

**完成报告**

- 分支：`feature/task-005_xwz0910`
- 验收：
  - `uv run pytest core/tests/parsing/test_markdown.py -q` → 22 passed（样本 8 个 md 文件）；
  - 基线三条：`uv run ruff check .` → All checks passed；
    `uv run python scripts/check_dependency_direction.py` → 通过；`uv run pytest` → 23 passed；
  - dogfood：解析 `docs/design/Module/01-切片存储.md` → 25 个 SpecBlock，含 heading_path 带 "2.2" 的块，
    全部 id 唯一；确定性：同输入两次 `ParsedFile` 相等。
- 关键产物：`core/zace_core/parsing/markdown.py`（`MarkdownParser` / `classify_doctype` /
  `spec_block_id`）、`core/tests/parsing/test_markdown.py`、`core/tests/parsing/samples/markdown/`（8 个样本）。
- 契约影响：无。`ParsedFile` / `SpecBlockDef` / `CodeFence` 按冻结定义使用；未动 `types.py`、`interfaces.py`、
  `parsing/{__init__,base,registry}.py`（归 TASK-002）。
- 与设计偏差：无。设计未覆盖的空白处按下列口径补齐（见下）。
- 未决问题：无。
- 建议复核点：① 口径表（下表）是否可接受；② 围栏归属最内层块、前置前言块两条补充口径是否与 TASK-006
  的 chunk 映射一致（TASK-006 每条 `SpecBlockDef` = 1 chunk，父块 content 含子块全文，属预期）。

**口径记录（本卡要求明确记录）**

| 项 | 最终口径 |
|---|---|
| 标题 | 仅 ATX（≤3 空格缩进，`#` 后需空白，剥离尾部 `#`）；setext（`===`/`---` 下划线）不识别，按正文处理 |
| 围栏 | ``` 与 ~~~ 均识别（≥3 字符，闭合需同类且不短于开头）；lang 取 info string 首 token（无语言 = `""`）；未闭合围栏延伸到文件末尾 |
| 围栏归属 | 归属最内层包含它的 SpecBlock（父块不重复登记），避免 TASK-006 切 chunk 时重复 |
| front matter | 首行 `---` 起、下一个 `---` 行止（含首尾行，end_line = 闭合行）单独成块；`heading_path="(front matter)"`、`heading=""`、`level=0`；content 为两条 `---` 之间的原文（不含分隔行）；front matter 区域不参与标题/围栏扫描 |
| 前言块（补充） | 首个标题之前（front matter 之后）的非空正文单独成块：`heading_path="(preamble)"`、`level=0`；避免无标题文件零产出/丢内容；全空白则不建块 |
| 块边界 | 每个标题块至下一个 level ≤ 当前 level 的标题前；EOF 收尾；父块 content 含整棵子树 |
| content 规范化 | `content.splitlines()` 后按 `"\n"` 连接（丢弃文件末尾换行与 `\r`），保证跨平台确定性与 hash 稳定 |
| mentioned | 行内反引号 code 内容 + 符号形态词（camelCase/PascalCase、snake_case/SCREAMING_SNAKE、`A::b`、带目录分隔符或已知扩展名的路径）；按首次出现位置去重、顺序稳定；提取范围含围栏内代码（意图代码是 spec↔code 天然锚点），宁多勿漏（D-06） |
| doctype | 有序规则表（首个命中生效）：agent-instructions（AGENTS.md/CLAUDE.md/.cursorrules，大小写不敏感）→ readme（README*）→ design（ARCHITECTURE* / 含 `docs/design/` 路径段）→ adr（含 `docs/adr/` 路径段）→ api（API*/PROTOCOL*/openapi*）→ changelog（CHANGELOG*）→ guide |
| id | 提供 `spec_block_id(block)`：`{path}:{heading_path}:{start_line}`（同名标题靠 start_line 消歧） |
