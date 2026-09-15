/**
 * API Key 管理（TASK-071；TASK-110 §1.7 追加拓荒者特权展示与自定义表单）。
 *
 * 三条安全口径（Module/06 §2.2）：
 * 1. **明文只显示一次**：创建成功后短暂展示并提供复制，离开页面即无法再取；
 * 2. 列表接口**永不含明文与哈希**——页面也不缓存明文到 localStorage/sessionStorage；
 * 3. 自定义 Key 的输入框也不缓存（提交后立刻清空）。
 *
 * TASK-110 §1.7 的 UI 要求（用户原话："**刻意展示拓荒者特权**"）：
 *
 * - 有特权（拓荒者/管理员）→ 顶部显式横幅 ``🧭 拓荒者特权 · 可自定义 API Key`` + 自定义表单；
 * - 无特权（公测）→ **显式说明**"自定义 Key 是拓荒者专属"，而不是静默隐藏。
 *   静默隐藏会让人以为产品没有这个能力；显式说明才能形成对比与期待。
 *
 * 判断依据是后端返回的 ``capabilities.canCustomKey``（**不在这里写 role === "beta"**）：
 * 两处各写一份角色判断必然漂移，而漂移的表现是"页面上说能自定义、点了却 403"。
 */

import { useCallback, useEffect, useState } from "react";

import {
  type Account,
  type ApiKeyCreated,
  type ApiKeySummary,
  createApiKey,
  getMe,
  listApiKeys,
  revokeApiKey,
} from "../api/client";
import { CopyButton, EmptyState, ErrorBlock, LoadingBlock, Page } from "../components/ui";
import { formatTime } from "./DashboardPage";

/** 自定义 Key 的最短长度（与后端 ``MIN_CUSTOM_KEY_CHARS`` 一致；仅做输入体验）。 */
const MIN_CUSTOM_KEY_CHARS = 16;
/** 自定义 Key 的固定前缀（用户要求"保证 zace_ 固定开头"）。 */
const KEY_PREFIX = "zace_";

export function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeySummary[] | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [name, setName] = useState("");
  const [customKey, setCustomKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [listed, me] = await Promise.all([listApiKeys(), getMe().catch(() => null)]);
      setKeys(listed);
      setAccount(me);
    } catch (err) {
      setKeys(null);
      setError(err);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onCreate(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setCreated(await createApiKey(name.trim(), customKey.trim()));
      setName("");
      setCustomKey("");
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function onRevoke(key: ApiKeySummary) {
    const confirmed = window.confirm(
      `确认撤销 API Key「${key.name || key.prefix}」？\n\n撤销后使用该 Key 的客户端会立即失效（软删）。`,
    );
    if (!confirmed) return;
    try {
      await revokeApiKey(key.id);
      await load();
    } catch (err) {
      setError(err);
    }
  }

  const canCustomKey = account?.capabilities.canCustomKey === true;

  return (
    <Page>
      <div>
        <h1 className="text-lg font-semibold">API Key</h1>
        <p className="mt-1 text-sm text-ink-muted">
          供编辑器 / CLI / 客户端使用。明文只在创建时显示一次。
        </p>
      </div>

      <PrivilegeBanner account={account} />

      {error !== null && <ErrorBlock error={error} />}

      {created && (
        <section className="rounded-lg border border-emerald-300 bg-emerald-50 p-4">
          <h2 className="text-sm font-semibold text-emerald-900">
            已创建：{created.name || created.prefix}
          </h2>
          <p className="mt-1 text-xs text-emerald-800">
            这是<strong>唯一一次</strong>能看到完整 Key 的机会，请立即复制到客户端配置里。
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <code className="flex-1 break-all rounded border border-ink-line bg-paper-card px-2 py-1 font-mono text-xs text-ink-primary">
              {created.token}
            </code>
            <CopyButton text={created.token} label="复制 Key" />
            <button
              type="button"
              onClick={() => setCreated(null)}
              className="rounded border border-emerald-300 px-2 py-1 text-xs text-emerald-900 hover:bg-emerald-100"
            >
              我已保存，隐藏
            </button>
          </div>
        </section>
      )}

      <form
        onSubmit={onCreate}
        className="flex flex-wrap items-end gap-2 rounded-lg border border-ink-line bg-paper-card p-4 shadow-sm"
      >
        <label className="flex-1 text-sm">
          <span className="mb-1 block text-xs text-ink-muted">名称（便于分辨用途）</span>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="例如：家里的 Cursor"
            className="w-full rounded border border-ink-line bg-paper-card px-3 py-1.5 text-sm text-ink-primary"
          />
        </label>
        {canCustomKey ? (
          <label className="flex-1 text-sm">
            <span className="mb-1 block text-xs text-ink-muted">
              自定义 Key（留空 = 服务端随机生成）
            </span>
            <input
              value={customKey}
              onChange={(event) => setCustomKey(event.target.value)}
              placeholder={`${KEY_PREFIX}my-project-2026`}
              autoComplete="off"
              className="w-full rounded border border-ink-line bg-paper-card px-3 py-1.5 font-mono text-xs text-ink-primary"
            />
            <span className="mt-1 block text-[11px] text-ink-muted">
              必须以 {KEY_PREFIX} 开头，其后至少 {MIN_CUSTOM_KEY_CHARS} 个字符
              （字母、数字、- 与 _）。
            </span>
          </label>
        ) : (
          <p className="flex-1 rounded border border-dashed border-ink-line px-3 py-2 text-xs text-ink-muted">
            🔒 自定义 API Key 是【拓荒者】专属特权：当前身份只能由服务端随机生成。
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-accent-seal px-4 py-1.5 text-sm text-white disabled:opacity-40"
        >
          {busy ? "创建中…" : "创建 Key"}
        </button>
      </form>

      <section className="rounded-lg border border-ink-line bg-paper-card shadow-sm">
        <header className="border-b border-ink-line/70 px-4 py-3">
          <h2 className="text-sm font-semibold text-ink-primary">现有的 Key</h2>
        </header>
        {keys === null ? (
          <LoadingBlock />
        ) : keys.length === 0 ? (
          <EmptyState
            title="还没有 API Key"
            hint="用上方表单创建一把，再把完整 Key 配置到编辑器 / CLI 客户端里；只有创建那一刻能看到完整值。"
          />
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="text-left text-xs text-ink-muted">
                <th className="px-4 py-2 font-normal">名称</th>
                <th className="px-4 py-2 font-normal">前缀</th>
                <th className="px-4 py-2 font-normal">来源</th>
                <th className="px-4 py-2 font-normal">创建时间</th>
                <th className="px-4 py-2 font-normal">最近使用</th>
                <th className="px-4 py-2 font-normal"></th>
              </tr>
            </thead>
            <tbody>
              {keys.map((key) => (
                <tr key={key.id} className="border-t border-ink-line/60">
                  <td className="px-4 py-2">
                    {key.name || <span className="text-ink-muted">未命名</span>}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs">{key.prefix}…</td>
                  <td className="px-4 py-2 text-xs text-ink-muted">
                    {key.isCustom ? "自定义" : "随机生成"}
                  </td>
                  <td className="px-4 py-2 text-xs text-ink-muted">
                    {formatTime(key.createdAt)}
                  </td>
                  <td className="px-4 py-2 text-xs text-ink-muted">
                    {key.lastUsedAt === null ? "从未使用" : formatTime(key.lastUsedAt)}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => void onRevoke(key)}
                      className="rounded border border-rose-300 px-2 py-1 text-xs text-rose-700 hover:bg-rose-50"
                    >
                      撤销
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </Page>
  );
}

/**
 * 特权横幅（TASK-110 §1.7）。
 *
 * 两种身份**都有话说**：有特权时宣称它（用户要求"刻意展示"），没有时说明它属于谁。
 * 只在 ``account`` 已加载时渲染——首帧还不知道身份就宣称什么都是错的。
 */
function PrivilegeBanner({ account }: { account: Account | null }) {
  if (account === null || account.isLocal) return null;
  if (account.capabilities.canCustomKey) {
    return (
      <section
        data-testid="privilege-banner"
        className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900"
      >
        🧭 {account.title}特权 · 可自定义 API Key
        {account.earlyMemberNo !== null && (
          <span className="ml-2 font-mono text-xs text-amber-800">
            编号 #{String(account.earlyMemberNo).padStart(3, "0")}
          </span>
        )}
      </section>
    );
  }
  return (
    <section
      data-testid="privilege-banner"
      className="rounded-lg border border-ink-line bg-paper-base px-4 py-3 text-xs text-ink-muted"
    >
      自定义 API Key（指定以 {KEY_PREFIX} 开头的 Key）是【拓荒者】专属特权；
      当前身份（{account.title}）使用服务端随机生成的 Key。
    </section>
  );
}
