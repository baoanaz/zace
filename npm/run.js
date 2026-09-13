#!/usr/bin/env node
// zace-client 的 npm 启动器。
//
// 职责（与 notace 的 npm/run.js 同思路，但按 zace 的现状做了取舍）：
//   1. 在缓存目录里找平台二进制；
//   2. 找不到 → 从 GitHub Release 下载对应归档并解压（带并发锁与重试）；
//   3. 都失败 → 回退到"本地已构建的二进制"或给出可操作的安装指引；
//   4. 用 stdio 拉起它（**inherit**：编辑器看到的就是二进制的 stdin/stdout）。
//
// 纪律：本包装器**只往 stderr 写日志**，stdout 必须原样留给 MCP 的 JSON-RPC 帧。

"use strict";

const { spawn, spawnSync } = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const https = require("https");
const os = require("os");
const path = require("path");

const PACKAGE_NAME = "zace-client";
const BINARY_NAME = process.platform === "win32" ? "zace-client.exe" : "zace-client";
const REPO_OWNER = "baoanaz";
const REPO_NAME = "zace";
const MAX_REDIRECTS = 10;
const REQUEST_TIMEOUT = 60_000;
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1_000;

// 本地回退：仓库内已构建的二进制（开发者用 `cargo build` 后即可跑 `node npm/run.js`）。
function localFallbacks() {
  return [
    path.resolve(__dirname, "..", "client", "target", "release", BINARY_NAME),
    path.resolve(__dirname, "..", "client", "target", "debug", BINARY_NAME),
  ];
}

function packageVersion() {
  return require("./package.json").version;
}

function cacheDir() {
  const home = os.homedir();
  const base =
    process.platform === "win32"
      ? path.join(process.env.LOCALAPPDATA || path.join(home, "AppData", "Local"), PACKAGE_NAME)
      : process.platform === "darwin"
        ? path.join(home, "Library", "Caches", PACKAGE_NAME)
        : path.join(process.env.XDG_CACHE_HOME || path.join(home, ".cache"), PACKAGE_NAME);
  // 版本进路径：升级后自然换目录，避免旧二进制残留。
  return path.join(base, packageVersion());
}

// 资产命名与 .github/workflows/release.yml 的 asset_name 一一对应（改一处必须改两处）。
function assetName() {
  const { platform, arch } = process;
  if (platform === "linux" && arch === "x64") return "zace-client_Linux_x86_64.tar.gz";
  if (platform === "linux" && arch === "arm64") return "zace-client_Linux_aarch64.tar.gz";
  if (platform === "darwin") return "zace-client_Darwin_universal.tar.gz";
  if (platform === "win32" && arch === "x64") return "zace-client_Windows_x86_64.zip";
  if (platform === "win32" && arch === "arm64") return "zace-client_Windows_aarch64.zip";
  throw new Error(
    `不支持的平台：${platform}/${arch}。` +
      "支持 Linux(x64/arm64)、macOS(x64/arm64)、Windows(x64/arm64)，或从源码构建：cd client && cargo build --release"
  );
}

function log(message) {
  console.error(`[${PACKAGE_NAME}] ${message}`);
}

function httpsGet(url, redirects = 0) {
  return new Promise((resolve, reject) => {
    if (redirects > MAX_REDIRECTS) return reject(new Error("重定向过多"));
    const headers = { "User-Agent": PACKAGE_NAME, Accept: "application/vnd.github.v3+json" };
    if (process.env.GITHUB_TOKEN) headers.Authorization = `token ${process.env.GITHUB_TOKEN}`;
    const request = https.get(url, { headers }, (response) => {
      if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
        response.resume();
        const next = response.headers.location;
        if (!next.startsWith("https://")) return reject(new Error(`不安全的跳转：${next}`));
        return resolve(httpsGet(next, redirects + 1));
      }
      if (response.statusCode !== 200) {
        response.resume();
        return reject(new Error(`HTTP ${response.statusCode}：${response.statusMessage}`));
      }
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => resolve(Buffer.concat(chunks)));
      response.on("error", reject);
    });
    request.on("error", reject);
    request.setTimeout(REQUEST_TIMEOUT, () => {
      request.destroy();
      reject(new Error("请求超时"));
    });
  });
}

function downloadToFile(url, destination, redirects = 0) {
  return new Promise((resolve, reject) => {
    if (redirects > MAX_REDIRECTS) return reject(new Error("重定向过多"));
    const headers = { "User-Agent": PACKAGE_NAME, Accept: "application/octet-stream" };
    if (process.env.GITHUB_TOKEN) headers.Authorization = `token ${process.env.GITHUB_TOKEN}`;
    const file = fs.createWriteStream(destination);
    const fail = (error) => {
      file.close(() => {
        try {
          fs.unlinkSync(destination);
        } catch {}
        reject(error);
      });
    };
    const request = https.get(url, { headers }, (response) => {
      if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
        response.resume();
        const next = response.headers.location;
        if (!next.startsWith("https://")) return fail(new Error(`不安全的跳转：${next}`));
        file.close(() => {
          try {
            fs.unlinkSync(destination);
          } catch {}
          downloadToFile(next, destination, redirects + 1).then(resolve).catch(reject);
        });
        return;
      }
      if (response.statusCode !== 200) {
        response.resume();
        return fail(new Error(`HTTP ${response.statusCode}：${response.statusMessage}`));
      }
      response.pipe(file);
      file.on("finish", () => file.close(() => resolve()));
      file.on("error", fail);
    });
    request.on("error", fail);
    request.setTimeout(REQUEST_TIMEOUT, () => request.destroy(new Error("下载超时")));
  });
}

// 子进程的 stdout 一律重定向到 stderr：解压工具绝不允许污染 MCP 的 stdout。
function runQuietly(command, args) {
  const result = spawnSync(command, args, { stdio: ["ignore", process.stderr, process.stderr] });
  if (result.error) {
    throw new Error(
      result.error.code === "ENOENT" ? `找不到命令：${command}` : result.error.message
    );
  }
  if (result.status !== 0) throw new Error(`${command} 退出码 ${result.status}`);
}

function extract(archive, destination, name) {
  if (name.endsWith(".zip")) {
    runQuietly("powershell", [
      "-NoProfile",
      "-ExecutionPolicy",
      "Bypass",
      "-Command",
      `Expand-Archive -LiteralPath '${archive.replace(/'/g, "''")}' -DestinationPath '${destination.replace(/'/g, "''")}' -Force`,
    ]);
  } else {
    runQuietly("tar", ["-xzf", archive, "-C", destination]);
  }
}

function acquireLock(lockPath) {
  try {
    fs.writeFileSync(lockPath, String(process.pid), { flag: "wx" });
    return true;
  } catch (error) {
    if (error.code !== "EEXIST") throw error;
    // 锁存在：持有者还活着就等，已死则清掉重抢。
    try {
      const pid = Number.parseInt(fs.readFileSync(lockPath, "utf8"), 10);
      process.kill(pid, 0);
      return false;
    } catch {
      try {
        fs.unlinkSync(lockPath);
      } catch {}
      return acquireLock(lockPath);
    }
  }
}

async function withRetry(operation) {
  let lastError;
  for (let attempt = 0; attempt < MAX_RETRIES; attempt += 1) {
    try {
      return await operation();
    } catch (error) {
      lastError = error;
      if (attempt < MAX_RETRIES - 1) {
        await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS * 2 ** attempt));
      }
    }
  }
  throw lastError;
}

async function fetchBinary(target) {
  const name = assetName();
  const directory = path.dirname(target);
  fs.mkdirSync(directory, { recursive: true });
  const lockPath = `${target}.lock`;

  if (!acquireLock(lockPath)) {
    for (let waited = 0; waited < 60; waited += 1) {
      if (fs.existsSync(target)) return;
      await new Promise((resolve) => setTimeout(resolve, 1_000));
    }
    throw new Error("等待其它进程下载超时");
  }

  try {
    if (fs.existsSync(target)) return;
    const version = packageVersion();
    log(`下载 v${version} 的 ${name} …`);
    const release = await withRetry(() =>
      httpsGet(`https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/tags/v${version}`)
    ).then(JSON.parse);
    const asset = (release.assets || []).find((item) => item.name === name);
    if (!asset) {
      const available = (release.assets || []).map((item) => item.name).join(", ") || "(空)";
      throw new Error(`release 里没有 ${name}；可用资产：${available}`);
    }

    const stamp = crypto.randomBytes(8).toString("hex");
    const archive = path.join(directory, `${stamp}-${name}`);
    const staging = path.join(directory, `${stamp}-extract`);
    fs.mkdirSync(staging, { recursive: true });
    await withRetry(() => downloadToFile(asset.browser_download_url, archive));
    extract(archive, staging, name);

    const extracted = path.join(staging, BINARY_NAME);
    if (!fs.existsSync(extracted)) {
      throw new Error(`归档里没有 ${BINARY_NAME}（解压目录：${staging}）`);
    }
    // 跨设备 move 会 EXDEV，退回复制 + 删除。
    try {
      fs.renameSync(extracted, target);
    } catch (error) {
      if (error.code !== "EXDEV") throw error;
      fs.copyFileSync(extracted, target);
    }
    if (process.platform !== "win32") fs.chmodSync(target, 0o755);
    fs.rmSync(staging, { recursive: true, force: true });
    try {
      fs.unlinkSync(archive);
    } catch {}
    log(`已安装到 ${target}`);
  } finally {
    try {
      fs.unlinkSync(lockPath);
    } catch {}
  }
}

async function resolveBinary() {
  const target = path.join(cacheDir(), BINARY_NAME);
  if (!fs.existsSync(target)) {
    try {
      await fetchBinary(target);
    } catch (error) {
      log(`从 GitHub Release 获取二进制失败：${error.message}`);
      for (const candidate of localFallbacks()) {
        if (fs.existsSync(candidate)) {
          log(`改用本地已构建的二进制：${candidate}`);
          return candidate;
        }
      }
      log("");
      log("请任选一种方式安装：");
      log("  1) 从源码构建：cd client && cargo build --release");
      log(`  2) 手动放置二进制到：${target}`);
      log(`  3) 从 release 页下载：https://github.com/${REPO_OWNER}/${REPO_NAME}/releases`);
      process.exit(1);
    }
  }
  return target;
}

async function main() {
  const binary = await resolveBinary();
  const child = spawn(binary, process.argv.slice(2), { stdio: "inherit", env: process.env });
  for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
    process.on(signal, () => {
      if (!child.killed) child.kill(signal);
    });
  }
  child.on("error", (error) => {
    log(`启动失败：${error.message}`);
    process.exit(1);
  });
  child.on("exit", (code, signal) => {
    process.exit(signal ? 128 + (os.constants.signals[signal] || 0) : (code ?? 0));
  });
}

main().catch((error) => {
  log(error.stack || String(error));
  process.exit(1);
});
