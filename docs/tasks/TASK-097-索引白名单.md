# TASK-097：索引白名单（AI 指令文档与 skills 目录放行）

> 状态：pending ｜ 阶段：Phase 3（M2c）｜ 硬依赖：TASK-037（已合并）｜ soft 依赖：无
> 建议分支：`feature/task-097-index-allowlist_<你的缩写><MMDD>`
> 交付物所有权：
> - `core/zace_core/pipeline/ignore.py`（白名单层 + 配置项）
> - `core/zace_core/parsing/markdown.py`（doctype 名表扩充；**仅** `_AGENT_INSTRUCTION_NAMES`）
> - `client/src/ignore.rs`（Rust 侧对齐，R42 要求两侧语义一致）
> - `core/tests/pipeline/`、`client/tests/`（新增/更新断言）
> - `docs/handbook/`（**新增**一节说明白名单，如 `索引白名单.md`）
>
> 清单外文件不得改。**特别提醒**：
> - **不得改** `docs/contracts/**`——但本卡**需要**契约变更（见 §D），请走 L2 流程：在
>   "执行记录"里写契约变更申请，**不要自己改 contracts 文件**；
> - **不得改** `zace_core/{types,interfaces,hashing}.py`；
> - **不得改** rerank 特征分值（R30 冻结）。

## 背景（用户 2026-09-14 提出）

用户在讨论切片上传时提出一个真实场景：

> 万一 .gitignore 中包含 .claude / .agent / .codex 等这些 AI 相关的隐藏文件，
> 里面有 SKILL.md 怎么办，这个也是信息含量高的文档。
>
> 又或者，能不能自动检索用户所有的 SKILL.md 进行上传呢？

### 实测现状（编排者验证）

**测试仓库**（含 `.gitignore` 排除 `.claude/` 与 `.codex/`）：

| 文件 | gitignore 是否命中 | zace 是否索引 |
|---|---|---|
| `.claude/skills/learned/SKILL.md` | ✅ 命中 | ❌ **不索引** |
| `.codex/config.toml` | ✅ 命中 | ❌ **不索引** |
| `.pi/agent/skills/SKILL.md` | ❌ 未命中 | ✅ 索引 |
| `AGENTS.md` | ❌ 未命中 | ✅ 索引 |

**结论**：zace 完全跟随 `.gitignore`——用户把 AI 目录写进 gitignore，里面的 SKILL.md 就不会被索引。

**但有一个好消息**：zace **不因为"隐藏"就跳过**（`client/src/ignore.rs` 的
`.hidden(false)`，并有测试 `hidden_directories_are_still_indexed_contrary_to_walker_defaults` 守护）。
且内置跳过列表里**没有** `.claude` / `.codex` / `.pi` / `.cursor`。
所以是否索引**完全取决于用户的 gitignore**。

**另有一条通路已工作**：`AGENTS.md` / `CLAUDE.md` / `.cursorrules` 已被识别为
`agent-instructions` doctype（`core/zace_core/parsing/markdown.py` 的 `_AGENT_INSTRUCTION_NAMES`），
享受 rerank `+0.8` 加分。**缺的只是"被 gitignore 排除的 AI 文档"这条通路。**

## 用户拍板的需求（2026-09-14）

> 倾向 C（文件名白名单）+ D（文档说明）的组合，就这样吧，
> 让 zace 能够**随意添加白名单文件**，这样就可以把一些高质量的文件上传上去了。
>
> AGENTS.md / CLAUDE.md / .cursorrules / .agent.md / HANDOFF.md / 这些是我目前能想到的。
> 外加一个 **skills/ 文件夹里面的都上传吧**？代替 SKILL.md

**需求拆解**：

1. **可配置的白名单机制**（"随意添加"）——用户能自己增删，不是硬编码死表；
2. **默认白名单**：AI 指令文档文件名 + `skills/` 目录；
3. **优先级**：白名单要能**压过 `.gitignore`**（否则被排除了仍然进不来）；
4. **文档说明**：让用户知道这个机制存在。

## 目标

新增一个**第 0 层"索引白名单"**（优先级高于现有三层），让用户能把高质量文件
（AI 指令文档、技能文档）强制纳入索引范围。

## §A 白名单机制设计（core 侧，主实现）

### §A-1 优先级位置

现有三层（`ignore.py` 的 `is_ignored`）：

```
第 1 层 .zaceignore   （最高）
第 2 层 .gitignore
第 3 层 内置目录名
```

**新增第 0 层"白名单"**，优先级**高于全部三层**：

```
第 0 层 索引白名单     ← 新增：命中即**强制索引**，无视其他三层的排除
第 1 层 .zaceignore
第 2 层 .gitignore
第 3 层 内置目录名
```

**语义**：白名单是"**强制包含**"（force-include），不是"优先考虑"。

### §A-2 配置方式（用户要"随意添加"）

**两种来源，取并集**：

| 来源 | 形式 | 用途 |
|---|---|---|
| **内置默认** | 代码常量 `DEFAULT_ALLOWLIST` | 开箱即用（AI 指令文档 + skills 目录） |
| **项目自定义** | `{repo}/.zaceinclude` 文件 | 用户随意添加（每行一个模式，语法同 gitignore） |
| **环境变量**（可选） | `ZACE_INDEX_ALLOWLIST`（逗号分隔） | 全局/服务端配置场景 |

**优先级**：`.zaceinclude` 与内置默认**取并集**（不做覆盖）——用户不需要重写内置项。

### §A-3 内置默认白名单（用户指定）

**文件名白名单**（按 basename 匹配，大小写不敏感）：

```
AGENTS.md
CLAUDE.md
.agent.md
.cursorrules
HANDOFF.md
```

**目录白名单**（路径中任意一段命中即放行该文件）：

```
skills/
```

**关于 `skills/` 的说明**（用户原话："外加上一个 skills/ 文件夹里面的都上传吧？代替 SKILL.md"）：
- 该规则放行**任意 `skills/` 目录下的全部文件**（不限文件名），
  这样 `skills/<分类>/<技能>/SKILL.md` 与同目录的辅助文件都能进来；
- **风险提示（写进文档）**：`skills/` 是个通用目录名，可能与其他项目的同名目录冲突
  （如 `node_modules/*/skills/`）。**实现时必须确保内置跳过目录（`node_modules` 等）优先级仍然生效**——
  即 `node_modules/xxx/skills/a.py` **不应**被白名单救回。**这是本卡最容易写错的地方，必须有测试守护。**

**编排者的实测证据**（最小复现仓库可重建于 `/tmp/zace-wl-test`）：

```
repo/
├── .gitignore          → 内容: "hacks/"
├── hacks/skills/SKILL.md          ← 要救的（被 gitignore 排除的真实技能文档）
├── node_modules/pkg/skills/a.py   ← 绝不能救的（依赖目录里的同名结构）
└── .git/objects/                  ← 绝不能救的（版本控制元数据）
```

无白名单时 `list_files()` 只返回 `.gitignore`（两个目录都被排除）。
**加白名单后预期结果**：`hacks/skills/SKILL.md` 出现，而 `node_modules/pkg/skills/a.py` **仍不出现**。

### §A-4 与内置跳过目录的关系（关键约束）

白名单**不得**突破以下两类目录（即"白名单不能救回它们里面的文件"）：

| 类别 | 例子 | 理由 |
|---|---|---|
| **版本控制元数据** | `.git/`、`.hg/`、`.svn/` | 救回它们毫无意义且危险（`.git/objects` 是二进制） |
| **依赖/产物目录** | `node_modules/`、`.venv/`、`__pycache__/`、`dist/`、`build/` | 这些目录里的 `skills/` 不是用户的技能文档 |

**实现建议**：白名单判定放在**内置目录剪枝之后**——
`DirectorySource._walk` 已经"遇到被忽略的目录就整体剪枝"（不进入），
所以只要内置层负责剪掉这些目录，白名单自然不会看到里面的文件。

> **需你验证**：确认 `_walk` 的剪枝顺序确实让内置层先于白名单生效。
> 若白名单在中途插入导致 `node_modules` 被遍历，就是 bug。

## §B client 侧对齐（R42 要求两侧语义一致）

R42 契约原文：

> **契约是"忽略语义"而不是库**：将来 client 用 `ignore` crate 时，两侧行为须一致
> （TASK-037 需给出语义清单与对照测试）

**要求**：
- `client/src/ignore.rs` 的 `walker()` 需支持同一套白名单语义；
- `ignore` crate 没有原生的 "force-include" 概念——**你需评估实现方式**，例如：
  - 用 `overrides` API（`WalkBuilder::overrides` 支持 `!pattern` 强制包含）；
  - 或在 `filter_entry` 里加一层判断；
  - **选一个并在报告里说明理由与局限**。
- 两侧行为差异必须在报告里**如实列出**（R42 允许已知差异，但要求记录）。

## §C doctype 与 rerank 对齐

`core/zace_core/parsing/markdown.py` 的 `_AGENT_INSTRUCTION_NAMES` 当前是：

```python
_AGENT_INSTRUCTION_NAMES = frozenset({"agents.md", "claude.md", ".cursorrules"})
```

**需扩充**（与白名单保持一致）：

```python
_AGENT_INSTRUCTION_NAMES = frozenset({
    "agents.md", "claude.md", ".cursorrules", ".agent.md", "handoff.md", "skill.md",
})
```

**注意**：
- 这是**新增 doctype 名称**，命中后享受现有 `agent-instructions` 的 `+0.8` rerank 加分
  （**不改分值**，只扩名表）；
- `HANDOFF.md` 加进来是合理的（用户明确指定），它确实是高信息密度的交接文档；
- 若你认为 `skill.md` 该单独一个 doctype，**先执行记录里提出来**，不要自行新增 doctype 取值
  （那会改 CF-03 的 `doctype` 枚举，属契约变更）。

## §D 契约变更申请（**必须写进执行记录，不要自行改契约文件**）

本卡触发的契约影响：

| 契约 | 影响 | 需要的动作 |
|---|---|---|
| **R42**（忽略规则三层） | 新增第 0 层白名单 → 从"三层"变"四层" | 需编排者更新 `docs/plan/contracts.md` 的 R42 |
| **Module/05 §3.1**（忽略规则设计） | 同上 | 需编排者更新设计文档 |
| CF-03（`doctype` 枚举） | 若只扩名表**不影响**；若新增 doctype 取值**会影响** | 取决于你 §C 的实现选择 |

**在"执行记录"里按 `docs/plan/orchestration.md` §4 的格式写申请**，然后继续实现
（本卡的实现不依赖契约文件本身，只依赖语义）。

## 验收标准（DoD）

- [ ] `uv run pytest core/tests/pipeline -q` 全绿，**必须覆盖**：
  - [ ] `.gitignore` 排除 `.claude/skills/SKILL.md` → **仍被索引**（白名单生效）；
  - [ ] `.gitignore` 排除 `AGENTS.md` → **仍被索引**；
  - [ ] **`node_modules/**/skills/a.py` 不被救回**（关键守护：白名单不突破依赖目录）；
  - [ ] **`.git/**` 不被救回**（版本控制元数据不进入）；
  - [ ] `.zaceinclude` 里自定义的模式生效（如加一行 `my-notes/*.md`）；
  - [ ] 白名单**不改变**既有三层的行为（未命中白名单的路径，行为逐字不变）；
  - [ ] 大小写不敏感（`agents.md` 与 `AGENTS.md` 等价）。
- [ ] **client 侧**：`cd client && cargo test` 全绿，覆盖同一组语义（至少"gitignore 排除的 AI 文档仍被索引"）。
- [ ] **两侧对照**：同一测试仓库上，core 与 client 的文件列表**一致**（贴两份输出对比）。
- [ ] **真实场景验证**（贴真实输出）：对含 `.claude/skills/**` 的仓库（如
      `/home/xuwenzheng/2_github/AI/ACE/source/GitNexus`，含 `.claude/skills`）跑一次列举，
      确认 skills 下的文件被纳入。
- [ ] **文档**：`docs/handbook/` 新增一节，说明：
      - 白名单机制是什么、优先级如何；
      - `.zaceinclude` 怎么写；
      - **默认清单有哪些**（让用户知道能删）；
      - **风险**：白名单会突破 gitignore，用户需知晓。
- [ ] 基线三条命令全绿：`uv run ruff check .`、
      `uv run python scripts/check_dependency_direction.py`、`uv run pytest -o addopts="" -q`
- [ ] 任务卡"执行记录"已回填（**含契约变更申请**）；任务板状态改为 `review`。

## 明确不做

- **不改** `docs/contracts/**`（走申请流程）；
- **不改** rerank 特征分值（R30 冻结；`+0.8` 是既有值，只扩名表）；
- 不做"用户上传任意文件"的通路（这是索引范围，不是上传接口）；
- 不做白名单的 GUI 配置（属 WebUI，另开卡）；
- 不改 `.zaceignore` 的语义（它是"排除"，白名单是"包含"，两者正交）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板。**必须包含**：

- §A-2 配置方式的实现与理由；
- §A-3 `skills/` 规则**不突破 `node_modules` 的验证证据**（这是最容易写错的点）；
- §B 两侧一致性对照（core vs client 的文件列表）；
- §D 契约变更申请的完整文本；
- 真实仓库（含 `.claude/skills`）上的验证输出。

## 执行记录

（实施 AI 在此填写。）
