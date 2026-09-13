/**
 * API 层：错误信封统一解析 + 服务未启动的可操作提示。
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  SERVICE_DOWN_MESSAGE,
  errorHint,
  getHealth,
  search,
} from "./client";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("request 错误处理", () => {
  it("把 CF-05 错误信封转成 ApiError（保留 code/status）", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ error: { code: "project_not_found", message: "项目不存在" } }, 404),
      ),
    );

    const error = await getHealth().catch((err: unknown) => err);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("project_not_found");
    expect((error as ApiError).status).toBe(404);
    expect((error as ApiError).message).toBe("项目不存在");
  });

  it("501 占位被识别为 not_implemented（未就绪页与错误块据此提示）", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          { error: { code: "not_implemented", message: "POST /api/auth/login（登录）尚未实现" } },
          501,
        ),
      ),
    );

    const error = await search("p1", "q").catch((err: unknown) => err);
    expect(ApiError.isNotImplemented(error)).toBe(true);
  });

  it("网络失败（服务未启动）给出可操作提示，而不是 Failed to fetch", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    const error = await getHealth().catch((err: unknown) => err);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("network_error");
    expect((error as ApiError).message).toBe(SERVICE_DOWN_MESSAGE);
  });

  it("非 JSON 错误响应也能给出可用文案", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("<html>502</html>", { status: 502 })),
    );

    const error = await getHealth().catch((err: unknown) => err);
    expect((error as ApiError).code).toBe("http_502");
    expect((error as ApiError).message).toContain("502");
  });
});

describe("errorHint（错误码 → 下一步）", () => {
  it("索引未就绪与索引失败要给出不同动作", () => {
    expect(errorHint(new ApiError("index_in_progress", "x", 409))).toContain("等索引完成");
    expect(errorHint(new ApiError("index_failed", "x", 500))).toContain("不要反复重试");
  });

  it("未知码不编造指引", () => {
    expect(errorHint(new ApiError("something_new", "x", 400))).toBeNull();
  });
});
