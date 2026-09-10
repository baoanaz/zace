# zace 仓库协作规则（实施 AI 必读）

本文件约束所有在本仓库工作的 AI 会话（含子 AI）。与 `docs/design/INDEX.md` §3 决策登记表冲突时，以决策登记表为准；本文件只讲"怎么干活"，不复述"设计成什么样"。

## 1. 开工前必读

1. `docs/design/INDEX.md`（文档地图 + 决策登记表 + 术语表）；
2. 你认领的任务卡 `docs/tasks/TASK-xxx.md`（含依赖、冻结接口、验收命令、参考锚点）；
3. 任务卡"输入文档"节列出的具体 Module 章节（只读所需章节，不全量读）。

参考项目源码在仓库外部工作区 `../source/`（ACE 工作区，只读）：
- 若本机存在 `../source/`，按任务卡"参考锚点"查阅；**禁止修改**；
- 若无（例如只 clone 了 zace 仓库），按任务卡内摘录与 `docs/design/Background/` 的源码路径锚点理解。

## 2. 硬性边界

- **不改设计文档**（`docs/design/**`）：发现设计问题在 PR 中标注并提出，由编排者裁决；只有"修订记录/状态"行随决策更新。
- **不改冻结契约**（`docs/contracts/**`、`core/zace_core/types.py`、`core/zace_core/interfaces.py`）：契约变更必须走 `docs/plan/orchestration.md` §4 流程。
- **不越界改文件**：每张任务卡有"交付物（文件所有权）"清单；清单外的文件不要改（公共文件改动先在任务卡的"执行记录"里提出）。
- **不修改 `source/` 下任何参考项目代码**。
- 不引入与任务无关的新依赖；依赖加入 `core/pyproject.toml` / `service/pyproject.toml` 时注释说明对应任务与决策编号。

## 3. Git 纪律

- 每张任务卡一个分支：`feature/task-<编号>_<缩写><MMDD>`（如 `feature/task-001_xwz0910`）；泳道模式下第一张卡从 `main` 开分支，后续卡从上一张卡的分支串联创建。
- 不直推 `main`、不使用 `git push --force`；泳道模式下只需**本地提交**（无需 push/PR），评审与合并由总览 AI 执行。
- 一次提交只做任务卡范围内的事；提交信息用英文祈使句 + 任务号，例：`task-001: add sqlite schema and FTS5 writer`。
- 不提交运行时产物（数据库、`.zace/`、构建输出）；不提交任何 secret/token。

## 4. 验证纪律

- 任务卡"验收标准"里的命令必须本地跑通，并把关键输出贴进 PR/完成报告；测试失败不得声明完成。
- 新增逻辑必须有单元测试；测试数据用临时目录/内存库，禁止依赖本机绝对路径。
- 全仓库基线检查必须保持绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest`。

## 5. 完成后必须回填

1. 任务卡底部"执行记录"：日期 + 分支 + 验收命令与结果 + 与设计的偏差 + 未决问题；
2. `docs/tasks/README.md` 任务板对应行状态改为 `review`；
3. PR 描述按 `docs/plan/orchestration.md` §3 的报告模板写。

## 6. 与设计文档冲突时

- 实现与 Module 设计冲突：**先停下来**在任务卡"执行记录/未决问题"里写清冲突点与建议，交编排者裁决；不得静默偏离设计。
- 代码与设计最终不一致且已上线：由编排者更新设计文档并在 `docs/design/INDEX.md` §4 记录漂移。
