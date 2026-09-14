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
  ErrorEnvelope,
  Health,
  Project,
  SearchResponse,
} from "./types";

// 页面从 `api/client` 取类型（唯一出口），避免到处 import types 的相对路径。
export type {
  AskResponse,
  EvidenceSummaryItem,
  Health,
  IndexProgress,
  PackMeta,
  Project,
  SearchResponse,
  SyncStatus,
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
    // ---- TASK-060 鉴权 ----
    case "unauthorized":
      return "凭据无效或已失效：请重新登录（或检查 API Key 是否已被撤销）。";
    case "register_disabled":
      return "注册已关闭：首个账户请用初始化页面创建，或由管理员开启 ZACE_REGISTER_OPEN。";
    case "already_initialized":
      return "已存在账户：初始化接口已关闭，请直接登录。";
    case "name_taken":
      return "账户名已被占用：换一个名字。";
    case "invalid_password":
      return "密码不符合要求：至少 3 个字符（上限 200）。";
    case "invalid_name":
      return "账户名不能为空，且不超过 64 个字符。";
    case "local_mode":
      return "本地单用户模式没有账户与 API Key（R34）：把 ZACE_LOCAL_MODE 设为 false 才启用。";
    case "token_not_found":
      return "该 API Key 不存在或已被撤销。";
    // ---- TASK-062/064 统计 ----
    case "meta_db_unavailable":
      return "元数据库（zace-meta.db）未就绪：历史与用量暂时读不到。";
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

// --------------------------------------------------------------------------- 账户（TASK-060）

/** 部署形态（`GET /api/meta`，**免鉴权**）：首屏据此决定显示登录/注册/初始化。 */
export interface DeploymentMeta {
  version: string;
  localMode: boolean;
  authRequired: boolean;
  registerOpen: boolean;
  needsBootstrap: boolean;
  userCount: number | null;
  /** TASK-088 §F：设置页的只读配置（**绝不含 key 任何部分**）。TASK-094 §B1 追加 `storage`。 */
  config: EffectiveConfig;
}

/**
 * 生效中的服务配置（设置页展示）。
 *
 * 两种详细度（服务端按"本地模式或已登录"门禁）：未鉴权时只有 `configured` / `missingEnv` / `mode`，
 * 模型名与地址等属内部拓扑，登录后才给；`apiKeyConfigured` 永远是布尔（连长度都不给）。
 */
export interface EffectiveConfig {
  embedding: EmbeddingConfigView;
  llm: LlmConfigView;
  /** TASK-094 §B1：存储配额（只读展示；`0` 表示不限）。 */
  storage?: StorageConfigView;
}

export interface EmbeddingConfigView {
  mode?: string;
  configured?: boolean;
  missingEnv?: string[];
  model?: string | null;
  provider?: string | null;
  baseUrl?: string | null;
  dim?: number | null;
  maxInputTokens?: number | null;
  offline?: boolean;
  error?: string;
  /**
   * 速率与吞吐限额（TASK-100 §需求9 要求展示）。
   *
   * **后端尚未提供**（`GET /api/meta` 目前不返回这两个字段）——声明为可选，
   * 页面在缺失时显示 `—`；TASK-099 补齐后无需再改前端。
   */
  tpm?: number | null;
  rpm?: number | null;
}

export interface LlmConfigView {
  configured: boolean;
  apiKeyConfigured: boolean;
  missingEnv: string[];
  model?: string | null;
  baseUrl?: string | null;
  timeoutS?: number;
  maxTokens?: number;
  temperature?: number;
  /**
   * 当前生效的是哪一份配置（TASK-099 §C-4）。
   *
   * `user` = 用户自己在设置页配的那份（`ask_project` 正在用它）；`server` = 环境变量默认。
   * 设置页据此把"保存/清除"的语义说清楚，而不是让用户猜。
   */
  source?: "user" | "server";
  /** 用户配置缺哪几项（字段名，不是环境变量名；TASK-099 §C）。 */
  missingKeys?: string[];
  /** 厂商与上下文窗口（TASK-100 §需求9）。同样**后端尚未提供**，缺失时显示 `—`。 */
  provider?: string | null;
  maxContextTokens?: number | null;
}

/** `PUT /api/auth/llm-config` 的响应（TASK-099 §C-3；**不含 key 的任何部分**）。 */
export interface LlmConfigSaved {
  model: string;
  baseUrl: string;
  apiKeyConfigured: boolean;
  updatedAt: number;
  source: "user";
}

/** 当前身份（`GET /api/auth/me`）。 */
export interface Account {
  userId: string;
  name: string;
  createdAt: number;
  isLocal: boolean;
  via: string;
}

/** API Key 列表项（**不含明文与哈希**）。 */
export interface ApiKeySummary {
  id: string;
  name: string;
  prefix: string;
  createdAt: number;
  lastUsedAt: number | null;
}

/** 创建 API Key 的响应（`token` 明文**仅此一次**）。 */
export interface ApiKeyCreated extends ApiKeySummary {
  token: string;
}

export function getMeta(): Promise<DeploymentMeta> {
  return request<DeploymentMeta>("/api/meta");
}

export function getMe(): Promise<Account> {
  return request<Account>("/api/auth/me");
}

export function login(name: string, password: string): Promise<Account> {
  return request<Account>("/api/auth/login", { method: "POST", body: { name, password } });
}

export function register(name: string, password: string): Promise<Account> {
  return request<Account>("/api/auth/register", { method: "POST", body: { name, password } });
}

/** 首个用户初始化（`users` 表为空时可用；用后自动关闭）。 */
export function bootstrap(name: string, password: string): Promise<Account> {
  return request<Account>("/api/auth/bootstrap", { method: "POST", body: { name, password } });
}

export async function logout(): Promise<void> {
  await request<void>("/api/auth/logout", { method: "POST" });
}

export function listApiKeys(): Promise<ApiKeySummary[]> {
  return request<ApiKeySummary[]>("/api/auth/tokens");
}

export function createApiKey(name: string): Promise<ApiKeyCreated> {
  return request<ApiKeyCreated>("/api/auth/tokens", { method: "POST", body: { name } });
}

export function revokeApiKey(id: string): Promise<void> {
  return request<void>(`/api/auth/tokens/${encodeURIComponent(id)}`, { method: "DELETE" });
}

// --------------------------------------------------------------------------- 用户级 LLM 配置（TASK-099）

/**
 * 保存本用户的 LLM 配置（TASK-099 §C-3）。
 *
 * `apiKey` 传空串 = **保持不变**（key 从不回显，因此"留空不改"是唯一可用语义）；
 * 首次保存必须给值，否则服务端返回 400 `invalid_llm_config`。
 *
 * 响应**不含 key 的任何部分**（连长度都没有），因此调用方拿不到它去回填输入框——
 * 这是刻意的：输入框在提交后就该清空。
 */
export function saveUserLlmConfig(input: {
  model: string;
  baseUrl: string;
  apiKey?: string;
}): Promise<LlmConfigSaved> {
  return request<LlmConfigSaved>("/api/auth/llm-config", {
    method: "PUT",
    body: { model: input.model, baseUrl: input.baseUrl, apiKey: input.apiKey ?? "" },
  });
}

/** 删除本用户的 LLM 配置 → 回落服务端默认（幂等：本来就没配也返回 204）。 */
export function deleteUserLlmConfig(): Promise<void> {
  return request<void>("/api/auth/llm-config", { method: "DELETE" });
}

// --------------------------------------------------------------------------- 统计与历史（TASK-062/064）

export interface IndexRun {
  runId: number;
  projectId: string;
  state: string;
  startedAt: number;
  finishedAt: number;
  durationMs: number;
  filesTotal: number;
  filesProcessed: number;
  chunks: number;
  errors: number;
  error: string | null;
}

export interface IndexStats {
  projectId?: string;
  total: number;
  succeeded: number;
  failed: number;
  avgDurationMs: number | null;
  minDurationMs?: number | null;
  maxDurationMs?: number | null;
  lastRunAt: number | null;
  lastState: string | null;
  recent: IndexRun[];
  diskBytes?: number;
}

/** 单项目索引统计：内存态当前进度 + 落库历史（两者口径不同，**不合成**）。 */
export interface ProjectIndexStats {
  projectId: string;
  current: {
    state: string;
    startedAt: number | null;
    finishedAt: number | null;
    processedFiles: number;
    totalFiles: number;
    error: string | null;
  };
  history: IndexStats;
  diskBytes: number;
}

export interface UsageRecord {
  queryId: number;
  projectId: string;
  mode: string;
  query: string;
  answerable: boolean | null;
  confidence: string | null;
  degraded: boolean;
  latencyMs: number;
  evidenceCount: number;
  docsCount: number;
  usedTokens: number;
  citationCoverage: number | null;
  /**
   * 请求 trace id（TASK-094 §C）：与响应头 `X-Request-Id`、服务端日志的 `requestId` 同源。
   * `null` = 这条记录落库时没有 trace（旧版本写下的行）——页面显示 `—`，不编造。
   * 用户报错时把它报给管理员，可到 `/api/request-log/{requestId}` 查完整链路（TASK-090）。
   */
  requestId: string | null;
  createdAt: number;
}

export interface UsageSummary {
  projectId?: string;
  days: number;
  total: number;
  succeeded: number;
  insufficient: number;
  failed: number;
  avgLatencyMs: number | null;
  p95LatencyMs: number | null;
  confidenceDistribution: Record<string, number>;
  citationCoverageAvg: number | null;
  topQueries: { query: string; count: number }[];
  recent: UsageRecord[];
}

/** 一个配额的维度（用量 / 上限 / 状态；`limitBytes=0` 表示**不限**）。 */
export interface QuotaDimensionView {
  usedBytes: number;
  limitBytes: number;
  ratio: number | null;
  status: "ok" | "warning" | "exceeded";
  unlimited: boolean;
}

/** 存储配额状态（TASK-094 §B4；`/api/account/overview` 的 `storage`）。 */
export interface QuotaStatusView {
  status: "ok" | "warning" | "exceeded";
  warnRatio: number;
  projectId: string;
  user: QuotaDimensionView;
  project: QuotaDimensionView;
}

/** 设置页展示的配额配置（`/api/meta` 的 `config.storage`，只读）。 */
export interface StorageConfigView {
  perProjectBytes: number;
  perUserBytes: number;
  warnRatio: number;
  /** 两个上限都为 0 时为 `false`（“不限”，页面只显示已用）。 */
  enabled: boolean;
}

/** 首页仪表盘（账户资料 + 索引统计 + 查询用量 + 存储配额）。 */
export interface AccountOverview {
  account: {
    name: string;
    createdAt: number;
    isLocal: boolean;
    projectCount: number;
  };
  index: IndexStats;
  usage: UsageSummary;
  projects: Project[];
  days: number;
  /** TASK-094 §B4：后端未提供时缺省（页面隐藏配额条）。 */
  storage?: QuotaStatusView;
}

export function getAccountOverview(days = 30): Promise<AccountOverview> {
  return request<AccountOverview>(`/api/account/overview?days=${days}`);
}

export function getProjectIndexStats(id: string, limit = 50): Promise<ProjectIndexStats> {
  return request<ProjectIndexStats>(
    `/api/projects/${encodeURIComponent(id)}/index-stats?limit=${limit}`,
  );
}

export function getProjectIndexRuns(id: string, limit = 50): Promise<IndexRun[]> {
  return request<IndexRun[]>(
    `/api/projects/${encodeURIComponent(id)}/index-runs?limit=${limit}`,
  );
}

export function getUsageSummary(days = 30, limit = 50): Promise<UsageSummary> {
  return request<UsageSummary>(`/api/usage/summary?days=${days}&limit=${limit}`);
}

export function getProjectUsage(id: string, days = 30): Promise<UsageSummary> {
  return request<UsageSummary>(
    `/api/usage/projects/${encodeURIComponent(id)}?days=${days}`,
  );
}

/**
 * 删除项目（TASK-094 §D）：级联删除该项目的**索引数据**（含向量与同步账本）。
 *
 * 后端已就绪（`DELETE /api/projects/{id}`，含 TASK-061 归属校验：他人项目同样 404）。
 * 返回 204（无内容），因此调用方不需要处理响应体。
 */
export function deleteProject(id: string): Promise<void> {
  return request<void>(`/api/projects/${encodeURIComponent(id)}`, { method: "DELETE" });
}
