# 靶场登记：benchmark/{leveldb,HelloAgents,langchain}

> 状态：**当前基线靶场**（2026-09-15 起）｜ 登记人：实施 AI（TASK-102）
> 本文是 `benches/README.md`「当前靶场」一节的延伸：旧靶场（2026-09-14 清理）见该文「靶场变更」。

## 为什么是这三个

用户 2026-09-15 指示："以后就基于这三个仓库进行测试，本机是公司电脑环境不会再变化。"

选型覆盖**规模梯度 + 语言差异 + 真实大仓库**三个维度：

| 档 | 仓库 | 主语言 | 规模 | 选取理由 |
|---|---|---|---|---|
| 小 | `leveldb` | C/C++ | 152 文件 / 1.9K chunks | 经典 C++ 仓库；**平均 chunk 最短**（137 tok/chunk），与 Python 仓库形成对照 |
| 中 | `HelloAgents` | Python + Markdown | 236 文件 / 2.7K chunks | 教程仓：文档与代码一一对应，覆盖 spec 检索与中英对照（与 `benches/golden/hello-agents` 同源） |
| 大 | `langchain` | Python | 2,950 文件 / 20.7K chunks | **真实 monorepo 规模**；同时含大量二进制/超限文件（173 个被跳过），是索引范围策略的活标本 |

## 路径与 commit（设备绑定）

三个靶场位于**仓库外部** `/home/xuwenzheng/2_github/AI/ACE/benchmark/`，**只读**：
不在其中建文件、不修改、不把源码纳入 zace 仓库。

| 仓库 | commit（2026-09-15 记录） | 远端 | 目录体积 | 其中 `.git` |
|---|---|---|---|---|
| `HelloAgents` | `93e77ea` | `github.com/jjyaoao/HelloAgents` | 5.6 MB | 2.0 MB |
| `leveldb` | `7ee830d` | `github.com/google/leveldb` | 3.5 MB | 2.2 MB |
| `langchain` | `41d3572` | `github.com/langchain-ai/langchain` | 644 MB | **593 MB** |

> ⚠️ langchain 的 644 MB 里 **593 MB 是 `.git`**，可索引范围只有 4.73M token。
> 引用"仓库大小"时必须区分：**chunk 数才是耗时指标，不是目录体积。**

## 画像（本地统计，免 API）

| 档 | 仓库 | 文件 listed/parsed | chunks | tokens | tok/chunk | token p50/p90/p99/max |
|---|---|---|---|---|---|---|
| 小 | `leveldb` | 152 / 152 | 1,898 | 0.26M | 137 | 39/271/2527/4967 |
| 中 | `HelloAgents` | 240 / 236 | 2,729 | 0.89M | 328 | 168/655/2920/3498 |
| 大 | `langchain` | 3,123 / 2,950 | 20,673 | 4.73M | 229 | 129/474/1881/7005 |

复现：`uv run python benches/embed-bench/profile_repo.py --repo <路径> --out out.json`

> 画像脚本已对齐 indexer 口径：**C++ 仓库的 `.h` 按 `cpp` 解析**（R1 仓库级语言抬升）。
> 未对齐时 leveldb 少算 513 chunks（1898 vs 1385）——这是最初的口径误差，已修正。

## 耗时基准

见 `benches/results/index-cost-model-company-wsl.md`（设备绑定 `company-wsl`）。

## 未做的事

- **未出 golden 用例**：本轮只测索引耗时，不测检索质量。若要在这三个靶场上做质量回归，
  需按 `benches/README.md` 的 JSONL 格式出题（`expected[].path` 用仓库相对路径）。
- **未进 `targets.json`**：该文件绑定"用例集 + 预建索引"，本靶场暂无用例，故不登记。
