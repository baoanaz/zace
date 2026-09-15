# TASK-060：鉴权（session + API token + 首个用户初始化）

> 状态：pending ｜ 阶段：Phase 3（M2c）｜ 硬依赖：TASK-030（done）｜ soft 依赖：TASK-061（租户，紧随本卡）
> 建议分支：`feature/task-060_<你的缩写><MMDD>`
> 交付物所有权：
> - `service/zace_service/routers/auth.py`（把 501 占位换成实现）
> - `service/zace_service/auth.py`（**新建**：密码哈希 / session 签发与校验 / token 生成与校验）
> - `service/zace_service/metadb.py`（**新建**：`zace-meta.db` 的 DDL 与访问层，本卡先建 users / sessions / api_tokens 三表）
> - `service/zace_service/{config,deps,app}.py`（追加鉴权开关与依赖注入）
> - `service/tests/test_auth.py`（**新建**）
>
> 清单外文件不得改。**`docs/contracts/openapi.yaml` 不得直接改**——本卡需要补的契约见"契约影响"节，走 L2 流程。

## 目标

让 `ZACE_LOCAL_MODE=false`（云端形态）真正要求凭据。当前状态是**阻断级安全缺口**：
TASK-051 实测（`docs/evidence/task-051-cloud-mcp-readiness.md` §1 A1）非本地模式下**不带凭据、甚至带无效
Bearer token 都能成功检索**，而 `/healthz` 却自报 `auth: enabled`。

本卡交付：

```text
web  登录/登出/初始化账户  ── session cookie（httpOnly, zace_session）
client / CLI / MCP        ── Bearer token（zace_ 前缀，明文仅创建时返回一次）
```

**被谁消费**：TASK-061（租户映射）、TASK-064（审计按用户归属）、TASK-070 起的所有 web 鉴权页、
TASK-040R（Rust client 的 token 注入）。

## 输入文档（按序读，只读所需章节）

1. `docs/design/Module/06-服务化与部署.md` §2.2（鉴权：token/session/密码算法/401 不区分细节）、§2.4
2. `docs/evidence/task-051-cloud-mcp-readiness.md` §1（A1 的实测证据与处置建议：本卡是它的修复）
3. `docs/contracts/openapi.yaml`（CF-05 的 `/api/auth/*` 段：路径与响应形状已冻结）
4. `service/zace_service/routers/auth.py`（现有 501 占位与"不声明请求体"的纪律）
5. `service/zace_service/deps.py`（现有依赖注入形态；本卡在此增加"当前用户"依赖）
6. `docs/contracts/PROCESS.md` §3.8（R34：本地模式免鉴权——**本卡不得破坏它**）

## 冻结接口（本卡不得变更）

- 消费：CF-05 的 `/api/auth/register|login|logout|tokens|tokens/{id}` 六个路径与响应形状。
- 产出（TASK-061 依赖，写出后不得随意改）：
  - `zace_service.auth.current_user(request) -> User | None`（本地模式返回本地用户）
  - `User`（`id` / `name` / `created_at` / `is_local`）
  - `zace_service.auth.require_user(request) -> User`（非本地模式下无凭据 → 401 `unauthorized`）
  - `zace_service.auth.hash_token(raw) -> str`、`verify_api_token(token) -> User | None`
  - `Settings` 新增字段：`auth_required: bool`（默认 = `not local_mode`）、`register_open: bool`（默认 False）

## 契约影响（L2 申请，需编排者先更新 CF-05，再实现）

本卡需要 CF-05 补充以下内容（**申请**，实现前请编排者确认并落盘契约）：

| 端点 | 需要的补充 | 为什么不能省 |
|---|---|---|
| `POST /api/auth/register` | 响应 `201 { userId, name }`；`409 name_taken`；`403 register_disabled`（register 关闭时） | 现契约只有 `201/403` 描述，无字段与冲突码 |
| `POST /api/auth/login` | 请求 `{name, password}`；响应 `200 { userId, name }` + `Set-Cookie: zace_session=…`；`401 unauthorized` | 现契约无请求体模型与响应字段 |
| `POST /api/auth/logout` | 语义：清除 cookie + 服务端 session 失效 | 现契约只有 204 |
| `POST /api/auth/tokens` | 请求可带 `{name}`；响应 `201 { id, token, prefix, name, createdAt }`（`token` 明文**仅此一次**） | web 要显示"复制"与列表 |
| `GET /api/auth/tokens` | 响应 `[{ id, prefix, name, createdAt, lastUsedAt }]`（**绝不含明文或 hash**） | web token 列表页 |
| `DELETE /api/auth/tokens/{id}` | 软删；`404 token_not_found` | — |
| **新增** `GET /api/auth/me` | `200 User` / `401` | web 每次加载要知道"登录了没、我是谁"，否则只能靠试探任意端点 |
| **新增** `POST /api/auth/bootstrap` | 首个用户初始化（见 §D） | **CF-05 目前没有任何"初始化账户"入口**，全新部署无法产生第一个用户 |
| **新增** `GET /api/meta` | `{ authRequired, registerOpen, localMode, version }` | 登录页要据此决定"显示注册/显示初始化/直接进主页"；不含任何秘密 |

前三项属"补全已有路径的语义"，后三项属新增路径，**均登记在本卡内**，由编排者同步到 CF-05。

## §A 数据模型（`zace-meta.db`）

新建 `service/zace_service/metadb.py`，DDL 由本卡登记（**不进 CF-01/CF-04 的 core DDL**——
core 无用户概念，D-34）。位置：`{data_root}/zace-meta.db`（Module/06 §4-A 已声明该文件名）。

```sql
CREATE TABLE IF NOT EXISTS users (
  id            TEXT PRIMARY KEY,          -- uuid4 hex
  name          TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,             -- argon2id 编码串
  created_at    INTEGER NOT NULL,
  is_local      INTEGER NOT NULL DEFAULT 0 -- 1 = 本地模式的隐式用户（TASK-061 用）
);
CREATE TABLE IF NOT EXISTS sessions (
  id         TEXT PRIMARY KEY,             -- 随机 32 字节 hex（cookie 里放的就是它）
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  last_seen_at INTEGER
);
CREATE TABLE IF NOT EXISTS api_tokens (
  id           TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name         TEXT NOT NULL DEFAULT '',
  prefix       TEXT NOT NULL,              -- 明文前 8 位，用于列表辨识
  token_hash   TEXT NOT NULL UNIQUE,       -- sha256(明文)
  created_at   INTEGER NOT NULL,
  last_used_at INTEGER,
  revoked_at   INTEGER                     -- NULL = 有效（软删）
);
```

## §B 密码与会话

- 密码：**argon2id**（`argon2-cffi`）。依赖加入 `service/pyproject.toml`，注释写 `TASK-060 / Module 06 §2.2`。
  **本地 ONNX 与云端 embedding 都不受影响**；core 的依赖清单不得出现它（`check_dependency_direction.py`
  的 `FORBIDDEN_CORE_DEPS` 已包含 `argon2-cffi`，本卡只改 service）。
- session：登录签发 `id = secrets.token_hex(32)`，**cookie 存 id 本身且 `httpOnly`**；
  库中存该 id（`sessions.id`）。有效期 30 天（卡内默认，可调）。
  cookie 属性：`HttpOnly; SameSite=Lax; Path=/;`；`Secure` 由 `ZACE_COOKIE_SECURE`（默认 `false`，
  本地 http 调试用；**上云必须在部署文档里要求设 true**）。
- token：`zace_` + `secrets.token_urlsafe(32)`；库存 `sha256(明文)`；明文只在创建响应里出现一次。
- 时间比较用 `time.time()`（与全仓一致），过期 session 视为无效并**顺手删除**。

## §C 鉴权接入点（关键：别把本地模式搞坏）

`service/zace_service/deps.py` 增加 FastAPI 依赖；**挂载位置必须精确**：

| 范围 | 规则 |
|---|---|
| `settings.local_mode == True`（默认） | **完全放行**，行为与今天逐字一致（R34 不可破坏） |
| `settings.local_mode == False` | `/api/**` 全部要求凭据；例外见下 |
| 豁免 | `/healthz`、`/api/meta`、`/api/auth/login`、`/api/auth/register`、`/api/auth/bootstrap`、`/api/auth/logout` |
| `/mcp` | **同样要求凭据**（TASK-051 A1 实测的漏洞就在这里）。Rust client 以 `Authorization: Bearer` 访问；无凭据时按 MCP 协议返回工具错误而不是裸 401（读 `mcp.py` 现有错误形态再定，写完在报告里说明选了哪种） |

实现方式二选一，**在报告里写清选了哪个与理由**：

1. 在 `app.py` 用 `dependencies=[Depends(require_user_when_remote)]` 挂在受保护 router 上；
2. 用中间件按路径前缀裁决（豁免表硬编码）。

倾向 1（显式、可测、不依赖路径字符串匹配），但需确认 `/mcp` 的挂载形态能否继承依赖。

**401 纪律**（Module/06 §2.2）：响应体**不得**区分"token 无效 / 已撤销 / 无权限"，统一 `401 unauthorized`。

## §D 首个用户初始化（bootstrap）

问题：全新部署下 `register` 默认关闭（Module/06 §2.2），于是**没有任何途径产生第一个用户**。

规则（本卡冻结）：

- `POST /api/auth/bootstrap {name, password}`：
  - `users` 表**为空** → 创建该用户并**直接签发 session cookie**（响应 201），随后**自动关闭** bootstrap；
  - 已有用户 → `403 already_initialized`（**不得**用它创建第二个账户，也不得覆盖第一个）；
  - 必须在**非本地模式**下才暴露；本地模式返回 `403 local_mode`（本地模式无需账户）。
- `GET /api/meta` 的 `authRequired && userCount == 0` 是 web 显示"初始化账户"页的唯一依据。
  **`userCount` 若要在 `/api/meta` 出现，必须把"是否为 0"这一个布尔透出（`needsBootstrap`），
  不要透出具体数量**——那属于人员信息。

## §E 与 `/healthz` 的诚实性修复（TASK-051 A1 附带项）

`service/zace_service/routers/ops.py` 的 `"auth"` 字段当前按 `local_mode` 字符串硬编码，
与真实鉴权状态无关（TASK-051 A1 证据：自报 `enabled` 却完全放行）。本卡实现真实鉴权后：

- 本地模式 → `"auth": "disabled(local)"`（保持）；
- 非本地模式 → `"auth": "required"`；
- 若因配置错误导致鉴权依赖未生效（例如忘挂 router 依赖），**`/healthz` 必须能反映**：
  加一个 `authSelfCheck` 字段：用一次**匿名内部请求**打受保护端点，期望 401；
  不是 401 就输出 `{"ok": false, "detail": …}` 且日志 WARN。

这一条是卡内强制项：**它是防止本卡"看起来实现了但没挂上"的唯一自动检查**。

## 验收标准（DoD）

- [ ] 单元/接口测试：`uv run pytest service/tests/test_auth.py -q` 全绿，**必须覆盖**：
  - [ ] 本地模式：六个 `/api/auth/*` 路径之外的全部既有端点**无需凭据**（回归保护 R34）；
  - [ ] 非本地模式：无凭据访问 `/api/query/search`、`/api/projects`、`/mcp` → **401**；
  - [ ] 非本地模式：**无效/已撤销** token → 401（TASK-051 A1 的原始缺陷，必须有用例钉住）；
  - [ ] bootstrap：空库首次成功 + 自动签发 session；第二次 → 403 `already_initialized`；
  - [ ] register 关闭时 → 403 `register_disabled`；开启时可注册且 `name` 冲突 → 409；
  - [ ] token 明文**只在创建响应出现**：`GET /api/auth/tokens` 的响应中不含明文与 hash（用字符串断言钉住）；
  - [ ] session 过期后被拒；
  - [ ] `/healthz` 的 `authSelfCheck.ok` 在正确挂载时为 `True`（可用一个"故意不挂依赖"的 app 夹具验证它为 `False`）。
- [ ] 行为验收（贴真实输出）：
      `ZACE_LOCAL_MODE=false` 起服务 → `curl /api/query/search` 无凭据得 401 →
      `bootstrap` → `login` → 带 cookie `search` 得 200 → 创建 token → 用 Bearer `search` 得 200 →
      revoke 后同一 token 得 401。
- [ ] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest`
- [ ] `docs/evidence/task-051-cloud-mcp-readiness.md` §1 A1 的处置建议在报告中逐条勾选（哪些本卡已消除、哪些留给 TASK-061）
- [ ] 任务卡"执行记录"已回填；任务板 `docs/tasks/README.md` 对应行状态改 `review`

## 参考源码锚点（只读；`../source/` 在本机不存在）

- 无直接参考实现。密码/session/token 三项均为标准做法，按 Module/06 §2.2 的措辞实现即可。

## 明确不做

- **不做租户映射**（token → owns project）→ TASK-061；本卡只回答"你是谁"。
- 不做注册开关的 web 界面、不做密码找回、不做邮箱验证、不做 OAuth/SSO（V1 不做清单）
- 不做速率限制 / 登录失败锁定（Module/06 §2.2 已知缺口，hosted 化前补，另开卡）
- 不改 `core/**`、不改 `docs/contracts/**`、不改 `docs/design/**`
- 不引 pydantic-settings、不引 ORM（`sqlite3` 直写，与 core 的存储层风格一致）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写：分支 / 验收命令与结果 / 契约影响（L2 列表）/
与设计偏差 / 未决问题。

## 执行记录

（实施 AI 在此填写：日期、关键决策、验收输出摘要、偏差与未决问题。）
