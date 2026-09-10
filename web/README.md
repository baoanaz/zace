# zace-web（Phase 4）

静态 SPA（Module/07）：V1 = 管理面 + Playground，复用服务端 Markdown 渲染，不自研渲染层（D-40）。

页面：Login / Project List / Project Detail / Search Playground / ask_project Playground / Tokens / Usage / Settings。
消费 `zace-service` REST API（`docs/contracts/openapi.yaml`），无 SSR、无 BFF、无秘密存储。

Phase 0/1 期间本目录只放任务规划，不写代码。
