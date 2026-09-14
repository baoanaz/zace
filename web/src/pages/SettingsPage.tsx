/**
 * 设置（TASK-088 §F）：展示**当前实际生效**的配置，只读。
 *
 * 三条口径：
 * 1. **不显示明文，也不显示 key 的任何部分**（含前缀/长度）——服务端连长度都不返回，
 *    页面因此没有任何可泄露的隐藏状态；只显示"已配置 / 未配置"；
 * 2. **未配置时给可操作的文案**（缺哪几个环境变量 + 未配置时 `ask` 返回什么），不留空白；
 * 3. **数据来自 `GET /api/meta` 的 `config`**（扩展现有免鉴权端点，不新增路径）：
 *    未登录的云端只拿得到"配了没"，因此页面如实说明"登录后可看模型名"，
 *    而不是假装读到空值。
 *
 * TASK-094 §B1：追加「存储配额（只读）」卡片（单项目/单用户上限 + 告警阈值），
 * 与后端的 `Settings` 同源（设置页显示的上限与实际告警阈值不会漂移）。
 *
 * 为什么扩展现有 `/api/meta` 而不是新增只读端点：配置展示是**首屏信息**的一部分
 * （与部署形态同源，都由 `Settings` 计算），复用它可以零新增路径、零契约文件改动，
 * 且服务端能按"本地模式或已登录"精细门禁；新增端点还要动 CF-05 的路径白名单。
 */

import { useCallback, useEffect, useState } from "react";

import { type DeploymentMeta, getMeta } from "../api/client";
import { Card, ErrorBlock, KeyValue, LoadingBlock } from "../components/ui";
import { formatBytes } from "./DashboardPage";

export function SettingsPage() {
  const [meta, setMeta] = useState<DeploymentMeta | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setMeta(await getMeta());
      setError(null);
    } catch (err) {
      setMeta(null);
      setError(err);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error !== null) {
    return (
      <div className="space-y-5">
        <h1 className="text-lg font-semibold">设置</h1>
        <ErrorBlock error={error} />
      </div>
    );
  }
  if (meta === null) {
    return <LoadingBlock text="正在读取服务配置…" />;
  }

  const { embedding, llm, storage } = meta.config;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold">设置</h1>
        <p className="mt-1 text-sm text-ink-muted">
          当前实际生效的配置（只读）。改配置请设环境变量后重启服务——本页只做展示，
          不落任何密钥。
        </p>
      </div>

      <Card title="总结模型（LLM）">
        {!llm.configured && (
          <p
            data-testid="llm-notice"
            className="mb-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800"
          >
            未配置（
            <code className="rounded bg-amber-100 px-1">ask_project</code> 返回检索结果）：需要设置
            {llm.missingEnv.map((name) => (
              <code key={name} className="mr-1 rounded bg-amber-100 px-1">
                {name}
              </code>
            ))}
            后重启服务。未配置时 ask_project 不报错，会返回检索到的上下文包（D-26）。
          </p>
        )}
        {llm.configured && (
          <p className="mb-3 rounded border border-ink-line bg-paper-base px-3 py-2 text-xs text-ink-muted">
            启用外部 LLM 时，<strong>证据片段会发往该提供商</strong>（Module/06 §3）。
            key 不在此页展示，服务端也不返回它的任何片段。
          </p>
        )}
        <KeyValue
          items={[
            ["模型", llm.model ? <code>{llm.model}</code> : <span>—</span>],
            ["服务地址", llm.baseUrl ? <code>{llm.baseUrl}</code> : <span>—</span>],
            [
              "API Key",
              llm.apiKeyConfigured ? <span>已配置</span> : <span className="text-ink-muted">未配置</span>,
            ],
            ["超时（秒）", llm.timeoutS != null ? <span>{llm.timeoutS}</span> : <span>—</span>],
            ["maxTokens", llm.maxTokens != null ? <span>{llm.maxTokens}</span> : <span>—</span>],
            ["temperature", llm.temperature != null ? <span>{llm.temperature}</span> : <span>—</span>],
          ]}
        />
        {llm.model == null && llm.configured && (
          <p className="mt-2 text-xs text-ink-muted">
            已配置，但模型名与地址只对已登录用户展示（本端点是免鉴权端点）。
          </p>
        )}
      </Card>

      <Card title="检索向量模型（Embedding）">
        {embedding.error ? (
          <p className="text-sm text-rose-700">读不到 embedding 配置：{embedding.error}</p>
        ) : (
          <KeyValue
            items={[
              ["模式", embedding.mode ? <code>{embedding.mode}</code> : <span>—</span>],
              ["模型", embedding.model ? <code>{embedding.model}</code> : <span>—</span>],
              ["厂商", embedding.provider ? <code>{embedding.provider}</code> : <span>—</span>],
              ["地址", embedding.baseUrl ? <code>{embedding.baseUrl}</code> : <span>—</span>],
              ["维度", embedding.dim != null ? <span>{embedding.dim}</span> : <span>—</span>],
              [
                "单条截断",
                embedding.maxInputTokens != null ? <span>{embedding.maxInputTokens} token</span> : <span>—</span>,
              ],
            ]}
          />
        )}
        {embedding.mode === "api" && (
          <p className="mt-2 text-xs text-ink-muted">
            api 模式：索引文本会发往 embedding 服务商（EMBED_BASE_URL）。
          </p>
        )}
        {(embedding.missingEnv?.length ?? 0) > 0 && (
          <p className="mt-2 text-xs text-amber-700">
            缺少环境变量：
            {(embedding.missingEnv ?? []).map((name) => (
              <code key={name} className="mr-1 rounded bg-amber-100 px-1">
                {name}
              </code>
            ))}
          </p>
        )}
      </Card>

      <Card title="存储配额（只读）">
        {storage === undefined ? (
          <p className="text-sm text-ink-muted">
            后端未提供配额配置（旧版本服务）——升级后此处会显示单项目/单用户上限。
          </p>
        ) : (
          <>
            <KeyValue
              items={[
                [
                  "单项目上限",
                  storage.perProjectBytes === 0 ? (
                    <span className="text-ink-muted">不限</span>
                  ) : (
                    <span>{formatBytes(storage.perProjectBytes)}</span>
                  ),
                ],
                [
                  "单用户上限",
                  storage.perUserBytes === 0 ? (
                    <span className="text-ink-muted">不限</span>
                  ) : (
                    <span>{formatBytes(storage.perUserBytes)}</span>
                  ),
                ],
                ["告警阈值", <span>{Math.round(storage.warnRatio * 100)}%</span>],
              ]}
            />
            <p className="mt-2 text-xs text-ink-muted">
              达到阈值的 {Math.round(storage.warnRatio * 100)}% 时，检索工具会在**返回内容里**提醒
              Agent 转告用户去控制台删项目；**超限不阻断**（新索引与检索照常）。
              改这三项请设环境变量后重启：
              <code className="mx-1 rounded bg-paper-raised px-1">ZACE_STORAGE_LIMIT_PER_PROJECT_BYTES</code>
              <code className="mx-1 rounded bg-paper-raised px-1">ZACE_STORAGE_LIMIT_PER_USER_BYTES</code>
              <code className="mx-1 rounded bg-paper-raised px-1">ZACE_STORAGE_WARN_RATIO</code>
              （置 0 = 不限）。
            </p>
          </>
        )}
      </Card>

      <Card title="部署形态">
        <KeyValue
          items={[
            ["版本", <code>{meta.version}</code>],
            ["本地模式", <span>{meta.localMode ? "是" : "否"}</span>],
            ["需要登录", <span>{meta.authRequired ? "是" : "否"}</span>],
            ["开放注册", <span>{meta.registerOpen ? "是" : "否"}</span>],
          ]}
        />
      </Card>
    </div>
  );
}
