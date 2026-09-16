/**
 * 登录 / 注册 / 初始化（TASK-071；首屏页面）。TASK-098 §B 改版为**左装饰 + 右白卡片**。
 *
 * 一个页面承担三件事，由 `GET /api/meta` 决定显示哪个：
 *
 * | 部署状态 | 显示 |
 * |---|---|
 * | 本地模式（默认） | 不需要登录，直接进入（避免"强制登录但没有账户体系"的死局） |
 * | 云端 + 无账户 | **初始化账户**（users 为空，register 默认关闭时这是唯一入口） |
 * | 云端 + 有账户 | **登录**（下方可切换到注册表单） |
 *
 * 都不需要用户去记"我该点哪个"。
 *
 * TASK-098 只改**外观**：左侧装饰区（老纸底 + 衬线品牌字 + 细线几何图案），
 * 右侧纯白浮卡片（参考 Voyage 登录页）。三种模式、三个字段、错误展示、忙态禁用、
 * 窄屏（<768px）时装饰区收起，只留表单。
 *
 * TASK-110 §1.1：注册表单追加**邀请码**输入（注册**必须**有码）。它是注册模式的专属字段——
 * 登录与初始化不需要它（那两条路径面对的是已有/首个账户）。
 */

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  ApiError,
  type Account,
  type DeploymentMeta,
  bootstrap,
  getMeta,
  login,
  register,
} from "../api/client";
import { ErrorBlock, LoadingBlock } from "../components/ui";

/** 邀请码长度（与后端冻结的 6 位一致；前端只做输入体验，校验仍以后端为准）。 */
const INVITE_CODE_LENGTH = 6;

type Mode = "login" | "register" | "bootstrap";

export function LoginPage({ onSignedIn }: { onSignedIn: (account: Account) => void }) {
  const navigate = useNavigate();
  const [meta, setMeta] = useState<DeploymentMeta | null>(null);
  const [mode, setMode] = useState<Mode>("login");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  //: 邀请码（TASK-110；仅注册模式使用）。大写化在输入时就做——码面只有大写字母/数字，
  //: 而手机输入法默认首字母大写、从聊天软件粘贴也可能带小写，在这里统一比让用户自己改成大写好。
  const [inviteCode, setInviteCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    void (async () => {
      try {
        const resolved = await getMeta();
        setMeta(resolved);
        setMode(resolved.needsBootstrap ? "bootstrap" : "login");
      } catch (err) {
        setError(err);
      }
    })();
  }, []);

  const submit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      if (mode === "register" && password !== confirm) {
        setError(new ApiError("password_mismatch", "两次输入的密码不一致", 400));
        return;
      }
      if (mode === "register" && inviteCode.trim().length === 0) {
        setError(new ApiError("invalid_invite", "注册需要邀请码：请填入收到的邀请码", 400));
        return;
      }
      setBusy(true);
      setError(null);
      try {
        const account =
          mode === "login"
            ? await login(name.trim(), password)
            : mode === "register"
              ? await register(name.trim(), password, inviteCode.trim())
              : await bootstrap(name.trim(), password);
        onSignedIn(account);
        navigate("/", { replace: true });
      } catch (err) {
        setError(err);
      } finally {
        setBusy(false);
      }
    },
    [confirm, inviteCode, mode, name, onSignedIn, navigate, password],
  );

  if (error !== null && meta === null) return <ErrorBlock error={error} />;
  if (meta === null) return <LoadingBlock text="正在检查部署状态…" />;

  const title =
    mode === "bootstrap" ? "初始化账户" : mode === "register" ? "注册" : "登录";
  const submitLabel =
    mode === "bootstrap" ? "创建并进入" : mode === "register" ? "注册并进入" : "登录";

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      {/*
       * 左装饰区：老纸底 + 衬线品牌字 + 细线几何图案（§B）。
       * 窄屏收起（hidden md:flex）——不能挤压表单。
       * 图案只用 CSS 边框渐变拼出细线矩形，不引图片/字体资源。
       */}
      <section
        aria-hidden="true"
        className="relative hidden overflow-hidden border-r border-ink-line md:flex md:w-1/2 md:flex-col md:justify-between md:p-12 lg:w-3/5"
      >
        <div className="relative z-10 flex items-center gap-3">
          <span className="h-6 w-6 rounded-full border-2 border-accent-seal/60" />
          <span className="font-serif text-lg tracking-[0.2em] text-ink-muted uppercase">
            zace
          </span>
        </div>

        <div className="relative z-10 max-w-md">
          {/* 装饰性大标题：用 p 而不是 h1——真正的 h1 是表单标题（屏幕阅读器只该读一个）。 */}
          <p className="font-serif text-4xl leading-tight font-semibold text-ink-primary lg:text-5xl">
            Workspace
            <br />
            Context Engine
          </p>
          <p className="mt-5 text-sm leading-relaxed text-ink-muted">
            把仓库索引成可检索的上下文，让编码 Agent 在你的代码里找到依据，
            <br />
            而不是靠猜。
          </p>
        </div>

        <p className="relative z-10 text-xs tracking-wider text-ink-muted">
          Workspace Context Engine
        </p>

        {/* 细线几何图案：三层同心圆角矩形，颜色取自墨线 token。 */}
        <div className="pointer-events-none absolute inset-0 z-0 flex items-center justify-center">
          <div className="h-[26rem] w-[26rem] rotate-12 rounded-[3rem] border border-ink-line/70" />
          <div className="absolute h-[34rem] w-[34rem] rotate-12 rounded-[4rem] border border-ink-line/50" />
          <div className="absolute h-[42rem] w-[42rem] rotate-12 rounded-[5rem] border border-ink-line/30" />
        </div>
      </section>

      {/* 右表单区：米白浮卡片（TASK-100：不再是纯白，避免在浅底上突兀）。 */}
      <section className="flex flex-1 items-center justify-center px-4 py-10 md:px-10">
        <div className="w-full max-w-md">
          {/* 窄屏下装饰区收起，品牌字改在卡片上方显示。 */}
          <div className="mb-6 text-center md:hidden">
            <div className="font-serif text-2xl font-semibold text-ink-primary">zace</div>
            <p className="mt-1 text-sm text-ink-muted">Workspace Context Engine</p>
          </div>

          <form
            onSubmit={submit}
            className="space-y-4 rounded-xl border border-ink-line bg-paper-card p-6 shadow-[0_18px_50px_-24px_rgba(42,36,25,0.45)] md:p-8"
          >
            <h1 className="font-serif text-xl font-semibold text-ink-primary">{title}</h1>

            {mode === "bootstrap" && (
              <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                这是首次部署：创建第一个账户后，初始化入口会自动关闭。
              </p>
            )}

            <label className="block text-sm">
              <span className="mb-1 block text-xs text-ink-muted">账户</span>
              <input
                name="name"
                autoComplete="username"
                value={name}
                onChange={(event) => setName(event.target.value)}
                className="w-full rounded border border-ink-line bg-paper-card px-3 py-2 text-sm text-ink-primary"
                required
              />
            </label>

            <label className="block text-sm">
              <span className="mb-1 block text-xs text-ink-muted">密码</span>
              <input
                name="password"
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full rounded border border-ink-line bg-paper-card px-3 py-2 text-sm text-ink-primary"
                required
              />
            </label>

            {mode === "register" && (
              <label className="block text-sm">
                <span className="mb-1 block text-xs text-ink-muted">确认密码</span>
                <input
                  name="confirm"
                  type="password"
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(event) => setConfirm(event.target.value)}
                  className="w-full rounded border border-ink-line bg-paper-card px-3 py-2 text-sm text-ink-primary"
                  required
                />
              </label>
            )}

            {/*
              TASK-110（2026-09-15 用户要求）：邀请码排在**最后**（账户 → 密码 → 确认密码 → 邀请码）。
              之前它夹在密码与确认密码之间，读起来像“密码的一部分”。
            */}
            {mode === "register" && (
              <div className="block text-sm">
                <label className="block">
                  <span className="mb-1 block text-xs text-ink-muted">邀请码</span>
                  <input
                    name="inviteCode"
                    autoComplete="off"
                    value={inviteCode}
                    onChange={(event) => setInviteCode(event.target.value.toUpperCase())}
                    placeholder="6 位邀请码"
                    maxLength={INVITE_CODE_LENGTH}
                    className="w-full rounded border border-ink-line bg-paper-card px-3 py-2 font-mono text-sm tracking-widest text-ink-primary"
                    required
                  />
                </label>
                {/* 提示放在 label **之外**：放进 label 会把它拼进可访问名（屏幕阅读器与测试都
                    会把“邀请码”读成一整句话），而它本来只是辅助说明。 */}
                <span className="mt-1 block text-xs text-ink-muted">
                  目前是邀请制：没有邀请码请联系管理员获取。
                </span>
              </div>
            )}

            {error !== null && <ErrorBlock error={error} />}

            <button
              type="submit"
              disabled={
                busy ||
                name.trim().length === 0 ||
                password.length === 0 ||
                (mode === "register" && inviteCode.trim().length === 0)
              }
              className="w-full rounded bg-accent-seal px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              {busy ? "处理中…" : submitLabel}
            </button>

            <div className="space-y-1 border-t border-ink-line pt-3 text-center text-xs">
              {mode === "login" && (
                <button
                  type="button"
                  className="text-accent-seal underline"
                  onClick={() => setMode("register")}
                >
                  没有账户？注册
                </button>
              )}
              {mode === "register" && (
                <button
                  type="button"
                  className="text-accent-seal underline"
                  onClick={() => setMode("login")}
                >
                  已有账户？登录
                </button>
              )}
            </div>
          </form>

          <p className="mt-4 text-center text-xs text-ink-muted">zace v{meta.version}</p>
        </div>
      </section>
    </div>
  );
}
