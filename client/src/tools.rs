//! 工具层：两个 CF-06 工具（`search_context` / `ask_project`）+ 会话编排
//! （身份 → resolve → 扫描对账 → 上传 → checkpoint → 检索）。
//!
//! **参数名与 CF-06 一致**：编辑器侧仍传 `project_root`（本地绝对路径）。云端语义下
//! `project_root` 不用于服务端定位，而是**客户端**用来算 D-29 身份（就绪度报告 §2 方案乙：
//! 零契约变更）。
//!
//! `max_tokens`（TASK-MCP-BUDGET，2026-09-16）：**不再出现在 `inputSchema` 里**——
//! 包大小由服务端按证据密度决定，不由调用方猜；结构体仍保留该字段以便接收旧版编辑器
//! 发来的值（不报错），但不再向 AI 声明。
//!
//! 会话状态（进程内 `project_root → SessionState`，Module 05 §3.6）：缓存最后一次的
//! `projectId` / `scope` / `checkpointId`，避免每次 tool call 都重建 checkpoint。

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use serde_json::{json, Value};

use crate::identity::repo_identity;
use crate::index::{require_non_empty, IndexManager};
use crate::remote::{validate_project_root, CallContext, RemoteClient};

/// `max_tokens` 的可接受上限（服务端 `MAX_MAX_TOKENS`，运行时兜底）。
///
/// TASK-MCP-BUDGET：该参数已从 `inputSchema` 移除（不再向 AI 声明），但**仍可接收**——
/// 故校验与默认值保留，保证旧编辑器发来的值不会变成参数错误。
pub const MAX_TOKENS_ASK: i64 = 20_000;
/// 未收到 `max_tokens` 时发给服务端的值。
///
/// 实际很可能被服务端忽略（service 以自己的默认档位为准，Fast 14K / Deep 16K）；
/// 这里保留 10000 只为与旧版服务端（仍读该字段）兼容，不参与本地的预算决策。
pub const DEFAULT_MAX_TOKENS: i64 = 10_000;
/// 查询长度上限（与 service 侧 `MAX_QUERY_CHARS` 同口径）。
///
/// TASK-MCP-BUDGET：2000→8000（服务端已放宽到 8000）。此前客户端 8000 / 服务端 2000，
/// 2000～8000 字符的查询会在服务端被 400 拒，而调用方自认为合法。
const MAX_QUERY_CHARS: usize = 8_000;

/// 工具层错误（→ 协议层的三分类，Module 05 §2.2）。
#[derive(Debug)]
pub enum ToolError {
    /// 参数错误 → JSON-RPC `-32602`。
    InvalidArguments(String),
    /// 未知工具 → JSON-RPC `-32602`。
    UnknownTool(String),
    /// 工具执行错误 → 正常响应 + `isError: true`（agent 可读原因并决策重试）。
    Failed(String),
}

impl ToolError {
    fn invalid(message: impl Into<String>) -> Self {
        Self::InvalidArguments(message.into())
    }
}

/// 两个工具的 JSON Schema（CF-06；`additionalProperties: false`）。
///
/// TASK-MCP-BUDGET：不声明 `max_tokens`——包大小是服务端按证据密度决定的内部量，
/// 让 AI 去猜它只会猜小（实测把长函数截断成“签名 + 前 15 行”）。运行时仍接受该字段。
pub fn definitions() -> Value {
    json!([
        {
            "name": "search_context",
            "description": "在当前项目工作区检索与问题最相关的上下文（代码/调用链/文档证据包）。\
                适合'XX 在哪里实现'这类需要跨文件定位的问题；已知精确标识符的全量引用请用 grep，\
                已知文件请直接 read。调用链（Flow 节）只给一跳且遇分叉即停，想穷举调用方请用 grep。\
                返回 ContextPack 的 Markdown 渲染（含证据 id、行号与 Missing Evidence）。",
            "inputSchema": {
                "type": "object",
                "additionalProperties": false,
                "required": ["query", "project_root"],
                "properties": {
                    "query": {"type": "string", "minLength": 1, "description": "自然语言或符号混合查询，中英均可"},
                    "project_root": {"type": "string", "minLength": 1, "description": "项目根绝对路径，正斜杠"}
                }
            }
        },
        {
            "name": "ask_project",
            "description": "就当前项目提出调查性问题，返回基于证据包（含代码与设计文档）的带引用回答，并在证据不足时\
                给出缺口说明与改问建议。需要直接结论（'为什么/如何设计/实现与设计是否一致'）时用它；\
                只想要原始上下文时用 search_context。**长函数/内部流程类问题请改用 search_context**：\
                超长符号的证据块会降级为'签名 + 前 15 行'，容易恰好丢掉你要问的正文——\
                先用 search_context 拿到完整正文自己读。",
            "inputSchema": {
                "type": "object",
                "additionalProperties": false,
                "required": ["question", "project_root"],
                "properties": {
                    "question": {"type": "string", "minLength": 1, "description": "需要项目级回答的问题，中英均可"},
                    "project_root": {"type": "string", "minLength": 1, "description": "项目根绝对路径，正斜杠"}
                }
            }
        }
    ])
}

#[derive(Debug, Default, Clone)]
struct SessionState {
    checkpoint_id: Option<String>,
    scope: Option<Arc<Vec<String>>>,
}

/// 工具层（一个进程一个实例；服务端地址 + 可选 token）。
pub struct ToolLayer {
    remote: RemoteClient,
    cache_root: PathBuf,
    sessions: Mutex<HashMap<String, SessionState>>,
}

impl ToolLayer {
    pub fn new(remote: RemoteClient, cache_root: PathBuf) -> Self {
        Self {
            remote,
            cache_root,
            sessions: Mutex::new(HashMap::new()),
        }
    }

    /// 执行一个工具调用。
    ///
    /// **一次调用一个 callId**（TASK-099 §B-2）：进入这里先开一个 :class:`CallContext`，
    /// 再派生一个带它的 ``RemoteClient``——该次调用的所有 HTTP 请求（resolve / 上传 /
    /// 删除通知 / checkpoint / 检索）因此共享同一个 ``X-Request-Id``。服务端靠这个值把
    /// "N 次初始化 + 1 次检索"归成一次调用（卡内 §B-1 的问题）。
    ///
    /// 并发安全：callId 是**每次调用局部**的值，不存进 ``self``，因此两个 tool call 并发
    /// 执行时不会把彼此的 id 串起来（会话缓存 ``self.sessions`` 是跨调用状态，与它无关）。
    pub async fn execute(&self, tool_name: &str, arguments: Value) -> Result<String, ToolError> {
        let remote = self.remote.for_call(CallContext::new());
        // 诊断走 stderr（stdout 只出 JSON-RPC 帧）：用户/日志据此把客户端侧与
        // 服务端 ``GET /api/calls/{callId}`` 对上（TASK-099 §G 要抓的就是它）。
        eprintln!("zace-client: callId={} tool={tool_name}", remote.call_id());
        match tool_name {
            "search_context" => {
                let args: SearchArguments = decode(tool_name, arguments)?;
                require_query(&args.query, "query")?;
                require_max_tokens(args.max_tokens, MAX_TOKENS_ASK, "max_tokens")?;
                self.search(
                    &remote,
                    &args.project_root,
                    args.query.trim(),
                    args.max_tokens.unwrap_or(DEFAULT_MAX_TOKENS),
                )
                .await
            }
            "ask_project" => {
                let args: AskArguments = decode(tool_name, arguments)?;
                require_query(&args.question, "question")?;
                require_max_tokens(args.max_tokens, MAX_TOKENS_ASK, "max_tokens")?;
                self.ask(
                    &remote,
                    &args.project_root,
                    args.question.trim(),
                    args.max_tokens.unwrap_or(DEFAULT_MAX_TOKENS),
                )
                .await
            }
            other => Err(ToolError::UnknownTool(other.to_string())),
        }
    }

    async fn search(
        &self,
        remote: &RemoteClient,
        project_root: &str,
        query: &str,
        max_tokens: i64,
    ) -> Result<String, ToolError> {
        let (project_id, checkpoint_id) = self.sync_project(remote, project_root).await?;
        remote
            .search(&project_id, query, max_tokens, checkpoint_id.as_deref())
            .await
            .map_err(|error| ToolError::Failed(format!("检索失败：{error:#}")))
    }

    async fn ask(
        &self,
        remote: &RemoteClient,
        project_root: &str,
        question: &str,
        _max_tokens: i64,
    ) -> Result<String, ToolError> {
        let (project_id, checkpoint_id) = self.sync_project(remote, project_root).await?;
        remote
            .ask(&project_id, question, checkpoint_id.as_deref())
            .await
            .map_err(|error| ToolError::Failed(format!("提问失败：{error:#}")))
    }

    /// 懒同步编排（D-27）：每次 tool call 保证工作区新鲜，返回 `(projectId, checkpointId)`。
    ///
    /// 时序（Module 05 §3.3 + 就绪度报告 §5）：
    /// ① 算身份 → ② resolve → ③ 扫描对账 → ④ 上传变更 → ⑤ 通知删除 → ⑥ 建 checkpoint。
    ///
    /// ``remote`` 是**本次调用**的客户端（带该次调用的 callId，TASK-099 §B-2）：
    /// 上面的六步全走它，因此服务端那 N 条 ``index_runs`` 与随后的 ``query_audit`` 共享同一 id。
    async fn sync_project(
        &self,
        remote: &RemoteClient,
        project_root: &str,
    ) -> Result<(String, Option<String>), ToolError> {
        let root = validate_project_root(project_root)
            .map_err(|error| ToolError::invalid(error.to_string()))?;
        let identity = repo_identity(&root);

        let project_id = remote
            .resolve_project(&identity.identity_key, &identity.display_name)
            .await
            .map_err(|error| {
                ToolError::Failed(format!(
                    "无法在服务端定位项目（identityKey={}）：{error:#}",
                    identity.identity_key
                ))
            })?;

        // TASK-100：把服务端端点传给缓存（缓存目录按端点分片，且字段自证）。
        let manager = IndexManager::new(
            root.clone(),
            project_id.clone(),
            self.cache_root.clone(),
            remote.base_url(),
        );
        let mut scan = manager
            .scan()
            .map_err(|error| ToolError::Failed(format!("本地扫描失败：{error:#}")))?;
        require_non_empty(&scan.index).map_err(|error| ToolError::Failed(error.to_string()))?;

        // 上传变更（有变更才发请求）。
        if !scan.to_upload.is_empty() {
            let payload = crate::index::upload_payload(&scan.to_upload);
            let outcome = remote
                .upload_files(&project_id, &payload)
                .await
                .map_err(|error| ToolError::Failed(format!("上传失败：{error:#}")))?;
            let rejected = IndexManager::apply_upload_outcome(
                &mut scan.index,
                &scan.to_upload,
                &outcome.accepted,
                &outcome.skipped_paths,
            );
            if !rejected.is_empty() {
                eprintln!(
                    "zace-client: 服务端跳过 {} 个文件（示例：{:?}）",
                    rejected.len(),
                    rejected
                        .iter()
                        .take(3)
                        .map(|item| &item.path)
                        .collect::<Vec<_>>()
                );
            }
        }

        // 通知删除（幂等）。
        if !scan.deleted.is_empty() {
            remote
                .notify_deletions(&project_id, &scan.deleted)
                .await
                .map_err(|error| ToolError::Failed(format!("删除通知失败：{error:#}")))?;
        }

        // 提交缓存（只有成功上传的文件才在里面）+ 更新 scope/checkpoint。
        manager
            .commit(&scan.index)
            .map_err(|error| ToolError::Failed(format!("缓存写入失败：{error:#}")))?;

        let scope: Arc<Vec<String>> = Arc::new(scan.index.all_blob_hashes());
        let previous = self.session(&project_id);
        let checkpoint_id = match previous.checkpoint_id.clone() {
            Some(id) if previous.scope.as_ref() == Some(&scope) => Some(id),
            _ => match remote.create_checkpoint(&project_id, &scope).await {
                Ok(id) => Some(id),
                Err(error) => {
                    // checkpoint 是传输优化，失败不阻断检索（降级为服务端不用 checkpoint）。
                    eprintln!("zace-client: checkpoint 创建失败（不影响检索）：{error:#}");
                    None
                }
            },
        };
        self.store_session(
            &project_id,
            SessionState {
                checkpoint_id: checkpoint_id.clone(),
                scope: Some(scope),
            },
        );
        Ok((project_id, checkpoint_id))
    }

    fn session(&self, project_id: &str) -> SessionState {
        self.sessions
            .lock()
            .ok()
            .and_then(|sessions| sessions.get(project_id).cloned())
            .unwrap_or_default()
    }

    fn store_session(&self, project_id: &str, state: SessionState) {
        if let Ok(mut sessions) = self.sessions.lock() {
            sessions.insert(project_id.to_string(), state);
        }
    }
}

fn decode<T: serde::de::DeserializeOwned>(
    tool_name: &str,
    arguments: Value,
) -> Result<T, ToolError> {
    serde_json::from_value(arguments)
        .map_err(|error| ToolError::invalid(format!("{tool_name} 的参数不合法：{error}")))
}

fn require_query(raw: &str, field: &str) -> Result<(), ToolError> {
    if raw.trim().is_empty() {
        return Err(ToolError::invalid(format!(
            "{field} 不能为空或纯空白：请给出自然语言或符号混合的问题（中英均可）。"
        )));
    }
    if raw.chars().count() > MAX_QUERY_CHARS {
        return Err(ToolError::invalid(format!(
            "{field} 过长（{} 字符，上限 {MAX_QUERY_CHARS}）：请把问题聚焦成一句话。",
            raw.chars().count()
        )));
    }
    Ok(())
}

fn require_max_tokens(value: Option<i64>, limit: i64, field: &str) -> Result<(), ToolError> {
    if let Some(value) = value {
        if value < 1 {
            return Err(ToolError::invalid(format!(
                "{field} 必须 ≥ 1，收到 {value}"
            )));
        }
        if value > limit {
            return Err(ToolError::invalid(format!(
                "{field}={value} 超出上传上限 {limit}：请调小。"
            )));
        }
    }
    Ok(())
}

#[derive(serde::Deserialize)]
struct SearchArguments {
    query: String,
    project_root: String,
    #[serde(default)]
    max_tokens: Option<i64>,
}

#[derive(serde::Deserialize)]
struct AskArguments {
    question: String,
    project_root: String,
    #[serde(default)]
    max_tokens: Option<i64>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn definitions_match_cf06_required_fields_and_limits() {
        let tools = definitions();
        let array = tools.as_array().expect("array");
        assert_eq!(array.len(), 2);
        assert_eq!(array[0]["name"], "search_context");
        assert_eq!(array[1]["name"], "ask_project");
        for tool in array {
            assert_eq!(tool["inputSchema"]["additionalProperties"], false);
            let required = tool["inputSchema"]["required"]
                .as_array()
                .expect("required");
            assert_eq!(required.len(), 2);
            // TASK-MCP-BUDGET：max_tokens 不再对 AI 声明（服务端按证据密度决定包大小）
            let props = tool["inputSchema"]["properties"]
                .as_object()
                .expect("properties");
            assert!(
                !props.contains_key("max_tokens"),
                "{} 不应再声明 max_tokens：{:?}",
                tool["name"],
                props.keys().collect::<Vec<_>>()
            );
            assert_eq!(props.len(), 2);
        }
    }

    #[test]
    fn query_validation_rejects_blank_and_oversized() {
        assert!(require_query("   ", "query").is_err());
        assert!(require_query("ok", "query").is_ok());
        let long = "x".repeat(MAX_QUERY_CHARS + 1);
        assert!(require_query(&long, "query").is_err());
    }

    #[test]
    fn max_tokens_validation_still_accepts_legacy_callers() {
        // TASK-MCP-BUDGET：参数已从 schema 移除，但旧编辑器仍可能发送——不得变成参数错误。
        assert!(require_max_tokens(Some(0), MAX_TOKENS_ASK, "max_tokens").is_err());
        assert!(
            require_max_tokens(Some(MAX_TOKENS_ASK + 1), MAX_TOKENS_ASK, "max_tokens").is_err()
        );
        assert!(
            require_max_tokens(Some(MAX_TOKENS_ASK), MAX_TOKENS_ASK, "max_tokens").is_ok()
        );
        assert!(require_max_tokens(None, MAX_TOKENS_ASK, "max_tokens").is_ok());
        // 旧版常用的 10000 仍放行（现在两面共用一个上限）
        assert!(require_max_tokens(Some(DEFAULT_MAX_TOKENS), MAX_TOKENS_ASK, "max_tokens").is_ok());
    }

    #[tokio::test]
    async fn unknown_tool_and_bad_arguments_are_argument_errors() {
        let layer = ToolLayer::new(
            RemoteClient::new("http://127.0.0.1:9", None).expect("client"),
            std::env::temp_dir(),
        );
        assert!(matches!(
            layer.execute("nope", json!({})).await,
            Err(ToolError::UnknownTool(_))
        ));
        assert!(matches!(
            layer.execute("search_context", json!({"query": "x"})).await,
            Err(ToolError::InvalidArguments(_))
        ));
        assert!(matches!(
            layer
                .execute(
                    "search_context",
                    json!({"query": "  ", "project_root": "/tmp"})
                )
                .await,
            Err(ToolError::InvalidArguments(_))
        ));
    }
}
