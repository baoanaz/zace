# TASK-002：Parser 基座 + Python 抽取器

> 状态：pending ｜ 阶段：Phase 1 ｜ 硬依赖：无 ｜ soft 依赖：无
> 建议分支：`feature/task-002_<你的缩写><MMDD>`
> 交付物所有权：`core/zace_core/parsing/`（除 `c.py` / `cpp.py` / `markdown.py`，那三份归 003/004/005）、`core/tests/parsing/`

## 目标

建立 Parser 基座（注册表 + tree-sitter 加载 + 公共工具 + 兜底策略），并交付 Python 抽取器，
产出 `ParsedFile`（CF-08）。TASK-003/004/005 在此基座上开发各自语言抽取器。

## 输入文档（按序读）

1. `docs/design/Module/01-切片存储.md` §2.1、§2.2（Python 规则表）、§2.3
2. `core/zace_core/types.py`（SymbolDef/EdgeDef/UnresolvedRef/ParsedFile）
3. `core/zace_core/interfaces.py`（Parser 协议：不抛异常，失败 → `fallback=True`）
4. `docs/design/Background/02-codegraph.md` §3、§4（unresolved 两阶段模式、Rust kernel 线协议经验）

## 冻结接口（本卡不得变更）

- 消费：`types.py` 全部索引侧类型；`Parser` 协议。
- 产出：
  - `registry.py`：`get_parser(language) -> Parser`；语言识别 `detect_language(path) -> str | None`（python/c/cpp/markdown；未知 → None 表示走 `fallback`）。
    **注册约定（并行关键）**：本卡一次性写全四语言的懒加载条目（`python→zace_core.parsing.python:PythonParser`、`c→…:CParser`、`cpp→…:CppParser`、`markdown→…:MarkdownParser`），模块暂不存在时懒加载给出清晰错误即可；TASK-003/004/005 **只实现各自模块文件，不得修改 `registry.py` / `base.py` / `__init__.py`**。
  - `base.py`：`TreeSitterParser` 基类（加载 grammar、错误容忍、行号工具、输出去重排序），供 003/004 复用。
  - `python.py`：`PythonParser`。
  - `fallback.py`：递归字符切分兜底（800 行上限，TASK-006 调用；若归 006，则本卡只提供接口位置注释——**默认归本卡实现，006 只消费**）。

## Python 抽取规则（Module/01 §2.2，逐条落实）

- 符号：`function_definition`（含 async）、`class_definition`、模块级带注解 assignment；嵌套函数是否成符号由你裁定并在卡内记录（建议：成符号但 fqn 用 `Outer.inner`）。
- 边：`calls`（裸名/属性链，目标名给 `target_name` 交 TASK-006 解析）、`imports`（含 `from x import y as z`、相对 import、`__init__.py` 语义）、`extends`（基类）。
- unresolved：动态特性（`getattr`、字符串调用、`importlib`）如实进 `unresolved`，不猜。
- 确定性：输出顺序稳定（按行号）；同一输入两次解析结果逐字节相等（测试断言）。

## 交付物（文件所有权）

| 路径 | 内容 |
|---|---|
| `core/zace_core/parsing/__init__.py` | 导出 |
| `core/zace_core/parsing/registry.py` | 语言识别 + 四语言懒加载注册表（003/004/005 不得修改本文件） |
| `core/zace_core/parsing/base.py` | tree-sitter 基类与公共工具 |
| `core/zace_core/parsing/python.py` | Python 抽取器 |
| `core/zace_core/parsing/fallback.py` | 兜底切分 |
| `core/tests/parsing/` + `core/tests/parsing/samples/python/` | 测试语料与期望 |

## 验收标准（DoD）

- [ ] `uv run pytest core/tests/parsing -q` 全绿，样本语料 ≥ 8 个文件，必须覆盖：装饰器（跟随函数）、async、嵌套函数、类中方法、相对 import、`from ... import ... as`、带注解的模块级 assignment、语法错误文件（→ fallback + parse_errors 非空）。
- [ ] 确定性断言：同一文件 parse 两次，`ParsedFile` 相等。
- [ ] 自举：用本抽取器解析 `core/zace_core/types.py`，断言能得到预期符号（自行挑 3 个断言，至少含 1 个类与 1 个函数，如 `ChunkDef` / `chunk_content_hash` 所在的真实定义）。
- [ ] 基线三条命令全绿。

## 参考源码锚点（只读）

- `source/codegraph/codegraph-kernel/`（tree-sitter 抽取与线协议；见 Background/02 §3）
- `source/codegraph/src/resolution/name-matcher.ts`（可见性与名称匹配规则，Python 部分）
- `source/ragcode/src/indexing/analyzers/`（Python 分析器）

## 明确不做

- 不做二阶段跨文件解析（TASK-006）；不做 C/C++/Markdown（003/004/005）；不做 chunk 切分（TASK-006 消费本卡符号）。
- 不新增 `core/tests/parsing/conftest.py`、`__init__.py` 等共享文件（多泳道共用该目录，避免合并冲突；确需时先在卡内记录申请）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

（实施 AI 在此填写。嵌套函数策略、模块级 assignment 的取舍须在此记录。）
