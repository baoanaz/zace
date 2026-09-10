# TASK-003：C 抽取器（include / static / 函数指针 / 宏）

> 状态：done ｜ 阶段：Phase 1 ｜ 硬依赖：TASK-002 ｜ soft 依赖：无
> 建议分支：`feature/task-003_<你的缩写><MMDD>`
> 交付物所有权：`core/zace_core/parsing/c.py`、`core/tests/parsing/samples/c/`、`core/tests/parsing/test_c.py`

## 目标

交付 C 语言抽取器：符号/边/unresolved 如实产出；include 解析与函数指针调用合成是本卡两个难点，
C++ 抽取器（TASK-004）将复用本卡的 include 与名称匹配工具。

## 输入文档（按序读）

1. `docs/design/Module/01-切片存储.md` §2.2（C 规则表）
2. `core/zace_core/types.py`、`core/zace_core/interfaces.py`（Parser 协议）
3. `docs/design/Background/02-codegraph.md` §4（跨文件解析与 c-fnptr-synthesizer）

## 抽取规则（Module/01 §2.2，逐条落实）

| 项 | 规则 |
|---|---|
| 符号 | `function_definition` / `struct_specifier` / `enum_specifier` / `typedef` / 函数宏 `preproc_function_def` / 简单对象宏 `#define X`（复杂宏：token pasting `##`、可变参数宏不展开，进 parse_errors 或 unresolved 如实标注） |
| include | `#include "x.h"` 相对当前文件目录优先；`<x.h>` 无 build 信息时按"仓库内唯一同名"猜测；解不开 → unresolved（kind=import），不做猜测性连边 |
| static | `static` 函数/变量仅文件内可见：跨文件同名匹配时不得命中 static 符号（可见性过滤） |
| 函数指针 | 收集 `fp = func` / 函数指针表初始化，调用点 `fp(...)` → 对每个可能目标合成 `calls` 边，`provenance='synthesized'`；多个候选全部合成（宁多勿漏，rerank 已对 synthesized 降权） |
| 调用边 | 普通调用 `foo(args)` → edges(kind='calls', target_name='foo')，解析交 TASK-006 |
| unresolved | 动态分发、解不开的 include、复杂宏 → `unresolved`，禁止猜 |

## 冻结接口（本卡不得变更）

- 消费：`types.py` 索引侧类型、`parsing/base.py` 基类（TASK-002）。
- 产出：`parsing/c.py` 提供 `CParser`，并向 TASK-004 暴露可复用函数（include 解析、C 名称匹配），函数签名在 `c.py` 内自注释即可，但**不得放进 base.py**（避免与 002 所有权冲突）。
- 并行纪律：`registry.py` / `base.py` / `__init__.py` 归 TASK-002，本卡**不得修改**；若工作区里尚无 registry，测试直接 `from zace_core.parsing.c import CParser`。

## 交付物（文件所有权）

| 路径 | 内容 |
|---|---|
| `core/zace_core/parsing/c.py` | C 抽取器 + 供 004 复用的工具 |
| `core/tests/parsing/samples/c/` | 测试语料（含多文件 include 链） |
| `core/tests/parsing/test_c.py` | 测试 |

## 验收标准（DoD）

- [ ] `uv run pytest core/tests/parsing/test_c.py -q` 全绿，样本 ≥ 8 个文件，必须覆盖：
  - 多文件 include 链（`a.c → a.h → common.h`），`#include "..."` 与 `<...>` 各自的解析结果；
  - static 函数跨文件同名场景：不产生跨文件边；
  - 函数指针：赋值 + 调用 → synthesized 边存在且 provenance 正确；
  - 函数宏调用、简单对象宏；
  - typedef struct / enum / 匿名 struct；
  - 语法错误文件 → fallback 不抛异常。
- [ ] 确定性：同输入两次 `ParsedFile` 相等；输出按行号稳定排序。
- [ ] 基线三条命令全绿。

## 参考源码锚点（只读）

- `source/codegraph/codegraph-kernel/`（C 抽取；include/函数指针合成参考 `src/resolution/c-fnptr-synthesizer.ts`，见 Background/02 §4）
- `source/GitNexus/gitnexus/src` 中 C 相关 tree-sitter 处理（static linkage 分析）

## 明确不做

- 不做 C++ 语义（004）；不做 build 系统集成（compile_commands 属 V2，接口留白即可）；
- 不做宏展开；不做函数指针的"唯一目标"推断（多候选全合成是设计选择）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

- 日期：2026-09-10 ｜ 分支：`feature/task-003_xwz0910`（自 `feature/task-002_xwz0910` 创建，泳道内串联）
- 关键产物：`core/zace_core/parsing/c.py`、`core/tests/parsing/test_c.py`、
  `core/tests/parsing/samples/c/`（13 个语料文件：include 链 / static / 函数指针 / 宏 / struct-enum-typedef / 语法错误）

### 验收命令与结果

| 命令 | 结果 |
|---|---|
| `uv run pytest core/tests/parsing/test_c.py -q` | 16 passed |
| `uv run pytest` | 59 passed |
| `uv run ruff check .` | All checks passed |
| `uv run python scripts/check_dependency_direction.py` | 依赖方向检查通过 |

### include 猜测策略最终口径（本卡关键产物，004/006 与文档漂移回溯用）

单文件解析（`Parser.parse`，无 I/O）与带仓库表解析（`resolve_include(..., repo_paths)`）两档：

| 输入形态 | 单文件模式（repo_paths=None） | 带仓库表模式 |
|---|---|---|
| `#include "x.h"` | 相对当前文件目录拼接（折叠 `./..`，越出仓库根 → None）→ 产 imports 边 | 相对路径命中仓库表优先；未命中 → 唯一同名猜测 |
| `#include <x.h>` | **一律 None → unresolved(kind=import)**（无 build 信息不猜） | 仓库内唯一同名猜测；0 或多命中 → None |
| `#include MACRO`（宏形式） | unresolved(kind=import) | 同左 |

- 边形态：`imports`，source = 当前文件 path；target = 解析出的仓库相对路径（正斜杠）。
- unresolved 的 `name` 用书写形态（`<stdio.h>` / `"../outside.h"`），保留 `<` `>` 与引号。
- “相对优先”与“唯一同名”的歧义边界：相对路径命中不查全局；未命中时同名歧义（≥2）不猜。

### 其余口径（必须评审）

1. **符号表**：`function_definition` / 有 body 的 `struct_specifier`·`union_specifier`·`enum_specifier` /
   `type_definition`（typedef）/ `preproc_function_def` / `preproc_def`（对象宏）。
   **函数原型（无 body 的声明）不成符号**（卡内符号表未列；仅 `b.h` 这类纯原型头会只剩 include-guard 宏）；
   全局/静态变量不成符号（V1 口径）。
2. **kind 映射**：union → `struct`（设计 kind 表无 union，二者同为记录类型）；`#ifdef/#if/#else/#elif` 容器内
   的声明照常抽取（极常见形态）。
3. **匿名 struct/enum 不成符号**（无稳定 fqn），由外层 typedef 承载名字；
   `typedef struct Point {...} Point;` 只保留 struct 符号（否则同 fqn 同 start_line 会撞 chunk_id）。
4. **static**：`is_exported=False`；本卡提供 `filter_visible()` 作为跨文件匹配的强制可见性过滤（TASK-004/006 复用）。
   卡内 DoD 的“不产生跨文件边”在执行层等价于：解析器只产同名 `calls` 边 + 可见性元数据，真正的连边由 TASK-006 的
   name-matcher 穿过过滤后执行（本卡已测：static helper 在 a.c 视角下不可见）。
5. **函数指针**：文件内全局收集候选（声明初始化 / `fp = func` / `fp = &func` / 函数指针数组的位置式初始化 /
   设计化初始化 `.field = func` / 函数指针 typedef 别名推导），调用点 `fp(...)`、`obj.field(...)`、`arr[i](...)`
   对**全部**候选合成 `calls` 边（provenance=`synthesized`），宁多勿漏；命中候选时不再产同名 parsed 边。
   设计化字段按字段名匹配（不校验接收者类型）——记录在案，属有意放宽。
6. **宏**：函数宏/对象宏建符号；`##`（token pasting）与可变参数宏**不展开**，写入 `parse_errors`（警告；
   `files.parse_errors` 契约就是“解析警告（非失败）”，不置 fallback）。宏调用点仍产 parsed `calls` 边指向宏名。
7. **宏可见性**：头文件（`.h/.hh/.hpp/.hxx/.inc/.def`）宏 `is_exported=True`，源文件宏 False（宏不跨编译单元）。
8. **结束行**：预处理指令节点的行尾换行会被算进节点，符号 `end_line` 回退一行（`_node_end_line`）。

### 与设计的偏差

无。契约消费方式与 `types.py`/`interfaces.py` 一致；未改任何契约、设计文档或 TASK-002 的 `registry.py`/`base.py`/`__init__.py`。

### 未决问题（交编排者裁决）

1. **函数原型不成符号**：若真实 C 仓库的公共 API 只写在头文件（声明+实现分离），TASK-006 的名字匹配会落到 `.c` 的定义；
   但“头文件里声明的宏/结构体/typedef”仍会被索引。若产品上需要“以头文件作为 API 入口点”，需补一条卡内口径（会影响 chunk 数量）。
2. **include 的 `<...>` 单文件模式一律 unresolved**：`repo_paths` 已有实现但当前无调用方（`parse()` 纯函数无 I/O）。
   TASK-007 若要在索引期输出 resolved include 边，需在流水线里传入文件表并重跑 `resolve_include`（接口已就绪）。
3. **`synthesized` 边的数量**：多候选全合成（如 L20 一行 3 条边）会增加图扩展候选量，D-16/D-17 已定 rerank 对 synthesized 降权；
   若后续有 noisy 反馈，再议“唯一候选才合成”（当前按卡内“宁多勿漏”）。
