/**
 * 唯一请求出口：所有对 zace-service 的调用都在这里（Module/07 §2）。
 *
 * 两条纪律：
 * 1. **错误只有一种形态**：CF-05 信封 `{error:{code,message}}` → `ApiError`；网络/代理失败 →
 *    `ApiError("network_error", …)`。页面不需要认识 `fetch` 或 `Response`。
 * 2. **服务未启动要可操作**：Vite 代理打不通时 `fetch` 抛 `TypeError`，此时给出的是
 *    "怎么把服务起起来"的提示，而不是一个白屏或 `Failed to fetch`。
 */

import type {
  AskResponse,
  ErrorEnvelope,
  Health,
  Project,
  SearchResponse,
} from "./types";

/**
 * API 基址。
 *
 * 默认空串 = 同源（生产由 Caddy 同源托管；开发由 Vite 代理）。
 * `VITE_ZACE_API_BASE` 用于两种场景：web 与服务不同源部署，以及端到端测试直连真实服务
 * （`web/src/pages/e2e.test.tsx`）。
 */
export const API_BASE: string = import.meta.env.VITE_ZACE_API_BASE ?? "";

export const DEFAULT_MAX_TOKENS = 10_000;
export const MAX_MAX_TOKENS = 20_000;
export const MAX_QUERY_CHARS = 2_000;

/** 服务未启动时的可操作提示（与 `docs/handbook/M2a-验收手册.md` §1 的命令一致）。 */
export const SERVICE_DOWN_MESSAGE =
  "连不上 zace-service。请先启动服务（示例：uv run zace-service local --repo <你的仓库>），" +
  "或在开发模式下确认 Vite 代理的 ZACE_WEB_API 指向正确的地址。";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }

  /** 服务端路径存在但尚未实现（`/api/auth/*`、`/api/usage/*` 的 501 占位）。 */
  static isNotImplemented(error: unknown): boolean {
    return error instanceof ApiError && error.code === "not_implemented";
  }
}

/** 把错误映射成"下一步做什么"（页面统一从这里取指引，不各自写文案）。 */
export function errorHint(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null;
  switch (error.code) {
    case "network_error":
      return SERVICE_DOWN_MESSAGE;
    case "index_in_progress":
      return "索引尚未就绪：等索引完成后再查询（进度见项目页），或在索引完成后手动重扫。";
    case "index_failed":
      return "上次索引失败：请到项目页查看 indexProgress.error，修复后手动重扫。不要反复重试同一查询。";
    case "embedding_unavailable":
    case "embedding_unreachable":
      return "embedding provider 不可用：检查 EMBED_MODE / EMBED_MODEL / EMBED_BASE_URL / EMBED_API_KEY 配置。";
    case "project_not_found":
      return "项目不存在或未被当前用户认领：确认 projectId（可用项目页复制）后重试。";
    case "index_running":
      return "该项目的索引已在运行，无需重复触发。";
    case "invalid_root":
      return "目录不存在或不是目录：请填绝对路径。";
    case "local_mode_required":
      return "该端点仅在本地模式可用（本地模式之外的绑定请用客户端上传）。";
    case "local_root_unknown":
      return "服务重启后未重新 attach：请重新绑定本地目录。";
    case "not_implemented":
      return "该能力尚未实现（后端仍是 501 占位），依赖卡号见页面的“未就绪”说明。";
    default:
      return null;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const init: RequestInit = {
    method: options.method ?? "GET",
    headers: { Accept: "application/json" },
    // 本地模式无鉴权；M2c 起 session cookie 会随同源请求自动带上（credentials 默认 same-origin）。
  };
  if (options.body !== undefined) {
    init.headers = { ...init.headers, "Content-Type": "application/json" };
    init.body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError("network_error", SERVICE_DOWN_MESSAGE, 0);
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload: unknown = text.length > 0 ? safeJson(text) : null;

  if (!response.ok) {
    const envelope = payload as ErrorEnvelope | null;
    const code = envelope?.error?.code ?? `http_${response.status}`;
    const message = envelope?.error?.message ?? `请求失败（HTTP ${response.status}）`;
    throw new ApiError(code, message, response.status);
  }
  return payload as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

// --------------------------------------------------------------------------- 端点

export function getHealth(): Promise<Health> {
  return request<Health>("/healthz");
}

export function listProjects(): Promise<Project[]> {
  return request<Project[]>("/api/projects");
}

export function getProject(id: string): Promise<Project> {
  return request<Project>(`/api/projects/${encodeURIComponent(id)}`);
}

export function attachProject(root: string, displayName?: string): Promise<Project> {
  const body: Record<string, unknown> = { root };
  if (displayName) body.displayName = displayName;
  return request<Project>("/api/projects/attach", { method: "POST", body });
}

export function rescanProject(id: string): Promise<{ indexProgress: unknown }> {
  return request<{ indexProgress: unknown }>(
    `/api/projects/${encodeURIComponent(id)}/rescan`,
    { method: "POST" },
  );
}

export function deleteProject(id: string): Promise<void> {
  return request<void>(`/api/projects/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function search(
  projectId: string,
  query: string,
  maxTokens: number = DEFAULT_MAX_TOKENS,
): Promise<SearchResponse> {
  return request<SearchResponse>("/api/query/search", {
    method: "POST",
    body: { projectId, query, maxTokens },
  });
}

export function ask(projectId: string, question: string): Promise<AskResponse> {
  return request<AskResponse>("/api/query/ask", {
    method: "POST",
    body: { projectId, question },
  });
}
