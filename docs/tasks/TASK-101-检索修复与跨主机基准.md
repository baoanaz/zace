# TASK-101：检索质量修复与跨主机基准复现（实测驱动）

> 状态：review ｜ 阶段：Phase 5（质量）｜ 硬依赖：无 ｜ soft 依赖：TASK-091（评测靶场）
> 分支：`feature/task-101-retrieval-fix_xwz0915`
> 交付物所有权：
> - `core/zace_core/retrieval/`（新增 `literal.py`、`qcache.py`；改 `__init__.py`/`fusion.py`/`rerank.py`/`expand.py`）
> - `core/zace_core/storage/store.py`（新增三个只读查询方法）
> - `core/zace_core/engine.py`（查询覆盖率缺口、`bind_repo`/`set_query_cache`/`set_provider`）
> - `core/zace_core/cli/app.py`（`--project-id` / `--vector-cache` / `--replay` / `--repo` 可选）
> - `core/tests/retrieval/`、`benches/golden/cockpit-agents-py/`、`benches/README.md`、
>   `benches/results/`、`scripts/bench-bundle.sh`、`.zaceignore`
> - `service/zace_service/mcp.py`（**仅**两个工具的 description 文案）
>
> **不得改**：`docs/contracts/**`、`zace_core/{types,interfaces,hashing}.py`、已冻结的质量参数
> （`docs_ratio` / `CONSENSUS_SCORE_RATIO` / TASK-095 的 `score_ratio` / 原有 12 条 rerank 特征分值）。

## 背景（用户 2026-09-14 实测后拍板）

一个外部 AI 客户对 zace 两个工具做了逐条核对，指出**架构题答错**：它断言"这个仓库没有 main() 入口"，
而实际入口写在 `pyproject.toml` 的 `[project.scripts]` 里（`cvi-agent-aibox = "cvi_agent_product.app.host:main"`）。

用户要求：**先建真实靶场基准（30 题量级）、答案由 AI 读码核实，再做优化**，并明确"时间换准确度"可接受
（单次检索 0.5–1s，愿意用 5s）。本卡兑现这条路线。

## 目标

1. 建立 `cockpit-agents-py` 靶场 + 32 条真实问题基准（覆盖架构链路 / debug / 日志存储 / Runtime 设计 /
   Tool 清单 / 上下文窗口 / HMI / SDK 对接等 Agent 真实会问的场景），答案经**读码核实**；
2. 仅依据实测定位并修复检索缺陷，**每项修复都要有 A/B 数据**，无效果的一律删除；
3. 让基准可以**跨主机 / 离线复现**（换 WSL、另一台机器、没有靶场代码也能跑分）。

## §A 字面量通道（`literal`）

**缺陷（实测）**：`cvi-agent-aibox` 在 `pyproject.toml` 里是字面量，但 jieba 把它切成
`cvi / - / agent / - / aibox`，BM25 走 OR → 被 `agent` 命中的 691 个块淹没。实测池内 rank 10、
rerank 后 21，被装填闸门挤出 → 外部客户据此得出"仓库没有 main 入口"。

**实现**：新增通道（不切分、不调分词器，直接子串命中）：
- 强短语（反引号原文 / 含 `-=/:` 的长串 / 全大写长串）→ tier 0，吃 `explicit literal` +1.0；
- 弱短语（标识符词根，**只匹配符号名**）→ tier 1，吃 `literal root` +0.4；
- `key=VALUE` 形态额外尝试 `PREFIX.VALUE` 去前缀写法（`confirmation=REQUIRED` → `ConfirmationPolicy.REQUIRED`）。

**为什么 BM25 不加短语查询**：会改变既有 OR 召回与已冻结的排序行为（R29/R30），因此单开通道。

## §B 图扩展落到定义块（`Store.chunk_covering`）

**缺陷**：符号无 `chunk_id` 即整条边丢弃。符号表里 `(module)` 这类符号（以及类骨架之外的声明）
没有 `chunk_id`，而它们常是真实 call 边端点——实测 `capability_definitions` →
`tools/hmi/definitions.py` 整条边被丢，"业务 Tool 定义在哪个文件"在图扩展侧完全不可见。

**实现**：符号表已给行号，退回 `chunk_covering(file_path, start_line)` 取覆盖该行的切片。
**仍不编造**：拿不到行号或找不到覆盖切片才返回 `None`。

## §C 同名符号消歧（实测结论：无效果，未保留）

曾判断"同名 `main` 跨 8 个文件被 tierbreak 到错的文件"是主因，实现了"符号简名等值 +0.5"，
**A/B 实测开关闭合对两套 golden、全部 32+20 题排名零变化** → 已删除，不留在代码里。
真实原因见 §A（字面量被切碎），不是同名消歧。

## §D 查询覆盖率缺口（`query_partially_matched`）

**缺陷（真实客户反馈）**：`confidence` / `answerable` 奖励多通道共识，因此"主题词被召回、
但查询里的具体指纹一个都没进包"时仍报 `answerable=true / medium`，Agent 无从得知自己拿到的是背景材料。

**实现**：装填后统计查询内容词在包内的覆盖率，低于 `QUERY_COVERAGE_FLOOR=0.34` 时**追加**一条
`missing_evidence`（`code=query_partially_matched`），并在 `next_queries` 为空时补一条自愈查询。
**只增字段**：不动 `answerable` / `confidence`（R22 冻结口径）。

## §E benchmark 放行：`--project-id`

**问题**：数据目录名 = D-29 身份算出的 `projectId`，而身份只由 git remote + 仓库内相对路径决定；
换 checkout 路径 / 无 `.git` 副本 / 新 worktree 都会解析到**另一个** id，进而找不到索引。

**实现**：`--project-id` 直连该 id，跳过身份计算与 `project.json` 核验。
纪律：索引缺失/维度不符时**如实报错**（`DimensionMismatchError`），不静默重建。

## §F 跨主机离线复现（`--vector-cache` + `--replay` + bundle 脚本）

**关键发现**：向量通道在**查询时**才调 `embed_query()`（CF-09），因此只带索引（`index.db`+`vectors/`）
到另一台机器是**不够的**——没 key 会静默降级成 BM25+Exact，指标与出题机器不是同一口径。
故把"查询 → 向量"也固化成侧车文件（`PersistentQueryVectorCache`），并提供 `CachedOnlyProvider`。

三条纪律（均有反例验证）：

1. **未命中必须可见**：`--replay` 下未命中 → 该用例走向量通道降级并计入报告，**不**静默换 BM25；
2. **指纹必须对得上**：侧车/索引/当前配置三者 model+dim 不一致 → 直接拒绝；
3. **指纹以索引为准**：`--replay` 从 `index_config` 读 `(model, dim)`，**不读环境变量**
   （目标机 env 会回落到默认本地模型：实测 384 维 vs 索引 1024 维，整轮 0 分）。

顺手把 `--repo` 改为在给了 `--project-id` 时可省略（`eval`/`search` 只读索引，不需要靶场源码）。

## §G 工具分工文案（`search_context` vs `ask_project`）

按"答案形态"而非"深浅"分：`search_context` = 定位器（不调 LLM、可多轮）；`ask_project` = 判断器
（唯一调 LLM 者）。文案写清使用时机与"拿到结果后怎么走"（`query_partially_matched` /
`status=insufficient_evidence` / `nextQueries` 的处理）。**仅改 description**，工具名/参数/类型不动（CF-06）。

## §H 自索引回音消除（`.zaceignore`）

`benches/golden/**` 存的就是查询原文且躺在被索引仓库内 → 查询命中自己（实测 `zace-0110`/`zace-0117`
的 top-3 出现 `benches/golden/zace/zace.jsonl`）。用仓库根 `.zaceignore` 排除 `benches/golden/` 与
`benches/results/`。**放项目层而非改 `DEFAULT_SKIP_DIRS`**：只有 zace 自己存在该自引用，
不该改变 core 对所有仓库的行为。

## 验收标准（DoD）

- [x] `uv run ruff check .` → All checks passed
- [x] `uv run python scripts/check_dependency_direction.py` → 通过
- [x] `uv run pytest -o addopts="" -q` → **1020 passed, 2 skipped**
- [x] cockpit 基准：R5 0.733 → **0.767**、R10 0.833 → **0.867**、MRR 0.408 → **0.505**、负例 2/2
- [x] zace dogfood：MRR 0.454 → **0.480**（含回音消除）；R5 0.684 → 0.632（见未决问题 1）
- [x] 离线跨主机实测：无靶场代码 + 无 key + 断网 → 指标与出题机器**完全一致**
- [x] 每项修复都有 A/B 数据；无效果的（§C）已删除

## 明确不做

- 不动 R29/R30 冻结参数（`docs_ratio` / `CONSENSUS_SCORE_RATIO` / `score_ratio` / 原 12 条特征分值）；
- 不做 fan-out 多轮检索、Gap 二轮、LLM rerank（用户先看架构再定，见未决问题 2）；
- 不改 CF-03/05/06 契约；不改 `types/interfaces/hashing.py`。

## 执行记录

### 2026-09-14/15 实施

**靶场与基准**：`cockpit-agents-py @ febac6d`（287 文件 / 3416 切片 / 25 个 business capability）。
32 条用例（symbol 8 / path 3 / behavior 13 / spec 6 / negative 2），答案逐条读码核实；
含"入口在哪"「有多少 Tool」「日志落哪」「上下文窗口组成」「HMI/SDK 如何对接」等 Agent 真实问题。

**A/B 归因（两套 golden，逐机制开关）**：

| 机制 | 实测效果 | 处理 |
|---|---|---|
| §A 字面量通道 | cockpit R5 +0.034 / R10 +0.034；zace MRR +0.026 | 保留（权重 2.0→1.0，见未决问题 1） |
| §A 弱短语（词根扫符号名） | 关掉后 zace MRR 0.439→0.399、cockpit 0.505→0.497 | 保留 |
| §B 图落定义块 | **指标零变化**（仅候选数 0→30） | 保留，**不声称质量收益** |
| §C 同名消歧 | **逐题完全相同** | **已删除** |
| 词根扫正文（早期尝试） | 两套 golden 都掉分 | 已否决并删除 |

**跨主机实测**（`/tmp/fresh-host` 全新数据根 + `env -u` 删 key + 代理指向死端口）：

| | recall@5 | recall@10 | MRR | 负例 |
|---|---|---|---|---|
| 出题机器（联网） | 0.767 | 0.867 | 0.505 | 2/2 |
| 另一主机（无码/无 key/断网） | **0.767** | **0.867** | **0.505** | **2/2** |

bundle 体积实测 17M（索引）+ 0.7M（32 条查询向量侧车）。

**验收命令输出**：

```
uv run ruff check .                                  → All checks passed!
uv run python scripts/check_dependency_direction.py  → 依赖方向检查通过（core 纯库 / service 不上探）
uv run pytest -o addopts="" -q                       → 1020 passed, 2 skipped
```

### 未决问题（请编排者裁定）

1. **字面量权重与 zace R5 的取舍**：字面量命中权重从 2.0 降到 1.0 是实测最优（保 R10 与 MRR，
   2.0 会把无关短配置块顶到 top-1）。但 zace dogfood 仍有一题退步：`zace-0111` 从 rank 3 → 6
   （**仍在 R10 内**），换来 `zace-0109`(3→2)、`zace-0115`(2→1) 前进与 MRR 净涨。
   是否接受这个取舍，或进一步降权（0.6/0.8 实测与 1.0 逐题相同），请裁定。
2. **剩余 4 道 cockpit 失败题不是召回问题**：`0018`/`0019`/`0022` 的证据**在候选池内但被
   spec 配额（`docs_ratio=0.10`）与相对分数闸门（`score_ratio=0.5`）挡在包外**；`0012` 同理。
   两者都是 TASK-095 已冻结参数，本卡未动——是否放开属架构决策。
3. **bundle 分发位置未定**：建议内网共享盘 / Release 资产（**不用 git-lfs**：17M 二进制会被每个
   克隆者拉满，而只有想跑分的人需要）。
4. **`test_package_boundaries.py` 期望 26 个业务 Tool，实际 25**（靶场仓库的既有不一致，
   非本卡引入）——已在 golden 的 notes 里记录，未改靶场。
