/**
 * 登录 / 注册 / 初始化（TASK-071；首屏页面）。
 *
 * 一个页面承担三件事，由 `GET /api/meta` 决定显示哪个：
 *
 * | 部署状态 | 显示 |
 * |---|---|
 * | 本地模式（默认） | 不需要登录，直接进入（避免"强制登录但没有账户体系"的死局） |
 * | 云端 + 无账户 | **初始化账户**（users 为空，register 默认关闭时这是唯一入口） |
 * | 云端 + 有账户 | **登录**（register 开启时下方多一个注册表单） |
 *
 * 都不需要用户去记"我该点哪个"。
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

type Mode = "login" | "register" | "bootstrap";

export function LoginPage({ onSignedIn }: { onSignedIn: (account: Account) => void }) {
  const navigate = useNavigate();
  const [meta, setMeta] = useState<DeploymentMeta | null>(null);
  const [mode, setMode] = useState<Mode>("login");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
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
      setBusy(true);
      setError(null);
      try {
        const account =
          mode === "login"
            ? await login(name.trim(), password)
            : mode === "register"
              ? await register(name.trim(), password)
              : await bootstrap(name.trim(), password);
        onSignedIn(account);
        navigate("/", { replace: true });
      } catch (err) {
        setError(err);
      } finally {
        setBusy(false);
      }
    },
    [confirm, mode, name, onSignedIn, navigate, password],
  );

  if (error !== null && meta === null) return <ErrorBlock error={error} />;
  if (meta === null) return <LoadingBlock text="正在检查部署状态…" />;

  const title =
    mode === "bootstrap" ? "初始化账户" : mode === "register" ? "注册" : "登录";
  const submitLabel =
    mode === "bootstrap" ? "创建并进入" : mode === "register" ? "注册并进入" : "登录";

  return (
    <div className="mx-auto max-w-md py-10">
      <div className="mb-6 text-center">
        <div className="font-mono text-2xl font-semibold">zace</div>
        <p className="mt-1 text-sm text-slate-500">Workspace Context Engine</p>
      </div>

      <form
        onSubmit={submit}
        className="space-y-4 rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h1 className="text-base font-semibold">{title}</h1>

        {mode === "bootstrap" && (
          <p className="rounded border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-900">
            这是首次部署：创建第一个账户后，初始化入口会自动关闭。
          </p>
        )}

        <label className="block text-sm">
          <span className="mb-1 block text-xs text-slate-500">账户</span>
          <input
            name="name"
            autoComplete="username"
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="w-full rounded border border-slate-300 px-3 py-2 text-sm"
            required
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block text-xs text-slate-500">密码</span>
          <input
            name="password"
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full rounded border border-slate-300 px-3 py-2 text-sm"
            required
          />
        </label>

        {mode === "register" && (
          <label className="block text-sm">
            <span className="mb-1 block text-xs text-slate-500">确认密码</span>
            <input
              name="confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              className="w-full rounded border border-slate-300 px-3 py-2 text-sm"
              required
            />
          </label>
        )}

        {error !== null && <ErrorBlock error={error} />}

        <button
          type="submit"
          disabled={busy || name.trim().length === 0 || password.length === 0}
          className="w-full rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-40"
        >
          {busy ? "处理中…" : submitLabel}
        </button>

        <div className="space-y-1 border-t border-slate-100 pt-3 text-center text-xs">
          {mode === "login" && meta.registerOpen && (
            <button type="button" className="underline" onClick={() => setMode("register")}>
              没有账户？注册
            </button>
          )}
          {mode === "register" && (
            <button type="button" className="underline" onClick={() => setMode("login")}>
              已有账户？登录
            </button>
          )}
          {!meta.registerOpen && mode === "login" && (
            <p className="text-slate-400">
              注册已关闭（ZACE_REGISTER_OPEN）——单用户自部署的默认配置。
            </p>
          )}
        </div>
      </form>

      <p className="mt-4 text-center text-xs text-slate-400">
        zace v{meta.version}
        {meta.authRequired ? " · 云端形态（需鉴权）" : " · 本地形态"}
      </p>
    </div>
  );
}
