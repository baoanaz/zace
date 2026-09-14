"""TASK-098 截图用 mock：静态托管 web/dist + 假 API（仅本地截图用，不入库）。

用法: python3 mock_server.py <port> <mode: cloud|local> <dist_dir>
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1])
MODE = sys.argv[2]
DIST = sys.argv[3]

ACCOUNT = {
    "userId": "u1",
    "name": "xuwenzheng",
    "createdAt": 1789300000,
    "isLocal": MODE == "local",
    "via": "local" if MODE == "local" else "session",
}

PROJECTS = [
    {
        "projectId": "zace-a1b2c3",
        "displayName": "zace",
        "createdAt": 1789300000,
        "attachedRoot": "/home/dev/zace",
        "indexProgress": {
            "state": "done",
            "startedAt": 1789305500,
            "finishedAt": 1789305566,
            "processedFiles": 338,
            "totalFiles": 344,
            "error": None,
        },
        "sync": {"filesIndexed": 338, "chunks": 4210, "symbols": 1877, "edges": 903},
    },
    {
        "projectId": "demo-9f8e7d",
        "displayName": "demo",
        "createdAt": 1789200000,
        "attachedRoot": None,
        "indexProgress": {
            "state": "failed",
            "startedAt": 1789290000,
            "finishedAt": 1789290042,
            "processedFiles": 12,
            "totalFiles": 40,
            "error": "embedding provider unreachable",
        },
        "sync": {"filesIndexed": 12, "chunks": 90},
    },
]

OVERVIEW = {
    "account": {"name": "xuwenzheng", "createdAt": 1789300000, "isLocal": MODE == "local", "projectCount": 2},
    "index": {
        "total": 12,
        "succeeded": 9,
        "failed": 1,
        "avgDurationMs": 61000,
        "minDurationMs": 800,
        "maxDurationMs": 230900,
        "lastRunAt": 1789305566,
        "lastState": "done",
        "diskBytes": 12582912,
        "recent": [],
    },
    "usage": {
        "days": 30,
        "total": 128,
        "succeeded": 103,
        "insufficient": 17,
        "failed": 8,
        "avgLatencyMs": 412,
        "p95LatencyMs": 1180,
        "confidenceDistribution": {"high": 61, "medium": 42},
        "citationCoverageAvg": None,
        "topQueries": [],
        "recent": [],
    },
    "projects": PROJECTS,
    "days": 30,
}

USAGE = {
    "days": 30,
    "total": 128,
    "succeeded": 103,
    "insufficient": 17,
    "failed": 8,
    "avgLatencyMs": 412,
    "p95LatencyMs": 1180,
    "confidenceDistribution": {"high": 61, "medium": 42},
    "citationCoverageAvg": None,
    "topQueries": [],
    "recent": [
        {
            "queryId": 1,
            "projectId": "zace-a1b2c3",
            "mode": "hybrid",
            "query": "索引流水线在哪里做增量失效？",
            "answerable": True,
            "confidence": "high",
            "degraded": False,
            "latencyMs": 388,
            "evidenceCount": 7,
            "docsCount": 2,
            "usedTokens": 8100,
            "citationCoverage": 0.86,
            "createdAt": 1789305500,
        },
        {
            "queryId": 2,
            "projectId": "zace-a1b2c3",
            "mode": "hybrid",
            "query": "RRF 融合的 k 值",
            "answerable": False,
            "confidence": "low",
            "degraded": False,
            "latencyMs": 210,
            "evidenceCount": 2,
            "docsCount": 0,
            "usedTokens": 2400,
            "citationCoverage": None,
            "createdAt": 1789305400,
        },
    ],
}

RUNS = [
    {
        "runId": 3,
        "projectId": "zace-a1b2c3",
        "state": "done",
        "startedAt": 1789305500,
        "finishedAt": 1789305566,
        "durationMs": 66000,
        "filesTotal": 344,
        "filesProcessed": 338,
        "chunks": 4210,
        "errors": 0,
        "error": None,
    },
    {
        "runId": 2,
        "projectId": "zace-a1b2c3",
        "state": "done",
        "startedAt": 1789290000,
        "finishedAt": 1789290100,
        "durationMs": 100000,
        "filesTotal": 300,
        "filesProcessed": 300,
        "chunks": 3900,
        "errors": 2,
        "error": "2 个文件解析失败",
    },
]

KEYS = [
    {
        "id": "k1",
        "name": "家里的 Cursor",
        "prefix": "zace_ab12",
        "createdAt": 1789300000,
        "lastUsedAt": 1789305400,
    },
    {"id": "k2", "name": "ci-runner", "prefix": "zace_cd34", "createdAt": 1789200000, "lastUsedAt": None},
]

META_CLOUD = {
    "version": "0.0.1",
    "localMode": False,
    "authRequired": True,
    "registerOpen": False,
    "needsBootstrap": False,
    "userCount": 1,
    "config": {
        "embedding": {
            "mode": "api",
            "configured": True,
            "missingEnv": [],
            "model": "voyage-4-lite",
            "provider": "voyage",
            "baseUrl": "https://api.voyageai.com",
            "dim": 1024,
            "maxInputTokens": 32000,
        },
        "llm": {
            "configured": True,
            "apiKeyConfigured": True,
            "missingEnv": [],
            "model": "claude-sonnet-4",
            "baseUrl": "https://api.anthropic.com",
            "timeoutS": 60,
            "maxTokens": 4000,
            "temperature": 0.2,
        },
    },
}

META_LOCAL = {**META_CLOUD, "localMode": True, "authRequired": False, "userCount": None}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # 静音
        pass

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/meta":
            if MODE == "local":
                return self._json(META_LOCAL)
            if MODE == "cloudauth":
                return self._json(META_CLOUD)
            if MODE == "register":
                return self._json({**META_CLOUD, "registerOpen": True})
            if MODE == "bootstrap":
                return self._json({**META_CLOUD, "needsBootstrap": True, "userCount": 0})
            return self._json(META_CLOUD)
        if path == "/api/auth/me":
            if MODE == "local" or MODE == "cloudauth":
                return self._json({**ACCOUNT, "isLocal": False, "via": "session"})
            return self._json({"error": {"code": "unauthorized", "message": "缺少或无效的凭据"}}, 401)
        if path == "/api/account/overview":
            return self._json(OVERVIEW)
        if path == "/api/projects":
            return self._json(PROJECTS)
        if path == "/api/usage/summary":
            return self._json(USAGE)
        if path.endswith("/index-runs"):
            return self._json(RUNS)
        if path == "/api/auth/tokens":
            return self._json(KEYS)
        if path == "/healthz":
            return self._json({"status": "ok", "localMode": MODE == "local", "projects": []})
        return self._static(path)

    def _static(self, path):
        rel = "index.html" if path in ("/", "") or "." not in os.path.basename(path) else path.lstrip("/")
        full = os.path.join(DIST, rel)
        if not os.path.isfile(full):
            full = os.path.join(DIST, "index.html")
        with open(full, "rb") as fh:
            data = fh.read()
        ctype = "text/html"
        if full.endswith(".js"):
            ctype = "text/javascript"
        elif full.endswith(".css"):
            ctype = "text/css"
        elif full.endswith(".svg"):
            ctype = "image/svg+xml"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
