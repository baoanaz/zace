//! 远端同步层（CF-05 的 client 侧）：`resolve` → `batch-upload` → `deletions` → `checkpoint`。
//!
//! **与参考实现（notace）的关键差异**（zace 的 CF-05 已经定型，不能照搬 notace 的形态）：
//!
//! | 主题 | notace | zace（本模块） |
//! |---|---|---|
//! | 项目定位 | 只传 blob 名单，服务端自己认 | **先 `POST /api/projects/resolve`**（D-29 identityKey）拿 `projectId`（云端 MCP 的正解，见就绪度报告 §2） |
//! | blob 内容 | 明文 JSON（`content` 字段） | **base64**（CF-05：`contentB64`，JSON 二进制安全编码） |
//! | blob 名 | `sha256(path‖content)` 无分隔符 | **CF-02 `blob_hash`**（含 `0x00` 分隔符） |
//! | 请求体 | `{blobs:[{path,content}]}` | `{projectId, branch, commit, blobs:[{path,blobHash,contentB64}]}` |
//! | 响应 | `{blob_names[], skipped_blobs[]}` | `{accepted[], skipped[], report{...}}` |
//! | 鉴权 | Bearer（必填） | Bearer（**当前服务端未实现**，见就绪度报告 A1；带上为云端就绪） |
//! | 检索 | `POST /agents/codebase-retrieval`（带 blob 名单） | **`POST /api/query/search`**（带 `projectId` + 可选 `checkpointId`） |
//!
//! 分层超时（D-32）：upload 30s / search 15s / 其它 90s。

use std::collections::HashSet;
use std::path::Path;
use std::time::Duration;

use anyhow::{anyhow, bail, Context, Result};
use base64::Engine as _;
use serde::{Deserialize, Serialize};

use crate::blobref::blob_hash;

/// 每批上传的字节上限（CF-05：每批 ≤1MB）。
const MAX_BATCH_BYTES: usize = 1024 * 1024;
/// 分层超时（D-32）。
pub const UPLOAD_TIMEOUT: Duration = Duration::from_secs(30);
pub const SEARCH_TIMEOUT: Duration = Duration::from_secs(15);
pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(90);
/// 对外错误文本里的响应体截断（Module 05 §2.2：512 字节）。
const MAX_ERROR_SNIPPET_BYTES: usize = 512;

/// 一次上传的结果。
#[derive(Debug, Default, Clone)]
pub struct UploadOutcome {
    pub accepted: HashSet<String>,
    pub skipped_paths: HashSet<String>,
    pub batches: usize,
}

/// 远端客户端（一个服务端地址一个实例）。
pub struct RemoteClient {
    base_url: String,
    token: Option<String>,
    upload: reqwest::Client,
    search: reqwest::Client,
    general: reqwest::Client,
}

impl RemoteClient {
    pub fn new(base_url: &str, token: Option<String>) -> Result<Self> {
        let base_url = normalize_base_url(base_url)?;
        let token = token
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty());
        Ok(Self {
            upload: build_client(UPLOAD_TIMEOUT)?,
            search: build_client(SEARCH_TIMEOUT)?,
            general: build_client(DEFAULT_TIMEOUT)?,
            base_url,
            token,
        })
    }

    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    /// `POST /api/projects/resolve` → `projectId`（D-29 身份，幂等）。
    pub async fn resolve_project(&self, identity_key: &str, display_name: &str) -> Result<String> {
        let payload = serde_json::json!({
            "identityKey": identity_key,
            "displayName": display_name,
        });
        let response = self
            .request(
                self.general.post(self.url("/api/projects/resolve")),
                &payload,
            )
            .await?;
        let body: ResolveResponse = response.json().await.context("resolve 响应不是合法 JSON")?;
        if body.project_id.is_empty() {
            bail!("resolve 返回了空的 projectId");
        }
        Ok(body.project_id)
    }

    /// `POST /api/sync/batch-upload`：按 ≤1MB 分批；返回 accepted / skipped。
    pub async fn upload_files(
        &self,
        project_id: &str,
        files: &[(String, String)],
    ) -> Result<UploadOutcome> {
        let mut outcome = UploadOutcome::default();
        let mut start = 0usize;
        while start < files.len() {
            let mut end = start;
            let mut bytes = 0usize;
            while end < files.len() {
                let (path, content) = &files[end];
                // 批字节估算：base64 膨胀 4/3，另加 path 与 JSON 包装余量。
                let item_bytes = path.len() + content.len() * 4 / 3 + 128;
                if end > start && bytes + item_bytes > MAX_BATCH_BYTES {
                    break;
                }
                bytes += item_bytes;
                end += 1;
            }
            let batch = &files[start..end];
            let blobs: Vec<UploadBlob> = batch
                .iter()
                .map(|(path, content)| UploadBlob {
                    path: path.clone(),
                    blob_hash: blob_hash(path, content.as_bytes()),
                    content_b64: base64::engine::general_purpose::STANDARD
                        .encode(content.as_bytes()),
                })
                .collect();
            let payload = serde_json::json!({
                "projectId": project_id,
                "blobs": blobs,
            });
            let response = self
                .request(
                    self.upload.post(self.url("/api/sync/batch-upload")),
                    &payload,
                )
                .await?;
            let body: UploadResponse = response
                .json()
                .await
                .context("batch-upload 响应不是合法 JSON")?;
            outcome.accepted.extend(body.accepted);
            outcome.skipped_paths.extend(body.skipped);
            outcome.batches += 1;
            start = end;
        }
        Ok(outcome)
    }

    /// `POST /api/sync/deletions`：通知服务端删除路径（幂等）。
    pub async fn notify_deletions(&self, project_id: &str, paths: &[String]) -> Result<()> {
        if paths.is_empty() {
            return Ok(());
        }
        let payload = serde_json::json!({"projectId": project_id, "paths": paths});
        self.request(self.general.post(self.url("/api/sync/deletions")), &payload)
            .await?;
        Ok(())
    }

    /// `POST /api/sync/checkpoint`：提交 scope blob 集合换取 `checkpointId`。
    pub async fn create_checkpoint(&self, project_id: &str, hashes: &[String]) -> Result<String> {
        let payload = serde_json::json!({"projectId": project_id, "blobHashes": hashes});
        let response = self
            .request(
                self.general.post(self.url("/api/sync/checkpoint")),
                &payload,
            )
            .await?;
        let body: CheckpointResponse = response
            .json()
            .await
            .context("checkpoint 响应不是合法 JSON")?;
        Ok(body.checkpoint_id)
    }

    /// `POST /api/query/search`：返回服务端渲染的 Markdown（D-21：渲染在服务端）。
    pub async fn search(
        &self,
        project_id: &str,
        query: &str,
        max_tokens: i64,
        checkpoint_id: Option<&str>,
    ) -> Result<String> {
        let payload = serde_json::json!({
            "projectId": project_id,
            "query": query,
            "maxTokens": max_tokens,
            "checkpointId": checkpoint_id,
        });
        let response = self
            .request(self.search.post(self.url("/api/query/search")), &payload)
            .await?;
        let body: SearchResponse = response.json().await.context("search 响应不是合法 JSON")?;
        Ok(body.markdown)
    }

    /// `POST /api/query/ask`：Phase 2/3 均返回降级包（D-26），服务端已把说明写进 answer。
    pub async fn ask(
        &self,
        project_id: &str,
        question: &str,
        checkpoint_id: Option<&str>,
    ) -> Result<(String, String)> {
        let payload = serde_json::json!({
            "projectId": project_id,
            "question": question,
            "checkpointId": checkpoint_id,
        });
        let response = self
            .request(self.general.post(self.url("/api/query/ask")), &payload)
            .await?;
        let body: AskResponse = response.json().await.context("ask 响应不是合法 JSON")?;
        Ok((body.status, body.answer))
    }

    fn url(&self, path: &str) -> String {
        format!("{}{path}", self.base_url)
    }

    /// 统一发请求：带上 Bearer（若有）并映射可读错误（含响应体截断 + 脱敏）。
    async fn request(
        &self,
        builder: reqwest::RequestBuilder,
        payload: &serde_json::Value,
    ) -> Result<reqwest::Response> {
        let mut builder = builder.json(payload);
        if let Some(token) = &self.token {
            builder = builder.bearer_auth(token);
        }
        let response = builder
            .send()
            .await
            .map_err(|error| anyhow!("请求 {} 失败：{error}", self.base_url))?;
        let status = response.status();
        if status.is_success() {
            return Ok(response);
        }
        let body = response.text().await.unwrap_or_default();
        let snippet = redact(
            &truncate(&body, MAX_ERROR_SNIPPET_BYTES),
            self.token.as_deref(),
        );
        bail!("服务端返回 HTTP {status}：{snippet}");
    }
}

fn build_client(timeout: Duration) -> Result<reqwest::Client> {
    reqwest::Client::builder()
        .timeout(timeout)
        .user_agent(concat!("zace-client/", env!("CARGO_PKG_VERSION")))
        .build()
        .context("failed to build the HTTP client")
}

fn normalize_base_url(input: &str) -> Result<String> {
    let trimmed = input.trim().trim_end_matches('/');
    if trimmed.is_empty() {
        bail!("服务端地址不能为空");
    }
    if !(trimmed.starts_with("http://") || trimmed.starts_with("https://")) {
        bail!("服务端地址必须以 http:// 或 https:// 开头：{input}");
    }
    Ok(trimmed.to_string())
}

fn truncate(text: &str, limit: usize) -> String {
    if text.len() <= limit {
        return text.to_string();
    }
    let mut end = limit;
    while end > 0 && !text.is_char_boundary(end) {
        end -= 1;
    }
    format!("{}…（已截断）", &text[..end])
}

/// 错误文本脱敏：token 出现即替换（Module 05 §2.2 纪律）。
fn redact(text: &str, token: Option<&str>) -> String {
    match token {
        Some(token) if !token.is_empty() && text.contains(token) => text.replace(token, "***"),
        _ => text.to_string(),
    }
}

#[derive(Deserialize)]
struct ResolveResponse {
    #[serde(rename = "projectId")]
    project_id: String,
}

#[derive(Deserialize)]
struct UploadResponse {
    #[serde(default)]
    accepted: Vec<String>,
    #[serde(default)]
    skipped: Vec<String>,
}

#[derive(Deserialize)]
struct CheckpointResponse {
    #[serde(rename = "checkpointId")]
    checkpoint_id: String,
}

#[derive(Deserialize)]
struct SearchResponse {
    markdown: String,
}

#[derive(Deserialize)]
struct AskResponse {
    status: String,
    answer: String,
}

#[derive(Serialize)]
struct UploadBlob {
    path: String,
    #[serde(rename = "blobHash")]
    blob_hash: String,
    #[serde(rename = "contentB64")]
    content_b64: String,
}

/// 校验本地目录（MCP 工具入口的共同前置）。
pub fn validate_project_root(root: &str) -> Result<std::path::PathBuf> {
    if root.trim().is_empty() {
        bail!("project_root 不能为空");
    }
    if root.contains('\\') {
        bail!(
            "project_root 含反斜杠，必须是**正斜杠**绝对路径（服务端跑在 WSL/Linux，\
             Windows 路径如 C:\\... 在这里不存在）：收到 {root:?}"
        );
    }
    let path = Path::new(root);
    if !path.is_absolute() {
        bail!("project_root 必须是绝对路径：收到 {root:?}");
    }
    if !path.is_dir() {
        bail!("project_root 不是可读目录：{root}");
    }
    Ok(path.to_path_buf())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base_url_requires_scheme_and_drops_trailing_slash() {
        assert_eq!(
            normalize_base_url("https://zace.example.com/").unwrap(),
            "https://zace.example.com"
        );
        assert!(normalize_base_url("zace.example.com").is_err());
        assert!(normalize_base_url("   ").is_err());
    }

    #[test]
    fn error_text_is_truncated_and_token_redacted() {
        let long = "x".repeat(MAX_ERROR_SNIPPET_BYTES + 50);
        let snippet = truncate(&long, MAX_ERROR_SNIPPET_BYTES);
        assert!(snippet.len() < long.len());
        assert!(snippet.ends_with("…（已截断）"));

        let leaked = r#"{"error":{"message":"bad token sk-secret-123"}}"#;
        assert_eq!(
            redact(leaked, Some("sk-secret-123")),
            r#"{"error":{"message":"bad token ***"}}"#
        );
    }

    #[test]
    fn project_root_validation_rejects_relative_and_backslash_paths() {
        assert!(validate_project_root("relative/path").is_err());
        assert!(validate_project_root("C:\\Users\\x").is_err());
        let dir = tempfile::tempdir().expect("temp dir");
        assert!(validate_project_root(&dir.path().to_string_lossy()).is_ok());
    }
}
