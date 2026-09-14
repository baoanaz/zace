# zace golden eval 报告

- golden：benches/golden/cockpit-agents-py/cockpit.jsonl（32 条用例）
- repo：(未绑定仓库：--project-id 模式)
- project：8e69da62f37e5783
- 生成时间：2026-09-14 23:25:50
- 预算：maxTokens=10000｜排名口径=ContextPack 装填序｜top-k=10
- 向量通道降级用例数：0

## 总体（正例）

| 指标 | 值 |
|---|---|
| 正例数 | 30 |
| recall@5 | 0.767 |
| recall@10 | 0.867 |
| MRR | 0.505 |
| 负例通过 | 2/2 |

## 按语言（lang）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| zh | 30 | 0.767 | 0.867 | 0.505 |

## 按类别（category）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| behavior | 13 | 0.692 | 0.769 | 0.349 |
| path | 3 | 0.667 | 1.000 | 0.458 |
| spec | 6 | 1.000 | 1.000 | 0.833 |
| symbol | 8 | 0.750 | 0.875 | 0.531 |

## 失败清单（正例）

| id | lang | category | query | 期望 | top-3 |
|---|---|---|---|---|---|
| cockpit-0012 | zh | symbol | gRPC 双向流 MainStream 的服务端实现（含认证和有序出站队列）在哪个类里？ | src/cvi_agent_product/integrations/hmi/server.py#FrameworkGatewayServer | src/cvi_agent_product/integrations/hmi/server.py:260-294 (FrameworkGatewayService.MainStream) / src/cvi_agent_product/integrations/generated/gateway/cvi_agent_gateway_v1_pb2_grpc.py:47-51 (FrameworkGatewayServicer.MainStream) / src/cvi_agent_product/integrations/generated/gateway/cvi_agent_gateway_v1_pb2_grpc.py:72-97 (FrameworkGateway.MainStream) |
| cockpit-0018 | zh | behavior | 当前这个仓库里一共注册了多少个业务 Tool（capability）？它们分别在哪些文件里定义？ | src/cvi_agent_product/tools/hmi/definitions.py / src/cvi_agent_product/tools/sdk/definitions.py | benchmarks/llm/datasets/README.md:46-59 (LLM 基准数据集 > 紧凑 ToolCard 和最终 ContextWindow) / src/cvi_agent_product/products/welcome/new_friend/capabilities.py:46-141 (capability_definitions) / docs/internal-design.md:72-88 (仓库内部设计与源码分层 > 三、源码目录地图 > `cvi_agent_product`：AIBOX 产品和集成层) |
| cockpit-0019 | zh | behavior | 哪些 Tool 被声明为必须用户确认（confirmation=REQUIRED）才能执行？ | src/cvi_agent_product/tools/sdk/definitions.py / src/cvi_agent_product/tools/mcp/definitions.py | benchmarks/llm/datasets/README.md:11-45 (LLM 基准数据集 > 添加单轮 Tool 测试) / src/cvi_agent_product/prompts/welcome/music.system.md:1-1 ((preamble)) / tests/v2/capability_gateway/test_gateway_pipeline.py:87-103 (test_demo_execution_ignores_grounding_permission_confirmation_and_safety) |
| cockpit-0022 | zh | behavior | 一次模型调用最多可以暴露几个 Tool 描述符？超预算时上下文里的哪些内容会被丢弃？ | src/cvi_agent_core/context/builder.py | benchmarks/llm/README.md:68-77 (LLM Agent 基准测试 > 4. 当前覆盖 > 4.0 ContextWindow ToolCard v2) / benchmarks/llm/datasets/README.md:46-63 (LLM 基准数据集 > 紧凑 ToolCard 和最终 ContextWindow) / src/cvi_agent_core/context/tools.py:93-156 (compact_tool_card) |

## 负例清单

| id | 通过 | query | answerable | missingEvidence |
|---|---|---|---|---|
| cockpit-0031 | 是 | 支付网关的指数退避重试策略是在哪个文件里实现的？ | False | unresolved_reference, retrieval_truncated |
| cockpit-0032 | 是 | Kafka 消费者组的 rebalance 回调是在哪个模块实现的？ | False | unresolved_reference, retrieval_truncated |
