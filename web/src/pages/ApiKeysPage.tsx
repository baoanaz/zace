/**
 * API Key 管理（TASK-071）。
 *
 * 两条安全口径（Module/06 §2.2）：
 * 1. **明文只显示一次**：创建成功后短暂展示并提供复制，离开页面即无法再取；
 * 2. 列表接口**永不含明文与哈希**——页面也不缓存明文到 localStorage/sessionStorage。
 */

import { useCallback, useEffect, useState } from "react";

import {
  type ApiKeyCreated,
  type ApiKeySummary,
  createApiKey,
  listApiKeys,
  revokeApiKey,
} from "../api/client";
import { CopyButton, EmptyState, ErrorBlock, LoadingBlock } from "../components/ui";
import { formatTime } from "./DashboardPage";

export function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeySummary[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setKeys(await listApiKeys());
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
      setCreated(await createApiKey(name.trim()));
      setName("");
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

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold">API Key</h1>
        <p className="mt-1 text-sm text-ink-muted">
          供编辑器 / CLI / 客户端使用。明文只在创建时显示一次。
        </p>
      </div>

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
                <th className="px-4 py-2 font-normal">创建时间</th>
                <th className="px-4 py-2 font-normal">最近使用</th>
                <th className="px-4 py-2 font-normal"></th>
              </tr>
            </thead>
            <tbody>
              {keys.map((key) => (
                <tr key={key.id} className="border-t border-ink-line/60">
                  <td className="px-4 py-2">{key.name || <span className="text-ink-muted">未命名</span>}</td>
                  <td className="px-4 py-2 font-mono text-xs">{key.prefix}…</td>
                  <td className="px-4 py-2 text-xs text-ink-muted">{formatTime(key.createdAt)}</td>
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
    </div>
  );
}
