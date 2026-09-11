# 多仓库规模自举与索引健壮性（TASK-036）

> 状态：进行中（§A 部分靶场仍在跑，见 §A.1 的"未完成"标注）
> 分支：`feature/task-036_xwz0910`（从 `main` @ `ea4084d` 开出）
> 原始证据：`~/.zace-lanec/raw.jsonl`（每靶场一条 JSON，含**全部** errors/skipped_files）、
> `~/.zace-lanec/logs/<n>.log`（含 `/usr/bin/time -v` 的峰值内存）、
> `~/.zace-lanec/section_c.json`（§C 的构建产物占比数字）。
> 复现脚本：`~/.zace-lanec/scripts/{run_target,section_c,before_after_chunk_ids}.py`（临时工具，不入仓库）。
>
> **一句话结论**：规模自举在**真实仓库上重现了阻断级形态**——Obsidian 靶场有 7 个压缩
> JS/CSS 文件因 chunk id 冲突被**整份静默跳过**（10.0 MB 内容不入索引），根因是
> `split_fallback` 的"单行超长硬切"产出共享同一 `start_line`；另发现一条"读不了的文件
> 中止整次 ingest"的隔离缺口。两条都已修且有回归测试。**索引耗时几乎全部花在本地
> embedding 推理上**（Obsidian：4095 chunks / 2327s，解析+切分只占 4s），因此
> `hmi`（4.7 万 chunks）在 90 分钟预算内跑不完——这是可复现的算力事实，不是本卡该修的 bug。

## 0. 靶场与口径

| # | 仓库 | 可索引文件 | 可索引字节 | >128KB | 二进制(NUL) | 用途 |
|---|---|---|---|---|---|---|
| 1 | `notace-tool-rs` | 8 | 17 KB | 0 | 0 | 无 Rust 解析器 → 兜底路径 |
| 2 | `Obsidian-XuWenzheng` | 181（+74 未知扩展名文本） | 1.0 MB | 76 | 255 | 纯文档仓库 |
| 3 | `linux-mtk-hmi-framework` | 93 | 0.4 MB | 4 | 544 | 小 C++ 仓库 |
| 4 | `linux-mtk-mw-systemservice` | 107 | 3.3 MB | 5 | 1738 | 最大单文件 76 MB |
| 5 | `linux-mtk-hmi` | 1667 | 16.7 MB | 17 | 2687 | **规模上限** |
| 6 | `Trellis` | 1040 | 8.4 MB | 0 | 25 | 混合大仓库 |

"可索引" = 扩展名在 `parsing.registry.EXTENSION_LANGUAGE` 内且未被 `DEFAULT_SKIP_DIRS` 跳过。
命令一律 `zace-core ingest --repo <路径> --data <数据根>`（本卡用等价的
`Engine.ingest_repo` 调用，以便拿到 CLI 会截断的完整 `errors` / `skipped_files`）。
数据根放**持久目录** `~/.zace-lanec/data/<n>`：本会话第一次尝试用 `/tmp`，被 WSL 重启清空，
证据全丢——这类长跑的产物不该放 `/tmp`。

环境（都会影响绝对耗时，报告里按此读）：

```text
CPU 6 核 / 内存 15G（实测 embedding 只用到 ~2 核，见 §A.4）/ WSL2 Ubuntu 24.04
embedding 默认路径：local:multilingual-e5-small（D-44，384 维，ONNX + onnxruntime）
本机同时有另外两条泳道（lane A 跑 service、lane B 跑 bge-m3 bake-off）在抢 CPU/内存，
因此**本报告的耗时是上界**；其中 systemservice 的首轮运行被内存压力杀掉后重跑（见 §A.1 注）。
```

## §A 测量

### A.1 六靶场汇总

| # | 靶场 | ingest 耗时 | files_parsed | chunks | symbols | edges | errors | skipped | orphan | 向量数 | 索引体积 | 增量二次 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `notace-tool-rs` | 118.5s | 44 | 112 | 0 | 0 | 0 | 0 | 0 | 112 | 1.6 MB | 0.0s |
| 2 | `Obsidian` | 2327.2s | 256 | 4095 | 0 | 0 | 0 | 255 | 0 | 4095 | 52.9 MB | 0.8s |
| 3 | `hmi-framework` | 648.8s | 135 | 1756 | 1548 | 1141 | 14 | 544 | 0 | 1756 | 7.4 MB | 0.9s |
| 4 | `systemservice` | 1678.7s | 347 | 4585 | 3706 | 1401 | 21 | 1738 | 0 | 4585 | 51.9 MB | 3.5s |
| 5 | `hmi` | 见 §A.3 | | | | | | | | | | |
| 6 | `Trellis` | 见 §A.3 | | | | | | | | | | |

注：`notace-tool-rs` 的 118.5s 含两次 ingest + 检索冒烟（§A 口径统一为"ingest 段"的计时，
`chunks/s` 换算只在 §A.4 用），且该次运行与 lane B 的 bake-off 并发，属上界。

**`errors` 的完整口径**：本卡报告的 `errors_count` 含两类——
（a）解析器**语法告警**（`parse_errors`，不影响入库，例如 `missing ;`）；
（b）文件级**失败**（切分/落库/读取异常，该文件被跳过）。
第 1、2 项为 0，说明这两个靶场零告警；`hmi-framework` 的 14 条全部是 (a) 类语法告警，
逐条列出见 §A.2。

### A.2 逐靶场事实

#### 1. `notace-tool-rs`（8 个 `.rs`，无 Rust 解析器）

```text
files: added=44 modified=0 deleted=0 parsed=44
chunks: new=112 reused=0 removed=0
vectors: upserted=112
graph: edges_retargeted=0 unresolved_resolved=0 spec_refs=0 ambiguous=0
errors: 0   skipped: 0   orphan: 0
languages: ['fallback', 'markdown']
chunk kinds: spec_block=74, fallback_block=38
db: files=44 chunks=112 symbols=0 edges=0 spec_blocks=74
elapsed: 118.5s（含增量二次 + 2 条检索冒烟）
```

结论：**8 个 `.rs` 一个都没进符号表，全部走 `fallback` 兜底**（`languages=['fallback','markdown']`），
但检索仍可用（见 §A.5）。这正是设计预期（无 Rust 解析器 → 兜底），但也是 §C 的产品观察项：
Rust 文件在**文件名/注释/字符串**层面可被 BM25 命中，符号级检索（Exact-Inferred、图扩展）完全缺失。

#### 2. `Obsidian-XuWenzheng`（纯文档，540 磁盘文件）

```text
files: added=256 modified=0 deleted=0 parsed=256
chunks: new=4095 reused=0 removed=0
vectors: upserted=4095
errors: 0   skipped: 255   orphan: 0
languages: markdown=181, fallback=75
chunk kinds: spec_block=3602, fallback_block=493
skip reasons: binary-image=246, binary-other=4, binary-data=3, binary-obsidian-mdc=2
db: files=256 chunks=4095 symbols=0 edges=0 spec_blocks=3602
index dir: 52.9 MB   elapsed: 2327.2s (38.8 min)   增量二次: 0.8s
```

**这是本卡最重要的靶场**：修复前它在索引期报出 7 条

```text
.obsidian/plugins/dataview/main.js: ValueError: ... 切分产物出现重复 chunk id（禁止静默去重/丢弃）：
  .obsidian/plugins/dataview/main.js:(module):12784 × 15
```

即 7 个文件**整份被跳过**（详见 §B.1）。修复后 `errors=0`、`files_parsed=256`。

另外注意：**255 个文件被当二进制跳过**，其中 246 个是图片（27.2 MB）。
`symbols=0` 是对的（纯文档无代码符号），但 `spec_blocks=3602` 说明 MD 结构化资产被完整接住。

#### 3. `linux-mtk-hmi-framework`（C++，135 个入库文件）

```text
files: added=135 modified=0 deleted=0 parsed=135
chunks: new=1756 reused=0 removed=0
vectors: upserted=1756
graph: edges_retargeted=111 unresolved_resolved=97 spec_refs=0 ambiguous=202
errors: 14（全部为 C++ 语法告警）   skipped: 544   orphan: 0
languages: cpp=89, fallback=42, c=3, markdown=1
chunk kinds: method=1327, fallback_block=188, macro=76, class_skeleton=70, function=44,
             spec_block=20, typedef=16, struct=10, enum=5
db: files=135 chunks=1756 symbols=1548 edges=1141 spec_blocks=20 unresolved=260
index dir: 7.4 MB   elapsed: 648.8s (10.8 min)   增量二次: 0.9s
```

14 条语法告警的完整清单（全部为 (a) 类，文件照常入库）：

```text
Include/framework/Gui/ivi-application-client-protocol.h: L247: missing #endif
Include/framework/Message/MsgBindBase.h: L32: syntax error near '...'
Source/FantasyGui/CThemeImp.cpp: L35: missing ;; L37: missing ;
Source/FantasyGui/ivi-application-protocol.c: L50: missing ;; L60: missing ;
Source/Language/CLanguageImp.cpp: L36,55,66,78,127,263,317,465,489,548,551: missing ;
Source/MsgRoute/WorkQueue.cpp: L160: syntax error near 'return'
Source/Page/PageCounter.cpp: L318; L330: missing ;
Source/Page/PageManager.cpp: 18 处（L233,264,744,747,796,920,934,995,1029,1033,1041,1050,1070,1072,1074,1077,1080）
Source/Utils/Mutex.cpp: L70,102,119: missing ;
Source/Utils/hmistring.cpp: L77,89,111,117,124,133,140,173,195: missing ;
cmake-build-release/CMakeFiles/3.12.2/CompilerIdC/CMakeCCompilerId.c: L523..L623（构建产物）
cmake-build-release/CMakeFiles/3.12.2/CompilerIdCXX/CMakeCXXCompilerId.cpp: L508..L573（构建产物）
cmake-build-release/CMakeFiles/feature_tests.c: L4,11,18,25（构建产物）
cmake-build-release/CMakeFiles/feature_tests.cxx: L4..L67（构建产物）
```

**交接给 TASK-037**：14 条里有 4 条来自 `cmake-build-release/`，而该目录**根本不该进索引**
（见 §C）。语法告警里也混着"宏行被当代码"的噪声，但那是 C++ 抽取器的已知边界（R7/R6），
不属本卡。

#### 4. `linux-mtk-mw-systemservice`（C++，347 个入库文件 / 磁盘 160 MB）

```text
files: added=347 modified=0 deleted=0 parsed=347
chunks: new=4585 reused=0 removed=0
vectors: upserted=4585
graph: edges_retargeted=19 unresolved_resolved=89 spec_refs=0 ambiguous=12
errors: 21（全部为 C/C++ 语法告警）   skipped: 1738   orphan: 0
languages: fallback=240, cpp=102, c=3, markdown=2
chunk kinds: method=2859, fallback_block=853, macro=325, function=320, enum=90,
             class_skeleton=77, spec_block=34, struct=15, typedef=12
db: files=347 chunks=4585 symbols=3706 edges=1401 spec_blocks=34 unresolved=1095
skip reasons: binary-other=1692, binary-archive-or-object=46
index dir: 51.9 MB   elapsed: 1678.7s (28.0 min)   增量二次: 3.5s
峰值 RSS: 2,410,568 KB（2.3 GB）   wall clock: 28:16
```

**注意 `languages: fallback=240`**：347 个入库文件里 240 个走兜底——因为它们大多是
`dbus/*.c`、`usb.log`、`*.make` 这类"没有解析器但非二进制"的文本（详见 §C.3）。
检索仍正常（见 §A.5）。

`errors` 21 条的形态：多为 `missing ;` / `syntax error near`（宏行、GNU 属性、
`dbus` 的 GObject 宏），另有 4 条来自 `cmake-build-release/CMakeFiles/feature_tests.*`
等构建产物——**构建产物不仅浪费时间，还在产生噪声告警**（§C.3）。

### A.3 未完成的靶场（时间预算与进度）

**先记一条发生在测量过程中的运维事实**：`systemservice` 的首轮运行在 10:36 被系统杀掉
（`files=347 chunks=4585` 已落库，embedding 阶段被中断），随后我改用 `setsid` 完全脱离会话、
并加内存闸门（<4 GiB 可用则等待）重跑。原因是本机同时有 lane A（service 索引 aibox）与
lane B（bge-m3 bake-off，RSS ~3 GB）在跑，`MemAvailable` 一度降到 6 GiB 以下。
**这不是 zace 的缺陷**，但它说明"索引一个 3000+ 文件仓库"的内存峰值必须被显式设计
（实测单仓峰值 2.3 GB，见 §C.1）。

（`hmi` 与 `Trellis` 的最终数字在此回填。）

### A.4 什么在拖慢索引（"最慢/最大文件 Top 5"的答案）

**结论：耗时 ≈ 本地 embedding 推理时间，与文件大小、chunk 数近似线性；解析、切分、
二阶段解析（SQL）都不是瓶颈。**

直接实测（同一进程内，`local:multilingual-e5-small`，本机 6 核）：

```text
embed 256 × ~200 chars  : 20.78s   12.32 chunks/s   81.2 ms/chunk
embed 256 × ~800 chars  : 70.40s    3.64 chunks/s  275.0 ms/chunk
embed 256 × ~2000 chars : 126.21s   2.03 chunks/s  493.0 ms/chunk
embed 128 × ~6000 chars : 63.69s    2.01 chunks/s  497.6 ms/chunk
jieba 分词（FTS 写入路径，同批）: 137.5 chunks/s
```

对照整仓实测：

| 靶场 | chunks | ingest 耗时 | 每秒 chunk | 解析+切分实测 | 二阶段解析 SQL 实测 |
|---|---|---|---|---|---|
| Obsidian | 4095 | 2327s | 1.76 | 4.0s | `unresolved_edges()` 0.01s |
| hmi-framework | 1756 | 649s | 2.71 | 0.8s | `unresolved_edges()` 0.01s（894 行） |

即 **Obsidian 的 2327s 里，解析+切分只占 4s（0.17%）**；其余是 embedding。
`unresolved_edges()`（`target NOT IN (SELECT fqn FROM symbols)`）在 1141 条边 / 1548 个符号上
只要 0.01s，**没有出现担心的 SQL 二次方行为**。

Top 文件（磁盘字节 / 产生 chunk 数）：

```text
Obsidian     最大: .obsidian/plugins/make-md/main.js 5.7MB（201 chunks）
                   .smtcmp_vector_db.tar.gz 4.4MB（二进制，跳过）
             chunk 最多: Notion/.../学习总结.md 424、~工作/AI/Agent开发/面试题-V1.0.md 305
hmi-framework 最大: cmake-build-release/.../PageManager.cpp.o 3.2MB（二进制，跳过）
             chunk 最多: Include/framework/Gui/CViewBase.h 155、Source/FantasyGui/CViewBase.cpp 128
systemservice 最大: cmake-build-release/liblibsystemservice.a 76.6MB（二进制，跳过）
```

**CPU 只用了一半**：ingest 期间进程稳定在 ~200% CPU / 6 核（见 §C.4）。
`EmbeddingConfig` 不设 `intra_op_num_threads`，onnxruntime 默认自选——在 6 核 WSL 上
没有跑满。这是 TASK-062 的性能优化入口（本卡只测量，不优化）。

### A.5 检索冒烟（规模上去之后检索还能用吗）

| 靶场 | 查询 | answerable | confidence | 通道 | 候选池 | 首条证据 |
|---|---|---|---|---|---|---|
| notace（Rust/兜底） | `how is the MCP server started` | True | medium | bm25+vector | 65 | `server.json [1,37]` tier1 |
| notace | `src/finnian.rs` | True | high | bm25+vector | 68 | `src/finnian.rs [1,16]` tier0 |
| Obsidian（纯文档） | `令牌过期后在哪里刷新` | False | low | bm25（**向量降级**） | 50 | 3 条 `guide` 文档，全部不相关 |
| Obsidian | `Agent 开发的面试题` | False | low | bm25+vector | 97 | `~工作/AI/Agent开发/面试题-V1.0.md [31,61]`（命中正确文件） |
| hmi-framework（C++） | `view 的生命周期由谁管理` | True | medium | bm25+vector | 70 | `Source/Page/PageManager.h [42,52]` `PageManager::PageNotifyThread` |
| hmi-framework | `CViewBase::OnCreate` | True | medium | bm25+vector | 94 | `Source/FantasyGui/CViewBase.cpp [1,38]` `CViewBase::CViewBase` |

结论：**规模上去之后检索仍可用**——C++ 仓库两条查询都命中真实符号，Rust 仓库靠兜底块
也能给对文件。两个值得交接的现象：

1. **纯文档仓库 `answerable` 恒为 False**。`Agent 开发的面试题` 明明命中
   `面试题-V1.0.md`（E1，正好是问的那份文档），仍是 `answerable=False, confidence=low`。
   这是 R22/TASK-022 收紧后的判定：`answerable` 要求 explicit/inferred/结构命中或"被佐证"，
   纯 spec 证据不计。**这是产品判断**（"纯文档仓库该不该判可回答"），本卡不擅自改，写进
   §C.5 交编排者。
2. **向量通道在"新进程第一次查询"上必然降级**（下一条）。

### A.6 向量通道超时：5.0s 预算被"模型加载"吃掉（新发现，需裁决）

Obsidian 的 `令牌过期后在哪里刷新` 返回 `degraded=true`：

```text
vector 通道降级：VectorTimeoutError: vector 通道超时：5.0s 内未返回（Module/02 §5 降级为 Exact+BM25）
```

逐项计时（同一索引，4095 chunks）：

```text
query embedding（首次，含 ONNX session + tokenizer 加载）: 5.06s
query embedding（第二次，热）                          : 0.03s
vectors.search(top_k=50)  第 1/2/3 次                  : 0.033s / 0.029s / 0.016s
vectors.search(top_k=200)                              : 0.015s
recall_vector(..., timeout_s=5.0) 冷缓存 三次          : 0.11s / 0.05s / 0.07s（模型已热）
```

`RecallLimits.vector_timeout_s = 5.0` 覆盖的是 `embed_query()` + `search()` 的整体，
而**首次调用包含 ~5.0s 的模型懒加载**（`local.py` 的 `ensure_loaded`），于是
**每个新进程的第一次搜索**都会踩到这条超时并静默退化到 Exact+BM25。
对常驻的 service/MCP 进程只影响第一条查询；对 `zace-core search` 这种一次性 CLI
则是**每次都丢向量通道**（CLI 只在 stderr 打一行 warning，退出码仍是 0）。

**建议（不在本卡实施，`retrieval/vector.py` 不在本卡文件所有权内）**：在 `Engine.open`
或首次 `search` 前显式 warm-up（一次 `embed_query("")`），或把超时语义限定为
"预热后的检索耗时"。**需要编排者裁定归属卡**（性能回填 vs M2a 收口）。

## §B 崩溃与静默损坏（已修）

### B.1 chunk id 冲突 → 整个文件被静默跳过（**最严重**，实测命中 7 个真实文件）

**现象**：`Obsidian` 靶场 ingest 报 7 条 `ValueError`，每个文件整份不被索引，且
**没有任何文件被部分索引**。合计 **10,251 KB（10.0 MB）源码/样式内容消失**。

**最小复现**（不依赖大仓库，可直接跑）：

```python
from zace_core.types import ParsedFile
from zace_core.chunking import split_file
from zace_core.parsing.fallback import FALLBACK_MAX_CHARS

parsed = ParsedFile(path="assets/blob.bin", language="fallback", fallback=True)
split_file(parsed, "x" * (FALLBACK_MAX_CHARS * 2 + 10))
# 修复前: ValueError: assets/blob.bin: 切分产物出现重复 chunk id（禁止静默去重/丢弃）：
#         assets/blob.bin:(module):1 × 3
```

**根因**：`parsing/fallback.py::_split` 的兜底分支——当一段文本**找不到任何分隔符**
（`"\n\n"` → `"\n"` → `" "` 全部切不动）时按字符硬切：

```python
for index in range(0, len(text), max_chars):
    out.append((offset + index, text[index : index + max_chars]))
```

硬切只发生在**同一物理行内部**（有换行就轮不到这条分支），所以 N 个片段的
`start_line` **完全相同**；`ChunkDef.id = {path}:(module):{start_line}` 随之全等。
这不是数据不一致，而是 D-04 的 id 方案（"只用 `start_line` 消歧"）在一行多块时的**固有缺口**——
Module/01 §2.2 的取舍表里本来就写了"重载消歧 → chunk_id 后缀消歧"。

**修复**：`chunking/splitter.py` 新增 `_disambiguate_fallback_ids`：在出口前对"同 id 的
兜底块"按文档内次序补 `#N`（首块保留原 id），其余来源（同名同起始行的符号、同 heading
同起始行的 spec 块）**仍由 `_reject_duplicate_ids` 显式失败**——`#` 分隔符不参与任何 id 解析
（全仓没有 `chunk_id.split(":")` 之类的反解析），检索侧只把 id 当不透明主键。

**修复前后对照**（`~/.zace-lanec/scripts/before_after_chunk_ids.py`，把消歧步骤换成恒等即得"修复前"）：

```text
file                                                          KB              before      after  chars_kept
.obsidian/plugins/dataview/main.js                        1271.5  ValueError(1 dup ids)      47  1301998/1301998
.obsidian/plugins/heatmap-tracker/main.js                  617.4  ValueError(5 dup ids)      27   632221/632222
.obsidian/plugins/make-md/main.js                         5610.1  ValueError(35 dup ids)    201  5744763/5744765
.obsidian/plugins/make-md/styles.css                       146.0  ValueError(1 dup ids)       4   149456/149457
.obsidian/plugins/obsidian-custom-attachment-location/... 1563.9  ValueError(7 dup ids)      60  1601470/1601471
.obsidian/plugins/obsidian-git/main.js                     710.7  ValueError(1 dup ids)      30   727764/727765
.obsidian/plugins/templater-obsidian/main.js               331.6  ValueError(3 dup ids)      18   339564/339564
修复前：这 7 个文件整份被跳过（合计 10251 KB 内容不入索引）
修复后：共入库 387 个块，字符逐字守恒（无丢失、无重排）
```

（`chars_kept` 比源文件少 1 个字符的几例是文件末尾换行的规范化差异，非丢失。）

**为什么之前没被发现**：触发条件是"单行 > `FALLBACK_MAX_CHARS`（40,000 字符 ≈ 41 KB）
且无任何空白"，**不需要超大文件**——任何一个压缩过的 JS/CSS/单行 JSON 都命中。
TASK-018 §B 当时把它定成"显式失败"（比 sqlite `IntegrityError` 好），代价是**整文件丢失**；
本卡量出这个代价后在保持"不静默"的前提下改为消歧。

**回归测试**：
`core/tests/chunking/test_splitter.py::test_oversized_single_line_fallback_is_disambiguated_not_lost`、
`::test_disambiguation_is_deterministic_and_ordered`、
`::test_structural_duplicates_still_fail_loudly`（改写了 TASK-018 留下的
`test_oversized_single_line_fallback_raises_with_details`，因为那条断言的行为已被本卡强化，
原委写在测试 docstring 里）。

### B.2 一个"读不了"的文件中止整次 ingest（隔离缺口）

**现象**：仓库里存在一个文件名含反斜杠的文件时，`zace-core ingest` **整体失败**，
已解析的文件一个都留不下来：

```console
$ uv run zace-core ingest --repo <含 weird\name.py 的仓库> --data /tmp/x
zace-core: SourcePathError: 非法仓库相对路径：'src/weird\name.py'
```

**最小复现**：

```python
root = tmp_path / "repo"; (root / "src").mkdir(parents=True)
(root / "src" / "ok.py").write_text("def f():\n    return 1\n")
(root / "weird\\name.py").write_text("def g():\n    return 2\n")   # 反斜杠在 Linux 上是合法文件名
engine.ingest_repo(project_id, root)   # 修复前: SourcePathError
```

**根因（两半，归属不同）**：

- **读写口径不一致**在 `pipeline/source.py`：`list_files()` 用
  `relative_to(root).as_posix()` **原样**返回含反斜杠的路径，而 `read()` 的 `_resolve()`
  以 `"\\" in path` 为由抛 `SourcePathError`（`ValueError`）。**归 TASK-037**
  （本卡明确不得改该文件），证据与复现留在本节；
- **隔离缺口**在本卡文件内：`Indexer._collect_inputs` / `_rebuild_vectors` / `plan_scan`
  只捕 `OSError`，而 `SourcePathError` 是 `ValueError`，于是穿透了"单文件失败隔离"
  （TASK-018 §C 的 per-file 韧性）直接中止整仓。

**修复**：`pipeline/indexer.py` 新增 `_safe_read()`（捕获 `Exception`，记入
`acc.errors` 后返回 `None`）；`engine.plan_scan` 同样放宽。`KeyboardInterrupt` 等
`BaseException` 不受影响。**故意**不选"从 `list_files()` 里过滤掉这些路径"——那会把
"整仓失败"换成"静默跳过"，而该路径该不该索引属 TASK-037 的范围。

**实测覆盖度**：本机 7 个候选仓库（六个靶场 + zace 自身）**都没有**这类文件名
（脚本核对：每个仓库 0 个敌意路径）。因此这是**代码审查发现**的潜在缺陷，不是自举命中的——
报告如实区分这两类来源。

**回归测试**：`core/tests/integration/test_ingest_isolation.py`（4 条：ingest_repo 隔离、
full_reparse 隔离、干净仓库不产生假错误、变更集路径不被污染；Windows 上按平台 skip）。

### B.3 已核查但**未**发现问题的路径（避免"没查"被误读成"没问题"）

| 检查项 | 方法 | 结果 |
|---|---|---|
| chunk id 冲突（其它来源） | 全仓 grep `chunk_id.split` / `id.rsplit` 反解析 | 无任何反解析，`#N` 后缀安全 |
| 符号/spec 块越界区间 | 遍历 systemservice 全部 107 个可索引文件，检查 `start_line<1` 或 `end_line<start_line` | 0 例（`_clamp` 的静默丢弃路径未被触发） |
| 二阶段解析 SQL 二次方 | 在 1141 边 / 1548 符号上计时 `unresolved_edges()` | 0.01s |
| 向量 upsert 批次 | 读 `vectors/store.py`：`_UPSERT_BATCH_SIZE=1024`；SQLite 侧 `_SQLITE_PARAM_BATCH=500` | 均已分批，未见超参风险 |
| 单文件失败隔离（既有） | `hmi-framework` 14 条语法告警、544 个二进制跳过均未影响其它文件 | 正常 |

## §C 不接受的行为（记录 + 判据，交编排者/TASK-037）

### C.1 单文件 >50MB 的内存与耗时

`indexer._decode(data)` 先 `path.read_bytes()` 读全量再判 NUL，因此**任何大文件都要整份进内存**。
本卡实测的峰值（`/usr/bin/time -v`，见 `~/.zace-lanec/logs/<n>.log`）：

| 靶场 | 最大单文件 | 该文件处理结果 | 进程峰值 RSS |
|---|---|---|---|
| systemservice | `cmake-build-release/liblibsystemservice.a` **76.6 MB** | 跳过（前 8 KB 判 NUL） | （见 §A.3 回填） |
| Obsidian | `.obsidian/plugins/make-md/main.js` 5.7 MB | 入库（201 chunks） | ~2.1 GB |
| cameraservice（TASK-037 §D 用） | `lib/libcv.a` **308 MB** | 跳过 | — |

**量化影响**：跳过是"正确结果、错误代价"——为了判定它是二进制，进程要为它分配整份字节
（76 MB / 308 MB）。`camera` 那个 308 MB 的文件在 4GB 内存的机器上足以把进程推到危险区。
**建议**：读取前先 `stat`，按"前 8 KB 采样"判二进制（这正是 TASK-037 §B 的阈值设计），
无需整读——**归 TASK-037**。

### C.2 超大文件被切出成千上万 chunk

Obsidian 的 `学习总结.md`（0.14 MB）切出 **424 chunks**，`make-md/main.js` 切出 201 块；
hmi 预估 4.7 万 chunks。按 §A.4 的实测吞吐（2–12 chunks/s），**单文件 400 块 ≈ 2 分钟**。
当前**没有任何单文件或单仓库 chunk 上限**，也没有"这一块值不值得嵌"的判据。
**建议**：上限与阈值一起在 TASK-037 讨论（`>128KB` 跳过会顺带挡掉大部分这种文件）。

### C.3 构建产物被索引的规模占比（**给 TASK-037 的具体数字**）

| 仓库 | 磁盘可见文件/字节 | 其中 `cmake-build-*` / `lib/` / `assets/` | 入库文件 | 其中构建产物目录 | 构建产物占入库 |
|---|---|---|---|---|---|
| `hmi-framework` | 679 / 9.0 MB | 543 文件 / 8.1 MB（全为 NUL 二进制） | 135 | **43** | **31.9%** |
| `systemservice` | 2085 / 159.7 MB | `liblibsystemservice.a` 76.6 MB + ~1400 个 `.o` | （回填） | （回填） | （回填） |
| `hmi` | 4402 / 880.3 MB | `cmake-build-release/**` 为主，含 46 MB 的 `.cpp.o` | （回填） | （回填） | （回填） |
| `cameraservice` | 1382 / 332.3 MB | **`lib/libcv.a` 308.0 MB** + 10 个 `.a` | — | — | — |
| `Obsidian` | 511 / 46.5 MB | 246 张图片 27.2 MB | 256 | 0 | 0% |
| `Trellis` | 2342 / 131.6 MB | `assets/*.gif` 61.3+48.6 MB、`assets/*.png` | （回填） | （回填） | （回填） |

**关键数字**：`hmi-framework` 入库的 135 个文件里 **43 个（31.9%）来自
`cmake-build-release/`**——它们是 `.make` / `Makefile` / `.json` / `CMakeCCompilerId.c`
这类**构建产物里恰好没有 NUL 的文本**。这些文件：
（a）产生 4 条语法告警（§A.2）；（b）对检索是纯噪声；（c）**现存 `.gitignore` 已经写了
`cmake-build-release/`，但我们不读 `.gitignore`**（实测六个靶场的 `.gitignore` 全部存在，
且 5 个都明确忽略 `cmake-build-*`）。这就是 TASK-037 §A 的直接输入。

### C.4 二进制被读取与解码的代价 + CPU 利用率

- 二进制**没有**被 chunk（`_decode` 返回 `None` → 进 `skipped_files`），这部分是对的；
- 但代价是**整份读入内存**（§C.1）；
- 索引期间 CPU 利用率只有 **~200% / 600%**（6 核），因为 `EmbeddingConfig` 不设
  `intra_op_num_threads`，onnxruntime 在 WSL 上只用了 ~2 核。**这是最大的单点加速机会**
  （归 TASK-062，本卡只测量）。

### C.5 需要产品判断的三条（**不自行拍板**）

1. **纯文档仓库的 `answerable`**：Obsidian 上命中正确文档仍判 `False`（§A.5）。这是 R22
   的既定口径，但它意味着"文档仓库"这一类使用场景永远得到 `answerable=false`。
2. **无解析器语言的降级形态**：`.rs` 文件 100% 走兜底（§A.2-1），符号级检索缺失。
   V1 是否接受？（`fallback` 块的 evidence tier 天然低，属诚实标注）
3. **首个查询丢向量通道**（§A.6）：是"性能回填"还是"M2a 收口"的一部分？

## §D 索引一致性自检（已实现）

R41 附注要求把"`chunks > 0` 但 `vectors == 0`"这一**静默清空**形态变得可见。

**实现**（`core/zace_core/engine.py`，只复用既有字段，CF-03/CF-04 未动）：

- 新增模块级 `_vector_index_gap(store, vectors) -> str | None`：向量表为空且
  `chunks > 0` 时返回 `"向量索引为空（可能未重建）：chunks=N，vectors=0"`；
- `search_with_trace` 把该信号并入 `degraded` / `degraded_reason`，
  与通道既有降级原因**拼接而非覆盖**（`"{既有}；{gap}"`）；
- **反向不成立**：`chunks == 0`（真空库）**不**报降级——那是"还没索引"，由 `answerable`
  表达，报成"通道坏了"会给首次索引前的查询误导性诊断。

**回归测试**（`core/tests/integration/test_vector_index_health.py`，4 条）：

| 测试 | 断言 |
|---|---|
| `test_healthy_index_is_not_reported_as_degraded` | 健康索引 `degraded=False`、`answerable=True`（防止下面的断言变成永真） |
| `test_chunks_without_vectors_is_reported_as_degraded` | 制造静默清空 → `degraded=True`、reason 含两边计数、`answerable=False` |
| `test_empty_index_is_not_reported_as_degraded` | 真空库 `degraded=False` |
| `test_gap_reason_is_appended_to_existing_degraded_reason` | 与通道降级共存时**两条原因都能读到**且既有原因在前 |

**负控（必须做，否则可能是永真断言）**：把 `_vector_index_gap` 临时改成恒返回 `None` 后重跑，
2 条断言**如期失败**：

```text
FAILED tests/integration/test_vector_index_health.py::test_chunks_without_vectors_is_reported_as_degraded
FAILED tests/integration/test_vector_index_health.py::test_gap_reason_is_appended_to_existing_degraded_reason
```

## 基线三条

```text
uv run ruff check .                                  → All checks passed!
uv run python scripts/check_dependency_direction.py  → 依赖方向检查通过（core 纯库 / service 不上探）。
uv run pytest                                        → 622 passed, 2 skipped, 2 warnings in 410.85s
```

（main 基线为 612 passed / 2 skipped；本卡新增 10 条回归测试。）

## 契约影响

- **无契约变更**。本卡未改 `docs/contracts/**`、`core/zace_core/{types,interfaces,hashing}.py`。
- §D 只使用既有 `degraded` / `degraded_reason` 字段（R41 附注明文要求）；
- chunk id 的 `#N` 后缀是 **D-04 内部表示**的细化（"代内唯一"不变量不变），
  CF-01 的 `chunks.id TEXT PRIMARY KEY` 未变。

## 与设计偏差

| 偏差 | 说明 |
|---|---|
| Module/01 §2.2 的"chunk_id 后缀消歧"此前只覆盖重载，未覆盖"单行硬切" | 本卡把后缀消歧按同一机制推广到兜底硬切块，符合设计取向（§B.1） |
| TASK-018 §B 的"重复 id → 整文件失败"被本卡收窄为"仅非兜底来源失败" | 实测代价是 10 MB 内容静默丢失；`#N` 消歧不违反"不静默丢数据"（数据全保留） |

## 未决问题

1. **`source.py` 的读写路径口径不一致**（§B.2 根因前半）：`list_files()` 返回含反斜杠的
   路径而 `read()` 拒绝之。本卡按边界未改该文件。**归属 TASK-037 裁定**：
   是过滤掉（静默跳过）还是让 `read()` 接受（当普通文件处理）？
2. **向量通道首次调用超时**（§A.6）：5.0s 预算被 ~5.06s 的模型懒加载吃掉。
   建议 warm-up，但**归属卡需编排者裁定**（性能回填 / M2a 收口）。
3. **纯文档仓库 `answerable` 恒 False**（§C.5-1）：产品判断，未自行放宽。
4. **单文件整读判二进制**（§C.1）：308 MB 文件的代价；与 TASK-037 的阈值方案是同一次改动，
   建议一并处理。
5. **CLI 一次运行内的 CPU 只用了 1/3**（§C.4）：性能工程，归 TASK-062；本卡未优化
   （"不做性能优化工程"是本卡明文边界）。
