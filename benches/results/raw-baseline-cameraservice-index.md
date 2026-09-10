# zace golden eval 报告

- golden：benches/golden/linux-mtk-mw-cameraservice（索引层口径：候选池序）（16 条用例）
- repo：/home/xuwenzheng/0_project/main/linux-mtk-mw-cameraservice
- project：02f437a22ebbe713
- 生成时间：2026-09-10 19:46:17
- 预算：maxTokens=10000｜排名口径=ContextPack 装填序｜top-k=10
- 向量通道降级用例数：0

## 总体（正例）

| 指标 | 值 |
|---|---|
| 正例数 | 14 |
| recall@5 | 0.500 |
| recall@10 | 0.571 |
| MRR | 0.344 |
| 负例通过 | 1/2 |

## 按语言（lang）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| en | 4 | 0.250 | 0.250 | 0.125 |
| mixed | 6 | 0.667 | 0.833 | 0.469 |
| zh | 4 | 0.500 | 0.500 | 0.375 |

## 按类别（category）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| behavior | 4 | 0.750 | 0.750 | 0.300 |
| path | 3 | 0.333 | 0.333 | 0.167 |
| spec | 2 | 0.000 | 0.500 | 0.056 |
| symbol | 5 | 0.600 | 0.600 | 0.600 |

## 失败清单（正例）

| id | lang | category | query | 期望 | top-3 |
|---|---|---|---|---|---|
| cameraservice-0001 | zh | symbol | 摄像头通道切换的状态机类在哪个头文件里？ | cameraservice/stateMc/MWPStateMcManager.h#MWPStateMcManager | common/Constants.h:235-235 (CFG_PARK_CAMERA_STS_BIT) [bm25#14,vector#1] / Data/MWPCameraData.h:23-57 (MWPCameraDataMgr::CameraParamsData) [bm25#12,vector#47] / CLAUDE.md:94-118 (linux-mtk-mw-cameraservice 仓库架构概述 > 关键类) [bm25#1] |
| cameraservice-0003 | zh | path | 倒车影像（RVC）策略的实现文件是哪一个？ | cameraservice/policy/MWPRvcPolicy.cpp | Data/MWPCameraData.cpp:33-51 (CameraShmDataBase::InitCameraShmData) [bm25#24,vector#4] / common/Constants.h:237-237 (CFG_PARK_SIGNAL_STS_BIT) [bm25#38,vector#7] / park/render/MWPRearPage.cpp:116-122 ((module)) [bm25#1,vector#5] |
| cameraservice-0006 | en | symbol | Which class parses CAN bus frames and dispatches speed/gear changes to listeners? | cameraservice/policy/can/MWPCanInfo.h#MWPCanInfo | .claude/skills/cviauto-meta/references/platform-files/agents.md:73-79 (Agents > Modification Principles) [bm25#1] / README.md:78-84 (Editing this README > Contributing) [bm25#7] / README.md:47-92 (Editing this README) [bm25#12] |
| cameraservice-0007 | en | behavior | How does the AVM policy react when vehicle speed changes? | cameraservice/policy/MWPAvmPolicy.cpp#OnCarSpeedChanged | .claude/skills/cviauto-meta/references/platform-files/agents.md:11-20 (Agents > Agent Responsibilities) [bm25#28] / README.md:78-84 (Editing this README > Contributing) [bm25#35] / common/Message.h:22-43 (eMPU2MCU) [bm25#2] |
| cameraservice-0008 | en | spec | What processes make up this repository's two-process architecture and how do they communicate? | CLAUDE.md | .claude/skills/cviauto-spec-bootstrap/references/repository-analysis.md:13-24 (Repository Analysis > What To Capture) [bm25#1,vector#9] / .claude/skills/cviauto-update-spec/SKILL.md:105-116 (Update Code-Spec - Capture Executable Contracts > Update Process > Step 2: Classify the Update Type) [bm25#13,vector#15] / .claude/skills/cviauto-session-insight/references/triggering-patterns.md:72-84 (Triggering Patterns > Finish-work retrospective (on demand)) [bm25#12,vector#19] |
| cameraservice-0015 | mixed | path | 泊车页 logo 的绘制实现在哪个文件？ | park/render/MWPLogo.cpp | CLAUDE.md:78-93 (linux-mtk-mw-cameraservice 仓库架构概述 > 核心功能模块) [bm25#11,vector#23] / park/presenter/LogoPresenter.cpp:190-214 (LogoPresenter::OnTimerHandleFunc) [bm25#12,vector#5] / libcamera/MWPLogoFile.h:13-13 (LOGO_FINISH_PATH) [bm25#22,vector#12] |

## 负例清单

| id | 通过 | query | answerable | missingEvidence |
|---|---|---|---|---|
| cameraservice-0005 | 否 | Terraform 的资源依赖图是在哪个文件里构建的？ | True | unresolved_reference, retrieval_truncated |
| cameraservice-0010 | 是 | Where is the gRPC service definition for the parking assist module? | False | unresolved_reference, retrieval_truncated |
