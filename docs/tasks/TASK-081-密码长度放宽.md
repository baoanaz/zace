# TASK-081：密码长度下限放宽到 3 位

> 状态：pending ｜ 阶段：Phase 4（M4）｜ 硬依赖：无 ｜ soft 依赖：无
> 建议分支：`feature/task-081-password-min_<你的缩写><MMDD>`
> 交付物所有权：
> - `service/zace_service/routers/auth.py`（**仅** `MIN_PASSWORD_CHARS` 一处常量及其文案）
> - `service/tests/test_auth.py`（**仅**修正被新阈值影响的断言）
> - `web/src/api/client.ts`（**仅**错误文案里的 "至少 8 个字符"）
>
> 清单外文件不得改。

## 目标

用户原话（2026-09-13）：

> 登入密码不做 8 位数限制。3 位数及以上就可以了。

当前 `MIN_PASSWORD_CHARS = 8` 会让用户设一个短密码时被 400 拒绝。
改为 **3**，并同步前端的错误文案。

## 现状（实测）

| 位置 | 当前值 |
|---|---|
| `service/zace_service/routers/auth.py:44` | `MIN_PASSWORD_CHARS = 8` |
| `service/zace_service/routers/auth.py:241` | `if len(payload.password) < MIN_PASSWORD_CHARS:` → 400 `invalid_password` |
| `web/src/api/client.ts:101` | `return "密码不符合要求：至少 8 个字符（上限 200）。";` |

## ⚠️ 本卡最大的坑（编排者已预检，务必先读）

`service/tests/test_auth.py` 里有**两处**用字符串 `"short"`（**5 个字符**）来构造"密码太短"的用例：

- `test_weak_password_rejected`（约 183 行）
- 无鉴权路径白名单那个用例里的 bootstrap 断言（约 302 行）

把阈值降到 3 之后，`"short"` 变成**合法**密码，这两个断言会**直接失效**（测试会红，或者更糟：
改错了方向之后它仍然"通过"但测的是别的东西）。

**正确做法**：把这两处的 `"short"` 改成**真正短于 3** 的值（如 `"ab"`），
并保留原有断言意图（"低于下限 → 400 `invalid_password`"）。
**不得**删掉这两个用例，也不得放宽断言。

同时**新增**一条边界用例：长度正好 3 的密码**必须被接受**（这是本次改动的正向证明）。

## 验收标准（DoD）

- [ ] `uv run pytest service/tests/test_auth.py -q` 全绿，**必须覆盖**：
  - [ ] 长度 3 的密码 → bootstrap 成功（201）；
  - [ ] 长度 2 的密码 → 400 `invalid_password`；
  - [ ] 原有的"太短被拒"用例改为用 2 字符后仍断言 400；
  - [ ] 上限 200 的行为**不变**（别顺手改）。
- [ ] 行为验收（贴真实输出）：起一个云端模式服务，用 3 位密码 bootstrap 成功：
      ```bash
      ZACE_LOCAL_MODE=false ZACE_DATA_ROOT=/tmp/zace-pw uv run zace-service serve --port 8894 &
      curl -c /tmp/pw-c -X POST http://127.0.0.1:8894/api/auth/bootstrap \
        -H 'Content-Type: application/json' -d '{"name":"owner","password":"abc"}'
      # 期望 201
      ```
- [ ] 错误文案同步：前端 `client.ts` 与后端 `auth.py` 的提示都不再出现 "8"。
- [ ] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest -o addopts="" -q`
- [ ] 任务卡"执行记录"已回填；任务板状态改为 `review`。

## 明确不做

- **不改**登录逻辑、不引入密码复杂度规则（大小写/数字/符号都不要求）；
- **不改** `MAX_PASSWORD_CHARS = 200`；
- **不改** `hash_password` / `verify_password`（`service/zace_service/auth.py`）；
- **不动**前端登录页的表单校验逻辑（`LoginPage.tsx` 当前只校验"非空"，与阈值无关；若你发现它硬编码了 8，先写进"未决问题"而不是直接改）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板。

## 执行记录

（实施 AI 在此填写。）
