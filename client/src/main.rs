//! `zace-client` 命令行入口（MCP stdio server；由编辑器作为子进程拉起）。
//!
//! ```bash
//! # 编辑器配置（Claude Code / Codex 等 stdio harness）：
//! ZACE_BASE_URL=http://127.0.0.1:8787 zace-client
//! # 云端：ZACE_BASE_URL=https://zace.example.com ZACE_API_TOKEN=<token>
//! ```

use clap::Parser;

/// zace MCP stdio 客户端（本地扫描/哈希/上传 → 远端 zace-service 检索）。
#[derive(Parser, Debug)]
#[command(name = "zace-client", version, about)]
struct Args {
    /// zace-service 基础地址。
    #[arg(long, env = "ZACE_BASE_URL", value_name = "URL")]
    base_url: String,

    /// 远端 API token（M2c 鉴权；当前服务端未启用，可省略）。
    #[arg(
        long,
        env = "ZACE_API_TOKEN",
        value_name = "TOKEN",
        hide_env_values = true
    )]
    token: Option<String>,

    /// 本地缓存根（默认 `~/.cache/zace`）。
    #[arg(long, env = "ZACE_CLIENT_CACHE", value_name = "DIR")]
    cache_root: Option<std::path::PathBuf>,
}

#[tokio::main]
async fn main() {
    let args = Args::parse();
    let cache_root = args
        .cache_root
        .unwrap_or_else(zace_client::default_cache_root);
    if let Err(error) = zace_client::run(&args.base_url, args.token, cache_root).await {
        // stdout 只出 JSON-RPC 帧；诊断一律 stderr。
        eprintln!("zace-client: {error:#}");
        std::process::exit(1);
    }
}
