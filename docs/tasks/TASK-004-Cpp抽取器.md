# TASK-004：C++ 抽取器（尽力而为 + 诚实标注）

> 状态：review ｜ 阶段：Phase 1 ｜ 硬依赖：TASK-003（复用 include / 名称匹配工具） ｜ soft 依赖：无
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

- 日期：2026-09-10 ｜ 分支：`feature/task-004_xwz0910`（自 `feature/task-003_xwz0910` 创建）
- 关键产物：`core/zace_core/parsing/cpp.py`、`core/tests/parsing/test_cpp.py`、
  `core/tests/parsing/samples/cpp/`（14 个语料文件：命名空间/重载/模板/继承/跨文件/宏生成/间接调用/语法错误）

### 验收命令与结果

| 命令 | 结果 |
|---|---|
| `uv run pytest core/tests/parsing/test_cpp.py -q` | 11 passed |
| `uv run pytest` | 70 passed |
| `uv run ruff check .` | All checks passed |
| `uv run python scripts/check_dependency_direction.py` | 依赖方向检查通过 |

未修改 `c.py` / `registry.py` / `base.py` / `__init__.py`；`get_parser("cpp")` 已验证可懒加载到 `CppParser`。

### 哪些语法形态进 unresolved（最终口径，必须评审；Missing Evidence 文案直接复用本表）

| 形态 | 产出 | 理由 |
|---|---|---|
| 函数指针参数 / 无初始化的函数指针变量调用（`fn(x)`） | `unresolved(kind='call', name=变量名)` | 知道是间接调用但目标未知 |
| lambda 变量调用（`auto g = [](...); g(x)`） | `unresolved(kind='call', name='g')` | 目标是匿名 lambda，无符号可连 |
| `std::function` 变量调用 | `unresolved(kind='call', name=变量名)` | 目标运行时才定 |
| 成员指针调用 `(obj.*pmf)()` / `(obj->*pmf)()` | `unresolved(kind='call', name='(obj.*pmf)')` | 指针值静态不可知（`->*` 形态 tree-sitter 直接报 ERROR → 整文件 fallback） |
| 强制转换后的指针调用 `((int (*)(void*))raw)(x)` | `unresolved(kind='call', name=表达式)` | callee 不是 identifier/属性链 |
| 模板特化 `template <> class Box<int> {...};` | 保留符号 + `unresolved(kind='reference', name='Box<int>')` | 不建模特化语义，但不静默丢弃 |
| 宏生成的成员/变量声明（类型位置命中本文件宏名） | `unresolved(kind='reference', name=声明原文)` | 不展开宏，真实成员未知 |
| `override` 方法找不到同文件基类方法 | `unresolved(kind='reference', name='Base::method')` | 两阶段查找不做；跨文件基类是常态 |
| `<stdio.h>` 等解不开的 include | `unresolved(kind='import', name='<stdio.h>')` | 复用 TASK-003 口径 |

**跳过（不产边也不产 unresolved，记录口径）**：显式实例化 `template class Box<double>;`
——它不引入新声明实体，主模板符号已存在；仅在 `parse_errors` 记一条 `explicit template instantiation skipped`。

### 其余口径

1. **类内方法声明也成符号**（无 body，kind=method）：否则 header-only 类没有方法 chunk，
   “类骨架 + 每方法 1 chunk”无法成立。文件/命名空间作用域的函数原型仍不成符号（与 TASK-003 一致）。
2. **fqn** 用 `::` 连接（`outer::inner::Widget::run`）；重载不额外消歧（`start_line` 天然唯一，D-04）。
3. **kind**：`class_specifier`→class，`struct/union_specifier`→struct，`enum_specifier`→enum，
   `namespace_definition`→namespace，using 别名与 typedef 同 kind=typedef（设计 kind 表无 alias）。
4. **overrides**：仅同文件、仅名字匹配（基类短名后缀匹配 `app::Shape::area`），provenance=`synthesized`。
5. **调用目标归一**：`->` 归一到 `.`（`w.run`），模板实参去除（`max_value<int>` → `algo::max_value`），
   便于 TASK-006 的 name_tail 匹配（`. ` 分隔）。

### 与设计的偏差（重点评审）

1. **MISSING 容忍（C++ 专用，新增行为）**：`base.py` 把 ERROR/MISSING 一律视为解析失败（fallback）；
   C++ 里宏调用后缺分号（如 `DECLARE_ACCESSOR(width)`）会报 MISSING ';'——若整体兜底，宏密集的 C++
   仓库会丢掉全部符号。本卡在 `CppParser.parse` 里加了一条严格受限的容忍：**仅**当错误全为 MISSING、
   数量 ≤ 5 时照常抽取（错误仍完整保留在 `parse_errors`，宏生成声明另进 unresolved）；出现任何 ERROR
   或超过上限 → 仍整体 fallback。未修改 `base.py`（容忍逻辑完全在本模块内，复用 base 的公开工具函数）。
   若编排者认为应上提到 base.py 作为通用策略，需由 TASK-002 所有者修改。
2. 其余与设计一致：不做两阶段查找/模板实例化/转换序列/ADL/concepts（D-08）。

### 未决问题（交编排者裁决）

1. **overrides 的 unresolved 噪声**：跨文件基类（常态）会让每个 `override` 方法产生一条 unresolved。
   对 Missing Evidence 是真实信号，但量大时需要下游聚合（按类聚合计数）。是否改为“只在同文件基类可见时才报”，请编排者定。
2. **类内声明 + 类外定义会各出一个 chunk**（同 fqn、不同 start_line）。若 03/06 发现重复证据影响预算，
   可考虑在 TASK-006 按 fqn 聚合（当前按 D-04 只要求代内唯一）。
3. **`->*` 形态 tree-sitter 直接产 ERROR**（grammar 限制），这类文件会整文件 fallback。属上游语法库限制，
   V1 接受；若真实仓库 `->*` 常见，需要预处理或换 grammar 版本。
