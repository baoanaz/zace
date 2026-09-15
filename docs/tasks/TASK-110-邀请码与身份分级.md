# TASK-110：邀请码注册、身份分级与管理员后台

> 状态：pending（**用户 2026-09-15 指定，下一批重点**）｜ 阶段：Phase 4+（增长与运营）
> 硬依赖：TASK-060（鉴权 ✅）、TASK-061（租户双层 ✅）、TASK-094（配额 ✅）
> soft 依赖：TASK-099（用户级 LLM 配置 ✅，本卡可复用其迁移手法）
> 交付物所有权（详见 §6）：
> - `service/zace_service/{metadb,invites,roles,quota}.py`（`invites.py`/`roles.py` 新建）
> - `service/zace_service/routers/{auth,admin,ops}.py`
> - `web/src/pages/{RegisterPage,AccountPage,Admin*.tsx}`、`web/src/api/client.ts`
> - `service/tests/`、`web/src/**/*.test.tsx`
>
> **不得改**：`docs/contracts/**`（如需新增契约字段，按 `docs/contracts/PROCESS.md` 走流程）、
> `core/**`（本卡纯 service + web）。

## 0. 一句话

把"谁都能注册"改成**邀请码制**，并按邀请码类型把用户分成**管理员 / 内测 / 公测**三类；
内测用户拥有**永久权益**（自定义 Key、更高额度、【拓荒者】头衔 + 编号），
管理员有**后台五模块**做运营排查。

## 1. 需求（用户原话要点）

### 1.1 邀请码

- 注册**必须**填邀请码，否则拒绝；
- 三类邀请码，格式都是 **6 位大写字母**：
  - **A 类 → 管理员**
  - **B 类 → 内测玩家**
  - **C 类 → 公测玩家**
- 注册后**登录看到的页面不同**（按身份分层）。

> **设计问题待确认**：A/B/C 是"前缀字母 + 5 位随机"还是"纯 6 位、类型另存字段"？
> 见 §7 待确认 1。

### 1.2 内测玩家权益（三项永久）

| # | 权益 | 说明 |
|---|---|---|
| 1 | **自定义 API Key** | 可指定 `zace_` 开头的 Key（普通用户只能随机生成） |
| 2 | **更高免费额度** | 项目数 / 索引空间高于普通用户（见 §1.5） |
| 3 | **永久头衔** | 注册即授予【拓荒者】，永久保留 |

### 1.3 头衔（自动授予）

| 身份 | 头衔 |
|---|---|
| 管理员 | 【执炬者】 |
| 内测玩家 | 【拓荒者】 |
| 公测玩家 | 【旅人】 |

### 1.4 编号（早期用户收藏感）

- 内测用户注册时分配 `early_member_no`；
- 展示为 `拓荒者 #0027`；
- **前 100 名显示 `拓荒者 #001` ~ `#100`，之后不再发放**（编号超过 100 就不显示编号）。

### 1.5 配额（用户指定数字）

| 身份 | 索引空间 |
|---|---|
| 公测玩家 | 500 MB |
| 内测玩家 | 1 GB |
| 管理员 | 5 GB |

> 现状：`config.py` 只有**全局默认**（per-project 500MB / per-user 2GB），
> 且 TASK-094 是**告警**语义。本卡要做**per-role 覆盖 + 按身份生效**，
> 是否升级为强制拒绝见 §7 待确认 3。

### 1.6 管理员后台五模块

| # | 模块 | 内容 |
|---|---|---|
| 1 | **用户** | 注册时间、身份、头衔、Project 数、索引占用、检索次数、最后活跃时间；支持封禁/恢复、修改配额、授予头衔 |
| 2 | **邀请码** | 创建 / 失效 / 使用记录 |
| 3 | **项目** | 排查异常索引（失败原因、跳过文件、重建入口） |
| 4 | **调用统计** | Search / Ask 次数、Token、错误率 |
| 5 | **系统状态** | 服务状态 + Embedding / LLM 状态 |

### 1.7 UI 要求

- **刻意展示拓荒者特权**，例如：
  `🧭 拓荒者特权 · 可自定义 API Key`
- 普通用户的 Key 页要**显式说明**"自定义 Key 是拓荒者专属"，形成对比而非静默隐藏。

## 2. 现状（实施前必读，均已核实）

| 事实 | 位置 | 对本卡的影响 |
|---|---|---|
| `users` 表只有 `id/name/password_hash/created_at/is_local` | `metadb.py:53` | 需加 `role`/`title`/`early_member_no`/`quota_bytes`/`banned_at` |
| 注册端点**无邀请码校验** | `routers/auth.py:304` | 本卡核心改动点 |
| Token 由服务端随机生成（`prefix` + hash，明文只返一次） | `metadb.py:552` | 自定义 Key 需改签发路径 + 唯一性校验 |
| 配额只有全局默认 + **告警**语义 | `config.py:109`、`quota.py` | 需 per-role 覆盖 |
| 审计表已有（`query_audit`/`index_runs`/`usage_summary`） | `metadb.py` | **后台 3/4 模块的数据源现成**，不用新建表 |
| 无任何 admin 端点 | `routers/` | 后台需新建 `routers/admin.py` |
| 无角色概念 | 全仓 | 鉴权依赖需加角色检查 |

**好消息**：调用统计、项目排查、系统状态三个模块的**数据都已存在**
（`usage_summary` / `index_runs` / `/api/meta` 的 provider 健康），
本卡主要是**读取侧聚合 + admin 鉴权 + 前端页面**。

## 3. 设计要点

### 3.1 数据模型（`metadb.py` 迁移）

沿用 TASK-099 的"只加列、不改既有 DDL 语义"手法：

```sql
-- users 加列（可空，旧行默认公测）
ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'public';
--   'admin' | 'beta'（内测） | 'public'（公测）
ALTER TABLE users ADD COLUMN title TEXT;              -- 冗余展示用；权威在 roles.py 的映射
ALTER TABLE users ADD COLUMN early_member_no INTEGER; -- 仅内测前 100 名
ALTER TABLE users ADD COLUMN quota_bytes INTEGER;     -- NULL = 按角色默认
ALTER TABLE users ADD COLUMN banned_at INTEGER;       -- 非空即封禁
ALTER TABLE users ADD COLUMN last_seen_at INTEGER;    -- 后台"最后活跃时间"

CREATE TABLE IF NOT EXISTS invites (
  code         TEXT PRIMARY KEY,     -- 6 位大写字母
  kind         TEXT NOT NULL,        -- 'A' | 'B' | 'C'
  created_by   TEXT,                 -- 管理员 user_id
  created_at   INTEGER NOT NULL,
  expires_at   INTEGER,              -- NULL = 永久
  revoked_at   INTEGER,
  max_uses     INTEGER NOT NULL DEFAULT 1,
  used_count   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS invite_uses (
  code      TEXT NOT NULL,
  user_id   TEXT NOT NULL,
  used_at   INTEGER NOT NULL,
  PRIMARY KEY (code, user_id)
);
```

**幂等保证**：注册事务里 `UPDATE invites SET used_count=used_count+1 WHERE code=? AND
revoked_at IS NULL AND used_count < max_uses`，**用影响行数判成败**（避免并发超发）。

### 3.2 角色与头衔（新文件 `roles.py`）

```python
ROLE_ADMIN, ROLE_BETA, ROLE_PUBLIC = "admin", "beta", "public"

TITLE_BY_ROLE = {ROLE_ADMIN: "执炬者", ROLE_BETA: "拓荒者", ROLE_PUBLIC: "旅人"}
KIND_TO_ROLE  = {"A": ROLE_ADMIN, "B": ROLE_BETA, "C": ROLE_PUBLIC}

# 配额（用户 2026-09-15 指定）
QUOTA_BY_ROLE = {
    ROLE_ADMIN:  5 * 1024**3,
    ROLE_BETA:   1 * 1024**3,
    ROLE_PUBLIC: 500 * 1024**2,
}

EARLY_MEMBER_MAX = 100          # 编号只发前 100 名
CAN_CUSTOM_KEY = {ROLE_ADMIN, ROLE_BETA}   # 自定义 Key 是内测/管理员特权
```

**头衔与权限必须同源**：前端展示的"拓荒者特权"直接读后端返回的能力位，
不要在 React 里另写一份角色判断（否则两处会漂移）。

### 3.3 能力位（`/api/auth/me` 扩展）

后端返回显式能力位，供前端渲染"特权"提示：

```json
{
  "user": {
    "name": "...", "role": "beta", "title": "拓荒者",
    "earlyMemberNo": 27,
    "capabilities": {
      "canCustomKey": true,
      "quotaBytes": 1073741824,
      "projectLimit": 10
    }
  }
}
```

> **契约影响**：`/api/auth/me` 的返回结构变化需按 §7 待确认 4 走契约流程。

### 3.4 自定义 Key（拓荒者特权）

规则：

- 格式 **必须以 `zace_` 开头**（用户要求"保证 zace_ 固定开头"）；
- 其余部分长度与字符集下限（建议 ≥16 字符，`[A-Za-z0-9_-]`）；
- **唯一性**：与既有 `token_hash` 一样进唯一索引，冲突返回 409；
- 非特权用户调用该参数 → **403 + 明确文案**（说明这是拓荒者特权），不是静默忽略；
- 安全：自定义 Key 熵更低，**禁止短于 16 字符**，且签发时记录 `is_custom=1` 便于审计。

### 3.5 管理员后台（`routers/admin.py`）

所有端点统一走 **`require_admin` 依赖**（非管理员一律 403，不泄露资源是否存在）：

| 端点 | 用途 | 数据源 |
|---|---|---|
| `GET /api/admin/users` | 用户列表（含 Project 数 / 占用 / 检索次数 / 最后活跃） | `users` + `list_projects` + `usage_summary` |
| `PATCH /api/admin/users/{id}` | 封禁/恢复、改配额、授予头衔 | 更新 `users` |
| `GET /api/admin/invites` | 邀请码列表 + 使用记录 | `invites` + `invite_uses` |
| `POST /api/admin/invites` | 创建（指定类型/次数/有效期） | `invites` |
| `DELETE /api/admin/invites/{code}` | 失效 | `invites.revoked_at` |
| `GET /api/admin/projects` | 排查异常索引（失败原因/跳过文件） | `index_runs` |
| `GET /api/admin/stats` | Search/Ask 次数、Token、错误率 | `query_audit` + `usage_summary` |
| `GET /api/admin/system` | 服务 + Embedding/LLM 状态 | `/api/meta` 同源 |

**封禁语义**：封禁后 session 与 token **立即失效**（校验时检查 `banned_at`），
不是等下次登录。

### 3.6 前端页面差异

| 身份 | 页面差异 |
|---|---|
| 公测 | 控制台 / 接入指南 / API Key / 历史 / 账户（**无自定义 Key**，显示"拓荒者特权"说明） |
| 内测 | 同上 + **自定义 Key 表单** + 头衔徽章（`拓荒者 #0027`） |
| 管理员 | 同上 + **后台五模块入口** |

## 4. 分期（建议按此顺序，每期可独立验收）

| 期 | 内容 | 可独立验证 |
|---|---|---|
| **P1** | 迁移 + `roles.py` + 邀请码校验注册 + 头衔/编号自动授予 | 无码注册 403；B 码注册后 `me` 返回 `拓荒者 + 编号` |
| **P2** | 自定义 Key + 能力位 + 配额按角色生效 | 内测可建 `zace_mykey123456`；公测建自定义 Key 得 403 |
| **P3** | 管理员后台后端五模块（`routers/admin.py`） | 非管理员访问全 403；管理员能列出用户与统计 |
| **P4** | 前端：注册页邀请码、账户页头衔/编号、Key 页特权展示、后台五模块页面 | 三种身份登录看到不同页面 |

**P1 必须先落地**：它是唯一有**数据迁移风险**的部分，后续都建立在它之上。

## 5. 验收标准

### P1

- [ ] 无邀请码注册 → **403/400 + 明确错误码**（不是 500）；
- [ ] 用 A 码注册 → `role=admin`、`title=执炬者`、`earlyMemberNo=NULL`；
- [ ] 用 B 码注册 → `role=beta`、`title=拓荒者`、`earlyMemberNo=1`（首位）、展示 `拓荒者 #0001`；
- [ ] 用 C 码注册 → `role=public`、`title=旅人`、无编号；
- [ ] 同一邀请码超用 → 拒绝；失效码 → 拒绝；过期码 → 拒绝；
- [ ] **并发安全**：`max_uses=1` 的码被两个请求同时用，**只有 1 个成功**（用影响行数断言）；
- [ ] **第 101 名内测**：`earlyMemberNo` 为 NULL，前端不显示编号；
- [ ] 旧用户（迁移前存在）默认 `role=public`，登录不受影响；
- [ ] **迁移路径（本机实际情况）**：跑迁移后 `xuwenzheng` 为 `role=admin`、`title=执炬者`，
      其 Key `zace_123456` **仍可用**（迁移不改 token_hash）；
- [ ] **全新路径**：空库跑 `bootstrap` 建的首个账户自动为 `admin`（否则 A 类码无人能造）。

### P2

- [ ] 内测用户建自定义 Key `zace_customkey12345` 成功，且**能用于 MCP 鉴权**；
- [ ] 公测用户传自定义 Key → **403**，文案说明是拓荒者特权；
- [ ] 自定义 Key 不以 `zace_` 开头 → 400；短于 16 字符 → 400；
- [ ] 与既有 Key 冲突 → 409；
- [ ] 配额：内测 1 GB、管理员 5 GB、公测 500 MB（`/api/account/overview` 可见）。

### P3

- [ ] 公测/内测访问任一 `/api/admin/*` → **403**，且不泄露资源是否存在；
- [ ] 管理员能看到用户列表（含 Project 数、索引占用、检索次数、最后活跃）；
- [ ] 封禁用户后其**既有 token 立即 401**（不是等重新登录）；
- [ ] 邀请码创建/失效/使用记录正确；
- [ ] 统计页的 Search/Ask 次数与 `usage_summary` 一致（同源，不重复计算）。

### P4

- [ ] 三种身份登录后**页面确实不同**（截图或 vitest 断言）；
- [ ] 内测用户 Key 页显示 `🧭 拓荒者特权 · 可自定义 API Key`；
- [ ] 公测用户 Key 页**显式说明**自定义是拓荒者专属；
- [ ] 头衔与编号在账户页可见（`拓荒者 #0027`）。

### 全局

- [ ] 全仓 `uv run pytest -o addopts="" -q` 全绿；`ruff check .` 全绿；
- [ ] 依赖方向检查通过；
- [ ] **不破坏既有接入**：现有用户（无 `role` 列值）登录 + MCP 调用全部照常；
- [ ] 基准不回退（本卡不碰检索，跑一次确认）：[`../handbook/benchmark/README.md`](../handbook/benchmark/README.md)。

## 6. 文件所有权

| 文件 | 动作 |
|---|---|
| `service/zace_service/metadb.py` | 加迁移（只加列/表） |
| `service/zace_service/roles.py` | **新建**：角色/头衔/配额/能力的单一事实源 |
| `service/zace_service/invites.py` | **新建**：邀请码生成与核销 |
| `service/zace_service/quota.py` | 改为按角色取值 |
| `service/zace_service/routers/auth.py` | 注册校验 + `me` 扩展 + 自定义 Key |
| `service/zace_service/routers/admin.py` | **新建**：后台五模块 |
| `service/zace_service/app.py` | 注册新路由 + `require_admin` 依赖 |
| `service/tests/test_invites.py` | **新建** |
| `service/tests/test_admin.py` | **新建** |
| `web/src/pages/RegisterPage.tsx` | 邀请码输入 |
| `web/src/pages/ApiKeysPage.tsx` | 特权展示 + 自定义表单 |
| `web/src/pages/AccountPage.tsx` | 头衔 + 编号 |
| `web/src/pages/Admin*.tsx` | **新建**：五模块 |
| `web/src/api/client.ts` | 类型与调用 |
| `docs/handbook/getting-started/agent接入与API-Key.md` | 补邀请码与自定义 Key |

## 7. 待确认（开工前与用户确认）

1. **邀请码格式**：A/B/C 是"首字母限定类型 + 后 5 位随机"（如 `A7K2M9`），
   还是"6 位纯随机、类型存在 `invites.kind` 字段"？
   *建议后者*：不暴露类型规律，更安全；类型由数据库字段决定。
2. **编号是否只给内测**：用户说"首批内测用户"，确认管理员**不占**编号（§3.2 已按此设计）。
3. **配额是硬拒还是告警**：现状是告警（可超）。改成超限**拒绝新索引**吗？
   *建议*：先保持告警 + 后台可见，硬拒在压测后再定（避免用户数据传一半失败）。
4. **`/api/auth/me` 契约**：新增 `role/title/earlyMemberNo/capabilities` 属契约变更，
   按 `docs/contracts/PROCESS.md` 走流程还是先按"向后兼容加字段"处理？

## 7.1 已定决策（用户 2026-09-15 拍板）

### 首个管理员

- **管理员就是 `xuwenzheng`**（用户本人，密码 `123456`）；
- **实现方式：指定名字提升**，不依赖 `bootstrap`（"最早创建者"）语义。

理由：`bootstrap` 在本机 live 库里已经用掉了（首个账户是 `xwz`，非管理员），
且未来换部署环境时"最早创建者"也不一定是管理员（可能是别人先试手）。
定名字更可预测。

**做法**：

1. 迁移时按 `users.name` 匹配（可用 `ZACE_ADMIN_NAME` 配置，默认 `xuwenzheng`）
   把它提为 `role='admin'`；
2. `bootstrap` 保留现有原子语义（`user_count()==0` 才可用），**行为去分两种情况**：
   - **空库（全新部署）** → 建的账户直接 `role='admin'`（否则死锁：没人能造 A 类码）；
   - **已有用户** → 本来就返回 403，不涉及；
3. 两者的**优先级**：迁移按名字匹配优先；名字不存在且库为空时才走 bootstrap 路径。

> 即：**已有库按名字指定；全新库按 bootstrap 首位**。两条路径都要有单测。

### 旧用户 `xwz`

- **删除**（用户 2026-09-15 拍板）；
- 已于 2026-09-15 在本机 live 库执行：删除 `users` 1 行、`api_tokens` 4 行、
  `sessions` 3 行（**无项目、无审计数据**）；删除前备份为
  `~/.zace/live/zace-meta.db.bak-<日期>`；
- 迁移脚本**不包含**这条删除（属一次性环境清理，已在库里做完）；
- 现 live 库只剩 `xuwenzheng` + Key `zace_123456`。

## 8. 明确不做

- 不做邮箱/短信验证（邀请码已足够）；
- 不做付费/充值（额度是固定的，不支持购买）；
- 不做邀请码二维码/分享链接（V1.5 再说）；
- 不做审计日志的独立管理页（已有日志与 trace 查询，见 `operations/`）；
- 不做管理员操作的双人复核（V1 单管理员足够）。

## 9. 执行记录

（实施 AI 在此填写：日期 + 分支 + 验收命令与结果 + 与设计的偏差 + 未决问题。）
