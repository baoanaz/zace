# TASK-004：C++ 抽取器（尽力而为 + 诚实标注）

> 状态：pending ｜ 阶段：Phase 1 ｜ 硬依赖：TASK-003（复用 include / 名称匹配工具） ｜ soft 依赖：无
> 建议分支：`feature/task-004_<你的缩写><MMDD>`
> 交付物所有权：`core/zace_core/parsing/cpp.py`、`core/tests/parsing/samples/cpp/`、`core/tests/parsing/test_cpp.py`
> **本卡是全项目最大风险项（D-08）：定位"尽力而为 + unresolved 如实标注"，宁可缺边不可错边。**

## 目标

交付 C++ 抽取器：类/命名空间/模板/重载/继承等核心符号与边可用；两阶段查找、模板实例化、
用户定义转换序列**不做**，解析不了的一律进 `unresolved`，供 Missing Evidence 如实报告。

## 输入文档（按序读）

1. `docs/design/Module/01-切片存储.md` §2.2（C++ 规则表）
2. `docs/design/Background/04-gitnexus.md` §6（C++ 语义功能清单，**只作能力清单参考，超纲项不做**）
3. `core/zace_core/parsing/c.py`（TASK-003 交付的复用工具）
4. `docs/design/Background/02-codegraph.md` §3-4（tree-sitter 抽取与跨文件解析）

## 抽取规则（Module/01 §2.2 + D-08）

| 项 | 规则 |
|---|---|
| 符号 | `class_specifier` / `struct_specifier` / `namespace_definition` / `template_declaration`（**整体 1 symbol，不实例化**）/ 类外定义 `Class::method` / 构造函数析构函数 / operator 重载 |
| 继承 | `extends` 边（含 public/protected/private 继承）；`virtual` 覆写 → `overrides` 边为加分项，做不到就如实进 unresolved |
| 重载消歧 | 同名重载靠 `start_line` 自然消歧（chunk_id 规则 D-04），不需要额外处理 |
| 模板调用 | `foo<int>(x)` 解析到 `foo` 的模板定义；显式实例化 `template class Foo<int>` 记 unresolved 或跳过（记录口径） |
| include | 复用 TASK-003 的解析器（相对优先 / 唯一同名猜测 / 解不开 unresolved） |
| 明确不做 | 两阶段名称查找、模板实例化/特化语义、转换序列、ADL、concepts、`decltype` 求值 |
| 诚实纪律 | 每个"没解析出来"必须落 `unresolved`（带 kind=call/reference/import），**禁止**用启发式连一条可能错的边 |

## 交付物（文件所有权）

| 路径 | 内容 |
|---|---|
| `core/zace_core/parsing/cpp.py` | C++ 抽取器 |
| `core/tests/parsing/samples/cpp/` | 测试语料（多文件） |
| `core/tests/parsing/test_cpp.py` | 测试 |

## 验收标准（DoD）

- [ ] `uv run pytest core/tests/parsing/test_cpp.py -q` 全绿，样本 ≥ 10 个文件，必须覆盖：
  - namespace 嵌套 + 类外方法定义（`A::B::foo`）；
  - 重载函数（同名不同参）→ 两个符号、id 不同；
  - 模板函数/模板类各 1 例 → 各 1 个模板符号，调用边指向模板定义；
  - 继承链（含虚函数声明）→ extends 边正确；
  - 头文件包含 + 跨文件调用（类方法调用）→ unresolved 或正确 resolved（按 TASK-006 解析前状态如实产出）；
  - 典型"解析不了"样例（模板特化、宏生成代码）→ unresolved 非空且不被静默丢弃。
- [ ] 诚实性回归：语料中刻意放 1 个无法静态解析的间接调用，断言它以 unresolved 出现。
- [ ] 确定性：同输入两次 `ParsedFile` 相等。
- [ ] 基线三条命令全绿。

## 参考源码锚点（只读）

- `source/GitNexus/gitnexus/src`（C++ tree-sitter 与两阶段查找实现——**只读理解边界，不复刻**）
- `source/codegraph/codegraph-kernel/src`（C++ 抽取）
- Background/04 §6 的 C++ 语义清单（作为"我们不做什么"的对照表）

## 明确不做

- 不做两阶段查找 / 模板实例化 / 类型推导（V2 按用户反馈排期）；
- 不接 compile_commands.json（V2，接口留白）；
- 不修改 TASK-003 的 `c.py`（需要扩展时先在本卡记录，由编排者协调 003 的所有者）；
- 不修改 `registry.py` / `base.py` / `__init__.py`（归 TASK-002）；测试直接 `from zace_core.parsing.cpp import CppParser`。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

（实施 AI 在此填写。"哪些语法形态进 unresolved"的最终口径必须在此列全，供文档漂移与 Missing Evidence 文案复用。）
