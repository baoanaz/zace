# zace golden eval 报告

- golden：/home/xuwenzheng/2_github/AI/ACE/zace-lane-f/benches/golden/cockpit-agents-py（38 条用例）
- repo：(未绑定仓库：--project-id 模式)
- project：8e69da62f37e5783
- 生成时间：2026-09-16 00:24:43
- 预算：maxTokens=10000｜排名口径=ContextPack 装填序｜top-k=10
- 向量通道降级用例数：0

## 总体（正例）

| 指标 | 值 |
|---|---|
| 正例数 | 36 |
| recall@5 | 0.861 |
| recall@10 | 0.861 |
| MRR | 0.562 |
| 负例通过 | 2/2 |

## 按语言（lang）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| zh | 36 | 0.861 | 0.861 | 0.562 |

## 按类别（category）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| behavior | 18 | 0.833 | 0.833 | 0.537 |
| path | 3 | 0.667 | 0.667 | 0.417 |
| spec | 6 | 1.000 | 1.000 | 0.708 |
| symbol | 9 | 0.889 | 0.889 | 0.563 |

## 失败清单（正例）

| id | lang | category | query | 期望 | top-3 |
|---|---|---|---|---|---|
| cockpit-0008 | zh | path | 宿主入口 main() 在哪里？它按什么顺序启动 SDK、MCP 和 HMI Gateway，停止时顺序如何？ | src/cvi_agent_product/app/host.py#main | src/cvi_agent_product/app/host.py:148-252 (build_host) / docs/internal-design.md:89-119 (仓库内部设计与源码分层 > 四、组合根和启动顺序) / src/cvi_agent_product/app/host.py:85-107 (AiboxHost) |
| cockpit-0018 | zh | behavior | 当前这个仓库里一共注册了多少个业务 Tool（capability）？它们分别在哪些文件里定义？ | src/cvi_agent_product/tools/hmi/definitions.py / src/cvi_agent_product/tools/sdk/definitions.py | src/cvi_agent_core/tools/catalog.py:27-29 (ToolCatalog) / src/cvi_agent_core/tools/__init__.py:1-5 ((module)) / benchmarks/llm/datasets/README.md:46-59 (LLM 基准数据集 > 紧凑 ToolCard 和最终 ContextWindow) |
| cockpit-0019 | zh | behavior | 哪些 Tool 被声明为必须用户确认（confirmation=REQUIRED）才能执行？ | src/cvi_agent_product/tools/sdk/definitions.py / src/cvi_agent_product/tools/mcp/definitions.py | benchmarks/llm/datasets/README.md:60-63 (LLM 基准数据集 > 添加多 ToolCall 测试) / benchmarks/llm/datasets/README.md:83-96 (LLM 基准数据集 > Expected 类型) / src/cvi_agent_product/prompts/welcome/music.system.md:1-1 ((preamble)) |
| cockpit-0022 | zh | behavior | 一次模型调用最多可以暴露几个 Tool 描述符？超预算时上下文里的哪些内容会被丢弃？ | src/cvi_agent_core/context/builder.py | benchmarks/llm/datasets/README.md:46-63 (LLM 基准数据集 > 紧凑 ToolCard 和最终 ContextWindow) / benchmarks/llm/README.md:68-77 (LLM Agent 基准测试 > 4. 当前覆盖 > 4.0 ContextWindow ToolCard v2) / src/cvi_agent_core/agent/definition.py:22-22 ((module)) |
| cockpit-0035 | zh | symbol | 能力网关 CapabilityGateway 如何实现幂等（idempotency）、参数验证（verification）、重试（retry）与 UNKNOWN 终态？ | src/cvi_agent_core/capability/gateway.py#CapabilityGateway._reserve_idempotency / src/cvi_agent_core/capability/gateway.py#CapabilityGateway._should_retry / src/cvi_agent_core/capability/gateway.py#CapabilityGateway._normalize | src/cvi_agent_core/capability/provider.py:16-16 (Provider.verify) / src/cvi_agent_product/products/welcome/new_friend/capabilities.py:195-204 (NewFriendCapabilityProvider.verify) / src/cvi_agent_product/tools/sdk/provider.py:32-32 (MemoryToolBackend.verify) |

## 负例清单

| id | 通过 | query | answerable | missingEvidence |
|---|---|---|---|---|
| cockpit-0031 | 是 | 支付网关的指数退避重试策略是在哪个文件里实现的？ | False | unresolved_reference, retrieval_truncated |
| cockpit-0032 | 是 | Kafka 消费者组的 rebalance 回调是在哪个模块实现的？ | False | unresolved_reference, retrieval_truncated |
