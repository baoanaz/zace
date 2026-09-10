# TASK-002：Parser 基座 + Python 抽取器

> 状态：done ｜ 阶段：Phase 1 ｜ 硬依赖：无 ｜ soft 依赖：无
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

- 日期：2026-09-10 ｜ 分支：`feature/task-002_xwz0910`（自 `main` 创建）｜ 实施：泳道 B 会话
- 关键产物：`core/zace_core/parsing/{__init__,registry,base,python,fallback}.py`、
  `core/tests/parsing/{test_registry,test_python,test_fallback}.py`、`core/tests/parsing/samples/python/`（9 个语料文件）

### 验收命令与结果

| 命令 | 结果 |
|---|---|
| `uv run pytest core/tests/parsing -q` | 42 passed（覆盖：装饰器/async 嵌套/类方法/相对 import/`as` 别名/带注解 assignment/语法错误兜底）|
| `uv run pytest` | 43 passed |
| `uv run ruff check .` | All checks passed！（语料含 `# noqa` 的最小必要标注）|
| `uv run python scripts/check_dependency_direction.py` | 依赖方向检查通过 |

附加验证：`test_self_hosting_types_and_hashing` 用本抽取器解析 `core/zace_core/types.py`
（`ChunkDef`/`ParsedFile`/`SymbolDef` 三个类符号）与 `core/zace_core/hashing.py`
（`chunk_content_hash` 函数符号）；`test_parse_is_deterministic` 对全部 9 个语料断言两次 parse
逐字段相等且跨实例一致。

### 必须评审的口径（TASK-003/004/005/006 依赖）

1. **嵌套函数成符号（本卡裁定）**：是。fqn 用外层链 `Outer.inner`、`Class.method.nested`，kind 仍为
   `function`（只有直接位于类体里的才是 `method`）；模块级函数 fqn 不含模块前缀（chunk_id 已含 path，D-04）。
2. **模块级 assignment 取舍**：仅"带类型注解且左值为裸标识符"的 assignment 建符号（kind=`variable`）；
   无注解、解包、下标/属性赋值一律不建（避免把脚本临时变量与副作用赋值灌进符号表）。类属性 assignment 不建符号（V1 口径）。
3. **语法错误处理**：检测到 ERROR/MISSING 节点时整文件 `fallback=True` + `parse_errors`（≤20 条，带行号），
   `language` 仍保留真实语言（python/c/cpp，不为 fallback），且**不产任何半可信符号/边** —— 诚实优先，交给 TASK-006 兜底切分。
4. **模块级（文件级）边的 source_fqn = 文件 path**：模块没有符号节点，`imports` 与模块级代码的 `calls`
   统一用 path 作 source（TASK-006 从 path 推导包语义做相对 import 解析）。
5. **`is_exported`**：仅模块级符号；模块定义了 `__all__` 时按 `__all__` 判定，否则"不以 `_` 开头"；
   方法/嵌套符号一律 False。
6. **装饰器**：装饰器区间计入符号 `start_line`（切 chunk 时装饰器跟随函数）；装饰器表达式本身不产边。
7. **动态特性（不猜）**：`getattr/setattr/hasattr/delattr` → `unresolved(kind=call)`（第二参数为字符串字面量时取其内容）；
   `importlib.import_module` / `__import__` → `unresolved(kind=import)` 且不产 calls 边；
   下标调用、立即调用 lambda、字符串调用、调用结果再调用 → `unresolved(kind=call)`。
   属性链调用给整条链（如 `self.transform`、`super().__init__`）交 TASK-006 按 name_tail 解析。
8. **扩展名归属**：`.h` 归 C；C++ 头文件用 `.hpp/.hh/.hxx/.h++`（见未决问题 1）。
9. **fallback 口径**：分隔符优先级 `\n\n` → `\n` → ` ` → 硬切，**贪心聚合**至 800 行一块
   （不做"一切到底"产生 1 行 1 块）；`FALLBACK_MAX_CHARS=40_000` 是单行巨型输入的安全阀，不改变行上限语义；
   块内容为原文连续子串，行号 1-based 含端点。

### 与设计的偏差

无。契约消费方式与 `types.py`/`interfaces.py` 冻结定义一致，未改任何契约与设计文档。

### 未决问题（交编排者裁决）

1. **`.h` 归属**：Module/01 §2.2 未规定 C/C++ 头文件歧义；本卡取"`.h → C`、C++ 用 `.hpp/.hh/.hxx`"。
   若真实仓库里 `.h` 大量含 C++ 语法（class/template），会整文件进 fallback（不猜，但召回损失）。
   建议设计侧补一句口径，或 V2 用 compile_commands.json 判型（D-08 接口留白）。
2. **`imports` 边的 `target_name` 形态没有契约定义**：本卡统一为"模块点路径 + 名字"
   （`from .service import Service` → `.service.Service`；`from x import *` → `x.*`；`import a.b as c` → `a.b`，别名不落边）。
   TASK-006 的相对 import 解析按此前导点约定实现；若编排者要求别的形态，请更新本卡口径（不涉契约文件）。
3. **`parsing/fallback.py` 归属**：按卡内默认归本卡（TASK-006 只消费 `split_fallback`）。本卡已实现并测试。
4. **`__init__.py` 导出面**：当前导出 base/registry/fallback 的公共符号；未导出 `python.py` 的类
   （TASK-003/004/005 按卡约定直接 `from zace_core.parsing.x import XParser`）。若 005 想把 `MarkdownParser`
   也放进 `__init__`，需编排者协调（本文件所有权归 TASK-002）。
