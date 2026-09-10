# TASK-003：C 抽取器（include / static / 函数指针 / 宏）

> 状态：pending ｜ 阶段：Phase 1 ｜ 硬依赖：TASK-002 ｜ soft 依赖：无
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

（实施 AI 在此填写。include 猜测策略的最终口径必须在此记录，供 004 与文档漂移回溯。）
