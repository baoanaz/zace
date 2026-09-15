/**
 * 账户页（TASK-110 §1.3/§1.4）：身份、头衔、编号与特权一览。
 *
 * 为什么单独一页（而不是塞进控制台）：控制台的口径是"看数据"（用户 2026-09-14 明确
 * "用户只是看数据"），而身份与特权是"我是谁、我能做什么"——两件事混在一起会让控制台
 * 又开始变大杂烩。TASK-100 已经立过这个规矩（项目页与设置页都是这样分出去的）。
 *
 * 三条展示口径：
 *
 * 1. **头衔来自后端**（``/api/auth/me`` 的 ``title``），不在这里按 role 拼字符串；
 * 2. **编号只在有编号时显示**（``拓荒者 #0027``；第 101 名起如实不显示）；
 * 3. **额度显示实际生效值**（``capabilities.quotaBytes``，与上传被拒时用的那根线同源）。
 */

import { useEffect, useState } from "react";

import { type Account, type AccountOverview, getAccountOverview, getMe } from "../api/client";
import { ErrorBlock, LoadingBlock, Page } from "../components/ui";
import { formatTime } from "./DashboardPage";

export function AccountPage() {
  const [account, setAccount] = useState<Account | null>(null);
  const [overview, setOverview] = useState<AccountOverview | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [me, data] = await Promise.all([getMe(), getAccountOverview()]);
        setAccount(me);
        setOverview(data);
      } catch (err) {
        setError(err);
      }
    })();
  }, []);

  if (error !== null) return <ErrorBlock error={error} />;
  if (account === null) return <LoadingBlock />;

  const storage = overview?.storage;

  return (
    <Page>
      <div>
        <h1 className="text-lg font-semibold">账户</h1>
        <p className="mt-1 text-sm text-ink-muted">身份、特权与用量上限。</p>
      </div>

      <section className="rounded-lg border border-ink-line bg-paper-card p-6 shadow-sm">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-serif text-2xl font-semibold text-ink-primary">
            {account.name}
          </span>
          <TitleBadge account={account} />
        </div>
        <p className="mt-2 text-xs text-ink-muted">
          {account.isLocal ? "本地单用户模式" : `云端账户 · 通过${viaLabel(account.via)}访问`}
          {" · 注册于 "}
          {formatTime(account.createdAt)}
        </p>      </section>

      <section className="rounded-lg border border-ink-line bg-paper-card p-4 shadow-sm">
        <h2 className="mb-3 text-sm font-semibold text-ink-primary">特权与额度</h2>
        <dl className="divide-y divide-dashed divide-ink-line/70 text-sm">
          <Row
            label="自定义 API Key"
            value={
              account.capabilities.canCustomKey ? (
                <span className="text-emerald-700">可用（拓荒者特权）</span>
              ) : (
                <span className="text-ink-muted">不可用（拓荒者专属）</span>
              )
            }
          />
          <Row label="索引空间上限" value={formatBytes(account.capabilities.quotaBytes)} />
          {storage && (
            <Row
              label="当前占用"
              value={`${formatBytes(storage.user.usedBytes)}（${
                storage.user.ratio === null
                  ? "未设上限"
                  : `${(storage.user.ratio * 100).toFixed(0)}%`
              }）`}
            />
          )}
          <Row label="项目数" value={String(overview?.account.projectCount ?? 0)} />
        </dl>
        {account.capabilities.quotaBytes > 0 && (
          <p className="mt-3 text-xs text-ink-muted">
            超额后**新的索引上传会被拒绝**（检索与已有项目不受影响）；删除不再需要的项目即可释放空间。
          </p>
        )}
      </section>
    </Page>
  );
}

/**
 * 头衔徽章：``拓荒者 #0027``。
 *
 * 编号只在后端给了编号时显示（``earlyMemberNo !== null``）——第 101 名起如实没有编号，
 * 前端不补一个"#—"之类的占位（那会让人以为号码丢了）。
 */
export function TitleBadge({ account }: { account: Account }) {
  if (account.isLocal) return null;
  const withNumber =
    account.earlyMemberNo === null
      ? account.title
      : `${account.title} #${String(account.earlyMemberNo).padStart(3, "0")}`;
  const tone =
    account.role === "admin"
      ? "border-rose-300 bg-rose-50 text-rose-800"
      : account.role === "beta"
        ? "border-amber-300 bg-amber-50 text-amber-900"
        : "border-ink-line bg-paper-base text-ink-muted";
  return (
    <span
      data-testid="title-badge"
      className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${tone}`}
    >
      {withNumber}
    </span>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-2">
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className="text-ink-primary">{value}</dd>
    </div>
  );
}

/** 字节 → 人读（与后端 ``quota.format_bytes`` 同一套单位与舍入）。 */
export function formatBytes(size: number): string {
  if (size <= 0) return "不限";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KiB`;
  if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MiB`;
  return `${(size / 1024 / 1024 / 1024).toFixed(2)} GiB`;
}

function viaLabel(via: string): string {
  if (via === "token") return "API Key";
  if (via === "session") return "登录会话";
  return via;
}
