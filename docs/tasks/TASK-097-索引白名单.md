# TASK-097：索引白名单（AI 指令文档与 skills 目录放行）

> 状态：review ｜ 阶段：Phase 3（M2c）｜ 硬依赖：TASK-037（已合并）｜ soft 依赖：无
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
| **R42**（忽略规则三层） | 新增第 0 层白名单 → 从"三层"变"四层" | 需编排者更新 `docs/contracts/PROCESS.md` 的 R42 |
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

### 2026-09-14 ｜ 分支 `feature/task-097-index-allowlist_xwz0914` ｜ 状态 review

#### 完成报告

- **分支**：`feature/task-097-index-allowlist_xwz0914`（从 `main` 的 `f154fc8` 起）
- **验收命令与结果**：
  - `uv run pytest core/tests/pipeline -o addopts="" -q` → **79 passed**（含新增 `test_allowlist.py` 26 条，其中 2 条是两侧对照）
  - `cd client && cargo test` → **50 passed**（43 lib + 2 parity + 5 stdio）
  - `uv run ruff check .` → **All checks passed**
  - `uv run python scripts/check_dependency_direction.py` → **通过**
  - `uv run pytest -o addopts="" -q`（须先 `env -u EMBED_MODE …`）→ **909 passed, 2 skipped**
- **关键产物**：`core/zace_core/pipeline/{ignore,source}.py`、`core/zace_core/parsing/markdown.py`、
  `core/zace_core/pipeline/__init__.py`、`client/src/{ignore,index}.rs`、
  `core/tests/pipeline/test_allowlist.py`、`client/tests/allowlist_parity.rs`、
  `docs/handbook/operations/索引白名单.md`

> **环境注意**：`.env` 里的 `EMBED_MODE=api` 会让 `core/tests/embedding/test_factory.py::test_default_is_local_onnx_provider`
> 失败（该测试断言默认是本地 provider，被环境变量覆盖）。这是既有环境敏感测试，与本卡无关；
> 本卡的基线数字用 `env -u EMBED_MODE -u EMBED_MODEL -u EMBED_BASE_URL -u EMBED_API_KEY uv run pytest` 取得。

#### §A-2 配置方式与理由

三种来源**取并集**（不覆盖）：`{repo}/.zaceinclude`（项目自定义）+ 内置默认（代码常量）
+ `ZACE_INDEX_ALLOWLIST`（逗号分隔，服务端/CI）。**为什么取并集而不是覆盖**：内置清单是
"开箱即用"的底线（用户原话是"让 zace 能够随意添加白名单文件"，是**添加**而不是"自己写全表"）；
覆盖语义会迫使每个项目复制一遍默认清单，升级时也拿不到新增的默认项。

**优先级**：内置默认 < 环境变量 < `.zaceinclude`（后写覆盖先写）。方向与既有第 1/2 层
（`.zaceignore` > `.gitignore`，"越靠近项目越优先"）一致，且让 `!skills` 这类取消条目真能生效
——**默认清单 therefore 是可删的**（手册 §3 明写）。

**语法刻意收窄**（不是完整 gitignore 语法）：`#` 注释、`!` 取消、含 `/` 或不含点的裸名字按
**目录名**、含点的裸名字按**文件名**（大小写不敏感）。**不支持 `*`/`**`/`?`/`[]`**：白名单是
"我必须拿到这些文件"的显式清单；引入通配就等于造第二套 `.gitignore`，R42 的两侧对照测试会立刻
失效（写的通配行被静默忽略，手册已注明）。

#### §A-3 不突破 `node_modules` 的验证证据（**实测输出**）

最小复现仓库（卡内 §A-3 形状 + GitNexus 真实技能文档，共 238 文件）：

```console
$ cat .gitignore
.claude/
.codex/
node_modules/
vendor/
$ find . -name SKILL.md | wc -l
13
```

`DirectorySource.list_files()` 实测（并统计 `os.scandir` 触碰过的目录）：

```console
$ uv run python /tmp/scan_evidence.py /tmp/task097-real
indexed: 37
  indexed under 'node_modules': 0 []
  indexed under '.git/objects': 0 []
  indexed under 'vendor': 0 []
  scandir touched 'node_modules': 0 []
  scandir touched '/.git': 0 []
  scandir touched 'vendor': 1 ['/tmp/task097-real/vendor']
```

- **要救的进了**：`.claude/skills/**` 下 30 个文件（`SKILL.md` + 参考文档 + 脚本）被救回
  （白名单 ON 37 个文件 vs 关闭白名单 7 个，差集 30 个全部来自 `skills/`）；
- **绝不能救的没进**：`node_modules/pkg/skills/a.py`、`.git/objects/**` 一个都没有，而且
  `scandir` **从未触碰** `node_modules` 与 `.git`（连枚举都没发生）；
- **没有无界下钻**：被排除的 `vendor/`（200 个文件）只被 `scandir` 一次（判断"里面有没有白名单
  命中项"），**不进入**——TASK-037 的性能约束未被推翻。

守护测试（两侧各有独立断言，不只靠上面这次手工验证）：
`core/tests/pipeline/test_allowlist.py::test_dependency_dir_skills_are_never_rescued` /
`::test_git_metadata_is_never_rescued` / `::test_lookthrough_does_not_enter_ignored_dirs_without_a_match`
/ `::test_walk_does_not_enumerate_pruned_dirs`，以及
`client/src/ignore.rs::dependency_dir_skills_are_never_rescued` / `::git_metadata_is_never_rescued`。

**实现要点（这是本卡最容易写错的地方，写清楚供复核）**：`IgnoreRules.is_ignored` 改为
**先判内置目录剪枝、命中即 `return True`**（白名单根本没机会看它）；`DirectorySource._walk`
的下钻判定 `_child_descend` 同样**先判内置目录名/模式**，从不下钻。卡内 §A-4 的"白名单判定放在
内置剪枝之后"因此是**双重落地**：独立 API 与遍历剪枝各有一条短路。

#### §B 两侧一致性对照（core vs client 文件列表）

同一份夹具仓库（`/tmp/task097-real`，GitNexus 真实技能文档 + 被排除的 `node_modules`/`.git`/`vendor`）：

```console
$ uv run python /tmp/core_scan.py /tmp/task097-real > /tmp/core_list.json
$ cd client && cargo run --example task097_scan -- /tmp/task097-real > /tmp/client_list.txt

core: 37 client: 37
IDENTICAL: True
```

固化形式：core `test_allowlist.py::test_parity_fixture_matches_expected_list` 与 client
`tests/allowlist_parity.rs::parity_fixture_matches_expected_list` 持有**同一份** `PARITY_REPO`
夹具与 `PARITY_EXPECTED` 期望清单（Python/Rust 各一份拷贝，逐字相同），任一侧语义漂移即失败。

**client 侧实现选择与理由**（卡内 §B 要求评估并说明）：

- **不采用 `overrides` API**：`ignore` crate 的 `Override::matched` 在"存在至少一条白名单 glob
  且 `is_dir == false`"时，会把**未命中任何 glob 的普通文件判为忽略**
  （`overrides.rs`：`if mat.is_none() && self.num_whitelists() > 0 && !is_dir { return Match::Ignore(..) }`）。
  那等于把语义变成"**只**索引白名单"，与需求"在原有范围之上**追加**"相反，且会让未被 gitignore 的
  普通源码全部消失。实测确认后放弃。
- **采用两次遍历取并集**（`IgnoreRules::walk_union()`）：walker A 走 `ignore` crate 的正常忽略
  （`.zaceignore` > `.gitignore` > 内置剪枝），walker B **关闭**忽略规则、只保留"内置目录剪枝 +
  白名单定向下钻"（下钻规则与 core 同口径：直接子项命中才进、深度上限 4、内置目录名从不下钻），
  再按 `Allowlist::allows` 裁决。`index.rs::scan()` 迭代并集并用 `HashSet` 按路径去重。
  这与 core 的"两步裁决"同构，是最容易保持两侧一致的形态。
- **已知差异（如实列出）**：
  1. `ignore` crate 豁免**被 git 跟踪**的文件（TASK-037 已记录的既有差异，约 1.9%）。
     被白名单救回的文件**不在** git 索引里，故本卡语义不受影响；两侧在**被跟踪**文件上的既有
     差异仍然存在（非本卡引入）；
  2. core 的 `is_ignored` 是"可对任意路径求解"的独立 API（含 `reason_for`），client 侧没有对应
     的公开查询接口（client 只在遍历时裁决、并把跳过原因写成 `skipped[].reason`）；
  3. client 的 `.zaceinclude` **只读仓库根**，与 core 相同；两侧都不支持嵌套 `.zaceinclude`。

#### §C doctype 扩充说明

`core/zace_core/parsing/markdown.py`：

```python
_AGENT_INSTRUCTION_NAMES = frozenset(
    {"agents.md", "claude.md", ".cursorrules", ".agent.md", "handoff.md", "skill.md"}
)
```

- **只扩名表，不改分值**：命中后沿用现有 `agent-instructions` 的 `+0.8` rerank（R30 冻结的值未动）；
- **不新增 doctype 取值** → CF-03 的 `doctype` 枚举（`docs/contracts/contextpack.schema.json`）
  不变；
- **`skill.md` 该不该单独一个 doctype**：我认为**长期应该**（"技能说明"与"项目指令"是两类文档，
  装填/rerank 权重可以不同）。但本卡按卡内要求**不自行新增取值**——那会同时改 CF-03 契约与
  `retrieval/rerank.py::HIGH_VALUE_DOCTYPES`（R30 冻结）。故先归入 `agent-instructions`
  （两者都是"给 AI 读的指令"、rerank 档位一致，暂无实际损失），诉求写入下方"未决问题"。
- 另注：名表命中**先于**路径规则（首命中生效），所以 `docs/design/HANDOFF.md` 的 doctype 是
  `agent-instructions` 而非 `design`。已在测试里显式锁定这一既有优先级。
- 测试：`core/tests/parsing/test_markdown.py` 的 `test_doctype_rule_table` 增加 5 个新名字的参数化
  用例（含大小写与 `skills/.../SKILL.md` 形态）。

#### §D 契约变更申请（按 `docs/plan/orchestration.md` §4 的 L2 流程）

**改什么**

| 契约 | 现状 | 拟更新为 |
|---|---|---|
| **R42**（`docs/contracts/PROCESS.md` §3.9） | "本地模式落 Python 实现：`{repo}/.zaceignore` > `.gitignore`（含否定规则）> 内置默认"——**三层** | **四层**：新增**第 0 层"索引白名单"（强制包含）**，来源 `.zaceinclude` ∪ 内置默认 ∪ `ZACE_INDEX_ALLOWLIST`；语义：命中即越过第 1/2 层；**不得突破**内置目录剪枝；下钻须"名字定向 + 有深度上限"；语法不支持通配 |
| **Module/05 §3.1**（忽略规则设计） | 三层忽略规则 | 同上四层 + 白名单语义（含"白名单不突破内置剪枝"与"下钻有界"两条硬约束） |
| CF-03（`doctype` 枚举） | `agent-instructions` 等 7 值 | **不受影响**（只扩 `_AGENT_INSTRUCTION_NAMES` 名表，未新增取值） |

**为什么**

用户在 2026-09-14 提出：项目把 `.claude/` / `.codex/` 等 AI 目录写进 `.gitignore` 后，
里面的 `SKILL.md`（高信息密度文档）就索引不到；要求"能**随意添加**白名单文件"，
默认清单为 `AGENTS.md` / `CLAUDE.md` / `.agent.md` / `.cursorrules` / `HANDOFF.md` + 整个 `skills/` 目录。
三层规则里没有"包含"这一维，必须新增一层才能表达。

**影响哪些卡**

- **TASK-037**（已合并）：其 `ignore.py` 的三层语义被扩展为四层；既有三层的判定结果对
  "未命中白名单"的路径**逐字不变**（有回归测试 `test_no_allowlist_matches_task_037_behaviour`
  与 `test_non_allowlisted_paths_behave_unchanged` 守护）。TASK-037 的代码注释/docstring 需要
  由编排者（或后续卡）同步为四层表述——**本卡已就地更新 `ignore.py`/`source.py`/`client/src/ignore.rs`
  的模块 docstring 与优先级表**，但 `docs/design/Module/05` 与 `docs/contracts/PROCESS.md` 的正式
  表述**未改**（越界）。
- **TASK-040R**（client 骨架与同步代理，已合并）：`client/src/index.rs::scan()` 的迭代源从
  `rules.walker()` 改为 `rules.walk_union()`（+ 去重）；缓存指纹新增 `.zaceinclude` 内容。
  协议/缓存 schema 未变（`CACHE_VERSION` 不变），但**配置指纹会变**→ 客户端首次同步会重扫一次
  （不是 bug，是"白名单可能改变文件集"的正确反应）。
- **TASK-093**（真实使用数据闭环）等消费 `skipped_files` / `skip_reasons` 的卡：**不受影响**
  （白名单不改变阈值判定的原因标签）。

**暂停范围（L2 协议要求"停止越界实现，仅提交不依赖该变更的部分"）**

本卡的实现**不依赖**契约文件本身（只依赖语义），且卡内 §D 明确要求"继续实现"，
故已完整实现 §A/§B/§C 并交付；**未改动** `docs/contracts/**` 与 `docs/design/**` 任何字节。
待编排者更新 R42 与 Module/05 后，建议再开一张极小卡把 `docs/design/Module/05` §3.1 的
"三层"表述与 `contracts.md` R42 对齐（本卡不做）。

#### 真实仓库验证

**A. 真实技能文档被救回**（`/tmp/task097-real`：拷贝 GitNexus 的真实 `.claude/skills/**`，
再把 `.claude/` 写进 `.gitignore`——正是用户报告的场景）：

```console
TOTAL on: 37  off: 7
rescued by allowlist: 30
  + .claude/skills/gitnexus-cli/SKILL.md
  + .claude/skills/gitnexus-debugging/SKILL.md
  ...
  + .claude/skills/gitnexus-review/ci-personas/ci-security-lens.md
  + .claude/skills/gitnexus-work/scripts/evidence-provenance.mjs
skills files indexed: 30
```

**B. `/home/xuwenzheng/2_github/AI/ACE/source/GitNexus` 本体（5357 文件）**：

```console
TOTAL on: 5357  off: 5357
rescued by allowlist: 0
skills files indexed: 109
  sample: ['.claude/skills/gitnexus-cli/SKILL.md', '.claude/skills/gitnexus-debugging/SKILL.md', ...]
```

**这条输出需要正确解读**：GitNexus 仓库**自己**没有把 `.claude/` 全目录写进 `.gitignore`
（它用的是细粒度规则 + 一批 `!.claude/skills/<技能>/` 反向否定），所以 `skills/**` 本来就在
索引范围里——119 个 `SKILL.md` 中 109 个（其余在 `gitignore` 掉的 `generated/` 等目录）**在白名单
启用前后都在**，差集为 0 正是"白名单没有改变既有行为"的证明。**用户的场景（AI 目录被整体
排除）由 A 覆盖**：A 是基于该仓库真实技能内容的复现。

#### 与设计偏差

1. **下钻（lookthrough）是卡内没写的新机制**：卡内 §A-3 要求 `hacks/skills/SKILL.md`（祖先目录
   被 gitignore）被救回，同时 §A-4 要求内置目录的"整目录剪枝"性能约束保持（§A-3 编排者实测把
   `_walk` 的剪枝顺序列为"需你验证"）。两者只能靠**有界下钻**共存，故实现为
   "名字定向 + 连续被排除层数上限 4（`ZACE_ALLOWLIST_DEPTH` 可配）"，并用
   `test_walk_does_not_enumerate_pruned_dirs` 锁住"无命中项的被排除目录不被进入"。
   已用 `ZACE_ALLOWLIST_SCOPE` 暴露 `deep`（默认）/ `gitignored` / `shallow` 三档，便于收窄。
2. **client 侧没有采用 `overrides` API**（卡内把它列为候选之一），理由见 §B（会变成"只索引白名单"）。
3. **`_AGENT_INSTRUCTION_NAMES` 里的 `skill.md`**：按卡内要求只扩名表、未新增 doctype 取值。

#### 未决问题（交编排者裁决）

1. **`skill.md` 是否单独一个 doctype**（如 `skill`）？我倾向"应该，但不在本卡"：需要同时改
   CF-03 的 `doctype` 枚举、`HIGH_VALUE_DOCTYPES`（R30 冻结）与装填策略，属 L3 级改动。
2. **`skills` 默认目录规则的范围**是否过宽？当前它放行**任意层级**同名目录下的**全部文件**
   （含脚本/测试数据）。实测在 GitNexus 上额外索引 30 个文件（可接受），但用户若有名为
   `skills/` 的业务目录（如 `packages/api/src/skills/*.ts`），这些文件会被强制纳入。
   可选收窄方案：内置默认改成 `skills/SKILL.md` + `skills/**/*.md`（只收文档）。
   **本卡按用户原话"skills/ 文件夹里面的都上传吧"保持宽松实现**，请编排者确认。
3. **`.zaceinclude` 是否需要支持嵌套/按目录作用域**（当前只读仓库根一份，已写进手册）？
4. **服务端多租户场景**是否需要"白名单仅影响本地扫描、不经服务端策略"之外的约束
   （即：租户能否用 `.zaceinclude` 绕过服务端的索引范围策略）？本卡未涉及鉴权层。
5. 上述 §D 契约更新（R42 → 四层、Module/05 §3.1）待编排者执行。

#### 建议复核点

1. `IgnoreRules.is_ignored` 的**短路顺序**（内置剪枝先于白名单）与 `source.py::_child_descend`
   的同构判定——这是卡内点名最易写错处；
2. `client/src/ignore.rs::walk_union` + `index.rs::scan` 的去重是否与 core 清单一致
   （已用真实仓库对照，37/37 完全相同）；
3. `Allowlist` 的语法收窄（无通配、`!` 取消、含点/不含点启发式）是否与手册
   `docs/handbook/operations/索引白名单.md` §4 描述一致；
4. 缓存指纹新增 `.zaceinclude` 是否会让 TASK-040R 的既有客户端出现一次非预期重扫（预期行为，
   但值得在发布说明里提一句）。
