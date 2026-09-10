# TASK-030：service 骨架（FastAPI 应用 / 配置 / 日志 / 错误信封 / healthz）

> 状态：review ｜ 阶段：Phase 2（M2a-1）｜ 硬依赖：无 ｜ soft 依赖：无
> 建议分支：`feature/task-030_<你的缩写><MMDD>`
> 交付物所有权：
> - `service/zace_service/{__init__,__main__,app,config,logging,errors}.py`（新建）
> - `service/zace_service/routers/{__init__,auth,projects,sync,query,ops}.py`（新建；本卡只做占位）
> - `service/tests/`（新建，含 `__init__.py` 与 `conftest.py`）
> - `service/pyproject.toml`（**仅**新增 `[project.scripts]` 与必要注释）
>
> 清单外文件不得改（尤其 `docs/contracts/**`、`core/**`、`service/zace_service/` 下未列出的文件）。

## 目标

把 `zace-service` 从空包变成**可启动、可探活、可被测试驱动**的 FastAPI 应用：业务路由先全部占位（501），
契约面（路径集合）在本卡一次性冻结为与 CF-05 一致，后续 TASK-031..033 只填实现不改路径。

本卡是 M2a 的地基：后面三张卡都要在这个应用上挂真实逻辑。

## 输入文档（按序读，只读所需章节）

1. `docs/design/Module/06-服务化与部署.md` §0.1（拆分与依赖方向）、§2.1（REST 路径清单）、§2.4（可观测）、§3（安全清单里与本卡相关的部分）
2. `docs/contracts/openapi.yaml`（CF-05：**路径集合与 Error 形态是冻结合同**）
3. `docs/plan/contracts.md` §3.8（R33-R37：本地模式免鉴权、`projectId` 可省略等裁定）
4. `docs/plan/phase2-roadmap.md` §1（M2a 卡序）
5. `service/pyproject.toml`（现有依赖：fastapi / uvicorn / pydantic / argon2-cffi / itsdangerous；dev: pytest / ruff / httpx）

## 冻结接口（本卡不得变更）

- **消费**：CF-05 的路径与 Error 信封 `{"error": {"code": ..., "message": ...}}`；TASK-030 不消费 core。
- **产出**（后续卡依赖，写出后不得随意改）：
  - `zace_service.app.create_app(settings: Settings | None = None) -> FastAPI`（测试与 `__main__` 的唯一入口）
  - `zace_service.config.Settings`（字段与默认值见下）+ `Settings.from_env()`
  - `zace_service.errors.ApiError(code: str, message: str, status: int = 400)`
  - `zace_service.deps.get_settings(request) -> Settings`（从 `app.state` 取，便于测试覆盖）
- **纪律**：不实现鉴权（M2c TASK-060）；`/api/auth/*` 路径必须存在但返回 501。

## 交付物（文件所有权）

| 路径 | 内容 |
|---|---|
| `service/zace_service/config.py` | `Settings`：`data_root`（默认 `~/.zace`，env `ZACE_DATA_ROOT`）、`host`（默认 `127.0.0.1`）、`port`（默认 `8787`）、`log_level`（默认 `info`）、`local_mode`（默认 `True`，env `ZACE_LOCAL_MODE`）、`version`（读包版本）；`from_env()` 用 `os.environ`，**不引入 pydantic-settings** |
| `service/zace_service/logging.py` | 结构化 JSON 日志（stderr）：`ts/level/logger/msg/requestId/...`；**脱敏**：Authorization / Cookie / token / 请求体不得进日志 |
| `service/zace_service/errors.py` | `ApiError` + 异常处理器：`ApiError→{error:{code,message}}` 与对应状态码；未捕获异常 → 500 `internal_error`（响应不含堆栈，日志含全量） |
| `service/zace_service/app.py` | `create_app()`：挂路由、JSON 日志、requestId 中间件（响应头 `X-Request-Id`）、异常处理器；`GET /healthz` 由 `routers/ops.py` 提供 |
| `service/zace_service/routers/ops.py` | `GET /healthz`：`{status,version,dataRoot,localMode,auth:"disabled(local)",core:{importable:true}}`（**不加载 embedding 模型**；`?deep=1` 时才探测 provider 并在响应里给 ok/failed+reason） |
| `service/zace_service/routers/{auth,projects,sync,query}.py` | 占位路由：路径齐全、统一 501 `not_implemented`；TASK-031/032/033 各自替换对应文件内的实现 |
| `service/zace_service/__main__.py` | `main()`：`--host/--port/--data-root/--log-level/--reload` → `uvicorn.run(create_app(...))`；console script `zace-service` |
| `service/tests/{__init__.py,conftest.py,test_skeleton.py}` | 见 DoD |
| `service/pyproject.toml` | 仅新增 `[project.scripts] zace-service = "zace_service.__main__:main"` |

> `routers/__init__.py` 已含在 `service/zace_service/routers/` 清单里（新建）。

## 验收标准（DoD）

- [ ] **CF-05 路径一致性测试**（本卡最重要的断言）：`set(app.openapi()["paths"])` 必须与 `docs/contracts/openapi.yaml` 里的路径集合**完全相等**（用 `yaml` 不可用则手写常量清单；差异必须报出多/少两侧）。
- [ ] `/healthz`：200 + 字段齐全；`?deep=1` 在 provider 不可用时返回 200 但 `core.ok=false` 且带 reason（不得 500）。
- [ ] 错误信封：调用任一占位路由（如 `POST /api/query/search`）→ 501 且 body 为 `{"error":{"code":"not_implemented",...}}`；未知路径 404 同样走信封；构造一个抛 `ApiError` 的路由验证 400/409 形态。
- [ ] requestId：响应带 `X-Request-Id`，且日志行里同一 id 可检索。
- [ ] 日志脱敏：发一个带 `Authorization: Bearer secret-token` 的请求，断言 `caplog` 输出里**不出现** `secret-token`。
- [ ] 行为验收（贴进执行记录）：`uv run zace-service --port 8787` 起服务；`curl -s localhost:8787/healthz`；`curl -si -X POST localhost:8787/api/query/search -H 'content-type: application/json' -d '{}'` 返回 501 + 信封。
- [ ] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest`
- [ ] 任务卡"执行记录"已回填；任务板 `docs/tasks/README.md` 对应行状态改 `review`。

## 参考源码锚点（只读）

- `docs/contracts/openapi.yaml`：路径清单（注意 `/api/auth/tokens/{id}` 这类带参数路径在 FastAPI 里是 `/api/auth/tokens/{id}` 形态，路径字符串必须逐字对齐）。
- `core/zace_core/cli/app.py`：本仓库既有的 argparse + main() 风格参考（保持风格一致）。

## 明确不做

- 不实现鉴权 / token / session / 用户体系（M2c TASK-060/061）——`/api/auth/*` 只占位 501。
- 不实现业务逻辑（查询、同步、项目解析都在 TASK-031..033）。
- 不实现索引 job 队列 / 进度上报（TASK-062）。
- 不写 HTML / 静态资源（那是 zace-web）。
- **不新增第三方依赖**（现有依赖已够；需要新依赖先在"未决问题"里申请）。
- 不做速率限制、CORS 放开等安全策略（V1 明确不做，Module/06 §8）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

- **日期 / 分支**：2026-09-10 ｜ `feature/task-030_xwz0910`（从 `main` @ `97a92f5` 创建）
- **关键产物**：`service/zace_service/{config,logging,errors,deps,app,__main__}.py`、
  `service/zace_service/routers/{__init__,auth,projects,sync,query,ops}.py`、
  `service/tests/{__init__,conftest,test_skeleton}.py`、`service/pyproject.toml`（仅新增 `[project.scripts]`）。

### 验收命令与结果

```text
$ uv run ruff check .
All checks passed!
$ uv run python scripts/check_dependency_direction.py
依赖方向检查通过（core 纯库 / service 不上探）。
$ uv run pytest
521 passed, 2 skipped, 2 warnings in 12.93s      # 基线 501+2 → 本卡新增 20 条
$ uv run pytest service/tests -q
20 passed
```

行为验收（真实进程 + curl；`--data-root /tmp/zace-t030` 避免污染 `~/.zace`）：

```text
$ uv run zace-service --port 8787 --data-root /tmp/zace-t030
$ curl -s localhost:8787/healthz
{"status":"ok","version":"0.0.1","dataRoot":"/tmp/zace-t030","localMode":true,
 "auth":"disabled(local)","core":{"importable":true}}

$ curl -si -X POST localhost:8787/api/query/search -H 'content-type: application/json' -d '{}'
HTTP/1.1 501 Not Implemented
X-Request-Id: 5c36254fa7744404
{"error":{"code":"not_implemented","message":"POST /api/query/search（Fast 检索）尚未实现
（由 TASK-032 交付）：本版本为 M2a 骨架，该端点为占位。"}}
```

stderr 结构化日志（同一 requestId 可在日志中检索；headers/body 从不落盘）：

```json
{"ts": "2026-09-10T12:52:06.181+00:00", "level": "info", "logger": "zace_service.app",
 "msg": "request", "requestId": "b275ec61e7c74ffa", "durationMs": 3.97,
 "method": "GET", "path": "/healthz", "status": 200}
{"ts": "2026-09-10T12:52:06.200+00:00", "level": "info", "logger": "zace_service.app",
 "msg": "request", "requestId": "5c36254fa7744404", "durationMs": 3.56,
 "method": "POST", "path": "/api/query/search", "status": 501}
```

### CF-05 路径一致性（本卡地基）

- `test_openapi_paths_match_cf05_contract`：`set(app.openapi()["paths"])` 必须与 `docs/contracts/openapi.yaml` 的路径集合（16 条）完全相等，失败时分别打印多/少两侧；
- `test_openapi_methods_match_cf05_contract`：逐路径比对方法集合（GET/POST/DELETE）；
- 合同解析**不用 PyYAML**（service 未声明该依赖）：按缩进提取 `paths:` 段下 2 空格的路径键与 4 空格的方法键，仍是直接读合同文件本身（能抓到双向漂移）。

### 契约影响

无。未改 `docs/contracts/**`；只消费 CF-05（路径 + Error 信封）与 R34（本地模式免鉴权）。

### 与设计偏差

1. **`deps.py` 在本卡新建**：卡内「冻结接口」就要求产出 `zace_service.deps.get_settings`，但交付物表未列该文件（TASK-031 的清单里写的是“新增 engine_manager 依赖”）。同一泳道串联，故本卡建文件+`get_settings`，TASK-031 就地追加 `get_engine_manager`；未改任何既有语义。
2. **healthz 的 `?deep=1` 探测**：本地模式下调用 `provider.ensure_loaded()`（会触碰模型文件）。自动化测试只覆盖“provider 不可用”路径（`EMBED_MODE=api` 且无 model/base_url → 离线即失败），真实模型加载不在 CI 内（离线纪律）。
3. **500 兜底放在 middleware 而非仅异常处理器**：Starlette 的 `ServerErrorMiddleware` 回完响应后仍会 re-raise，只靠 `add_exception_handler(Exception, ...)` 会“已回包又抛异常”。两个都装了，middleware 先接住（异常不逃出应用，响应始终是 CF-05 信封），处理器作兜底。
4. **uvicorn 自身的启动/关闭日志未接管**（仍是 uvicorn 纯文本）；访问日志已由 middleware 以 JSON 输出且 `access_log=False`。应用自身日志 100% JSON。
5. `--reload` 模式下配置经环境变量递给子进程，`--log-level` 只影响 uvicorn 自身日志（服务 JSON 日志沿用默认 `info`）——开发便利开关，不影响生产路径。

### 未决问题

1. 本地模式下的 `?deep=1` 真实探测（模型加载）无自动化测试（离线约束）；需要时人工跑 `curl 'localhost:8787/healthz?deep=1'`。
2. healthz 的 `auth` 字段在 `local_mode=false` 时输出 `"enabled"`，但 M2c 前并无真实鉴权（仅字段占位）——待 TASK-060 复核文案。
3. `/api/auth/*` 与 `/api/usage/projects/{id}` 仍为 501 占位（属 M2c/Phase 3），符合本卡「路径冻结、实现可迟到」口径。

### 建议复核点

① CF-05 一致性测试的合同解析方式（不依赖 PyYAML，但依旧是“读合同文件本身”）；
② 500 兜底位置与「响应无堆栈」断言；③ 日志脱敏双保险（不记 headers/body + 文本级 filter）。
