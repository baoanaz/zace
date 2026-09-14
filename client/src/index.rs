//! 本地索引缓存与扫描（Module 05 §3.2 / D-27 懒同步的本地侧）。
//!
//! **缓存位置**：`~/.cache/zace/<projectId>/index.json`，**不进工作区**。
//! 这是对参考实现（notace 放 `.not-ace-tool/index.json` 于项目内）的**有意改进**（`Background/01` §7-1）：
//! 不污染工作区、不与 `.gitignore` 纠缠，且同一仓库的不同 checkout 天然隔离（projectId 由 D-29 决定，
//! 而 D-29 含相对路径）。
//!
//! **已验证缓存命中（verified cache hit）**：`mtime + size` 只是**快路径**，最终以
//! `blob_hash` 内容 hash 一致为准——防"mtime 不变内容变"与"touch 即误判"（`Background/01` §3.2）。
//!
//! **上传成功才入缓存**：文件的所有 blob 都被服务端接受才写索引；部分接受/被跳过 → 该文件不入缓存
//! （下次重传），并计入 `skipped_paths`（服务端裁决权，S4）。
//!
//! 忽略语义（D-28 / R42）在 [`crate::ignore`] 模块；本模块只做编排与对账。

use std::collections::{BTreeMap, HashSet};
use std::path::{Path, PathBuf};

use anyhow::{anyhow, Context, Result};
use serde::{Deserialize, Serialize};

use crate::blobref::{blob_hash, is_binary, sanitize_content, BINARY_RATIO, MAX_FILE_BYTES};
use crate::ignore::IgnoreRules;

/// 缓存 schema 版本；不匹配即整体作废（安全阀）。
const CACHE_VERSION: u32 = 1;

/// 二进制探测窗口（与 core `_is_binary` 的 `probe` 默认值一致：前 8 KB）。
const BINARY_PROBE_BYTES: usize = 8 * 1024;

/// 单个缓存文件上限（超过即视为损坏，直接作废重扫）。
const MAX_CACHE_BYTES: u64 = 256 * 1024 * 1024;

/// 一份文件的缓存条目。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FileEntry {
    pub mtime_secs: u64,
    pub mtime_nanos: u32,
    pub size: u64,
    pub blob_hash: String,
}

/// 本地索引（`~/.cache/zace/<projectId>/index.json`）。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IndexData {
    pub version: u32,
    /// 项目身份（D-29）：缓存自证属于哪个项目，换仓库即作废。
    pub project_id: String,
    /// 扫描配置指纹（阈值 + 忽略规则版本）；变更即作废。
    pub config_hash: String,
    pub entries: BTreeMap<String, FileEntry>,
}

impl Default for IndexData {
    fn default() -> Self {
        Self {
            version: CACHE_VERSION,
            project_id: String::new(),
            config_hash: String::new(),
            entries: BTreeMap::new(),
        }
    }
}

impl IndexData {
    /// 全部 blob_hash（稳定排序）——scope 的来源。
    pub fn all_blob_hashes(&self) -> Vec<String> {
        self.entries
            .values()
            .map(|entry| entry.blob_hash.clone())
            .collect()
    }
}

/// 一次扫描的结果（对账后）。
#[derive(Debug, Default)]
pub struct ScanResult {
    /// 需要上传的文件（相对路径 → 内容）。
    pub to_upload: Vec<UploadFile>,
    /// 本轮无需上传（内容 hash 命中缓存）的文件数。
    pub cached_files: usize,
    /// 扫描后的完整索引（尚未提交）。
    pub index: IndexData,
    /// 被忽略/跳过并**如实记录原因**的路径（R43：跳过必须带原因）。
    pub skipped: Vec<SkippedPath>,
    /// 相对于缓存被删除的路径（需要通知服务端）。
    pub deleted: Vec<String>,
}

/// 待上传文件。
#[derive(Debug, Clone)]
pub struct UploadFile {
    pub path: String,
    pub content: String,
    pub blob_hash: String,
}

/// 被跳过的路径与原因（R43）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SkippedPath {
    pub path: String,
    pub reason: String,
}

/// 本地索引管理器（一个仓库一个实例）。
pub struct IndexManager {
    root: PathBuf,
    project_id: String,
    cache_dir: PathBuf,
    rules: IgnoreRules,
    config_hash: String,
}

impl IndexManager {
    /// `cache_root` = 缓存根（通常是 `~/.cache/zace`）；实际写 `<cache_root>/<projectId>/`。
    pub fn new(root: PathBuf, project_id: String, cache_root: PathBuf) -> Self {
        let rules = IgnoreRules::load(&root);
        let config_hash = config_fingerprint(&rules);
        Self {
            cache_dir: cache_root.join(&project_id),
            root,
            project_id,
            rules,
            config_hash,
        }
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    /// 扫描 + 对账（**纯本地、不联网**）。
    ///
    /// 判定顺序与 core/service 一致：目录剪枝（忽略规则）→ 大小阈值 → 二进制阈值 → 内容。
    pub fn scan(&self) -> Result<ScanResult> {
        let previous = self.load()?;
        let previous_entries = previous.entries;
        let mut entries = BTreeMap::new();
        let mut to_upload = Vec::new();
        let mut cached_files = 0usize;
        let mut skipped = Vec::new();

        // 忽略语义（D-28 / TASK-097）：第 0 层白名单（强制包含）> `.zaceignore` > `.gitignore`
        // > 内置目录剪枝。前两层的遍历由 `walker()` 完成；第 0 层由 `allowlist_walk()` 追加，
        // 因此这里迭代两者的**并集**，并用 `seen` 按路径去重（既未被忽略又命中白名单的文件
        // 会同时出现在两个 walker 里）。
        let mut seen: HashSet<String> = HashSet::new();
        for entry in self.rules.walk_union() {
            let entry = match entry {
                Ok(entry) => entry,
                Err(_) => continue,
            };
            if !entry.file_type().is_some_and(|kind| kind.is_file()) {
                continue;
            }
            let path = entry.path();
            let Some(relative) = relative_path(&self.root, path) else {
                continue;
            };
            if !seen.insert(relative.clone()) {
                continue;
            }
            let metadata = match entry.metadata() {
                Ok(metadata) => metadata,
                Err(_) => {
                    skipped.push(SkippedPath {
                        path: relative,
                        reason: "unreadable_metadata".to_string(),
                    });
                    continue;
                }
            };
            let size = metadata.len();
            if size > MAX_FILE_BYTES as u64 {
                skipped.push(SkippedPath {
                    path: relative,
                    reason: format!("oversize:{size}"),
                });
                continue;
            }
            let raw = match std::fs::read(path) {
                Ok(raw) => raw,
                Err(_) => {
                    skipped.push(SkippedPath {
                        path: relative,
                        reason: "unreadable".to_string(),
                    });
                    continue;
                }
            };
            if is_binary(&raw, BINARY_PROBE_BYTES, BINARY_RATIO) {
                skipped.push(SkippedPath {
                    path: relative,
                    reason: "binary".to_string(),
                });
                continue;
            }
            let (mtime_secs, mtime_nanos) = mtime_of(&metadata);
            let content = sanitize_content(&String::from_utf8_lossy(&raw));
            let hash = blob_hash(&relative, content.as_bytes());
            let file_entry = FileEntry {
                mtime_secs,
                mtime_nanos,
                size,
                blob_hash: hash.clone(),
            };

            // 已验证缓存命中：mtime+size 快路径 ≈ 且 **内容 hash 一致**才算命中。
            let verified_hit = previous_entries
                .get(&relative)
                .is_some_and(|cached| cached.blob_hash == hash);
            if verified_hit {
                cached_files += 1;
            } else {
                to_upload.push(UploadFile {
                    path: relative.clone(),
                    content,
                    blob_hash: hash,
                });
            }
            entries.insert(relative, file_entry);
        }

        let deleted: Vec<String> = previous_entries
            .keys()
            .filter(|path| !entries.contains_key(*path))
            .cloned()
            .collect();

        Ok(ScanResult {
            to_upload,
            cached_files,
            index: IndexData {
                version: CACHE_VERSION,
                project_id: self.project_id.clone(),
                config_hash: self.config_hash.clone(),
                entries,
            },
            skipped,
            deleted,
        })
    }

    /// 应用服务端裁决：**只有全部 blob 被接受且未被跳过**的文件才保留在索引里。
    ///
    /// `accepted` = 服务端返回的 `accepted` blobHash 列表；`skipped_paths` = `skipped` 路径列表。
    pub fn apply_upload_outcome(
        index: &mut IndexData,
        uploaded: &[UploadFile],
        accepted: &HashSet<String>,
        skipped_paths: &HashSet<String>,
    ) -> Vec<SkippedPath> {
        let mut rejected = Vec::new();
        for file in uploaded {
            let accepted_ok = accepted.contains(&file.blob_hash);
            // 服务端按"path"裁决；blob 名里的 path 与我们上传的 path 一致。
            let server_skipped = skipped_paths.contains(&file.path);
            if !accepted_ok || server_skipped {
                index.entries.remove(&file.path);
                rejected.push(SkippedPath {
                    path: file.path.clone(),
                    reason: if server_skipped {
                        "server_skipped".to_string()
                    } else {
                        "not_accepted".to_string()
                    },
                });
            }
        }
        rejected
    }

    /// 从缓存中"遗忘"服务端报告为 stale 的路径（checkpoint 自愈路径 2）。
    pub fn forget_paths(&self, paths: &[String]) -> Result<usize> {
        if paths.is_empty() {
            return Ok(0);
        }
        let mut index = self.load()?;
        let before = index.entries.len();
        for path in paths {
            index.entries.remove(path);
        }
        let removed = before - index.entries.len();
        if removed != 0 {
            self.commit(&index)?;
        }
        Ok(removed)
    }

    /// 读缓存（缺失/损坏/版本或指纹不符 → 空索引）。
    pub fn load(&self) -> Result<IndexData> {
        let path = self.cache_file();
        let Ok(metadata) = std::fs::metadata(&path) else {
            return Ok(IndexData::default());
        };
        if !metadata.is_file() || metadata.len() > MAX_CACHE_BYTES {
            return Ok(IndexData::default());
        }
        let Ok(bytes) = std::fs::read(&path) else {
            return Ok(IndexData::default());
        };
        let Ok(data) = serde_json::from_slice::<IndexData>(&bytes) else {
            return Ok(IndexData::default());
        };
        if data.version == CACHE_VERSION
            && data.config_hash == self.config_hash
            && data.project_id == self.project_id
        {
            Ok(data)
        } else {
            Ok(IndexData::default())
        }
    }

    /// 原子提交（tmp + rename；Windows 先删后改名）。
    pub fn commit(&self, index: &IndexData) -> Result<()> {
        std::fs::create_dir_all(&self.cache_dir).with_context(|| {
            format!(
                "failed to create cache directory: {}",
                self.cache_dir.display()
            )
        })?;
        let bytes = serde_json::to_vec(index).context("failed to serialize index cache")?;
        let target = self.cache_file();
        let temporary = target.with_extension("json.tmp");
        std::fs::write(&temporary, bytes)
            .with_context(|| format!("failed to write temporary cache: {}", temporary.display()))?;
        #[cfg(windows)]
        if target.exists() {
            std::fs::remove_file(&target)
                .with_context(|| format!("failed to replace cache: {}", target.display()))?;
        }
        std::fs::rename(&temporary, &target)
            .with_context(|| format!("failed to commit cache: {}", target.display()))?;
        Ok(())
    }

    fn cache_file(&self) -> PathBuf {
        self.cache_dir.join("index.json")
    }
}

/// 扫描配置指纹：阈值 + 忽略规则内容。任一变化 → 缓存作废（避免脏索引）。
fn config_fingerprint(rules: &IgnoreRules) -> String {
    let material = format!(
        "v{CACHE_VERSION}:{MAX_FILE_BYTES}:{BINARY_RATIO}:{BINARY_PROBE_BYTES}:{}",
        rules.fingerprint()
    );
    blob_hash("zace-client-config", material.as_bytes())
}

fn relative_path(root: &Path, path: &Path) -> Option<String> {
    let relative = path.strip_prefix(root).ok()?;
    Some(relative.to_string_lossy().replace('\\', "/"))
}

fn mtime_of(metadata: &std::fs::Metadata) -> (u64, u32) {
    let modified = match metadata.modified() {
        Ok(modified) => modified,
        Err(_) => return (0, 0),
    };
    match modified.duration_since(std::time::UNIX_EPOCH) {
        Ok(duration) => (duration.as_secs(), duration.subsec_nanos()),
        Err(error) => {
            let duration = error.duration();
            (0, duration.subsec_nanos())
        }
    }
}

/// 便捷入口：把 `ScanResult` 里待上传文件转成 `(path, content)` 列表（上传层用）。
pub fn upload_payload(files: &[UploadFile]) -> Vec<(String, String)> {
    files
        .iter()
        .map(|file| (file.path.clone(), file.content.clone()))
        .collect()
}

/// 空扫描防御：索引为空时报可读错误（与 MCP 工具的错误面一致）。
pub fn require_non_empty(index: &IndexData) -> Result<()> {
    if index.entries.is_empty() {
        return Err(anyhow!(
            "扫描后没有任何可上传的文件（可能全部被忽略规则/大小/二进制阈值跳过）"
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn manager(root: &Path, cache: &Path) -> IndexManager {
        IndexManager::new(
            root.to_path_buf(),
            "testproject0000".to_string(),
            cache.to_path_buf(),
        )
    }

    #[test]
    fn scan_skips_git_directory_and_reports_reasons() -> Result<()> {
        let project = tempfile::tempdir()?;
        let cache = tempfile::tempdir()?;
        fs::create_dir_all(project.path().join(".git"))?;
        fs::write(project.path().join(".git/config"), "metadata")?;
        fs::write(project.path().join("included.rs"), "pub fn included() {}")?;

        let scan = manager(project.path(), cache.path()).scan()?;

        assert!(scan.index.entries.contains_key("included.rs"));
        assert!(!scan.index.entries.contains_key(".git/config"));
        assert_eq!(scan.to_upload.len(), 1);
        Ok(())
    }

    #[test]
    fn oversize_and_binary_files_are_skipped_with_reasons() -> Result<()> {
        let project = tempfile::tempdir()?;
        let cache = tempfile::tempdir()?;
        fs::write(
            project.path().join("big.txt"),
            vec![b'a'; MAX_FILE_BYTES + 1],
        )?;
        fs::write(project.path().join("blob.bin"), [0u8, 1, 2, 3, 4])?;
        fs::write(project.path().join("ok.txt"), "fine")?;

        let scan = manager(project.path(), cache.path()).scan()?;
        let reasons: BTreeMap<&str, &str> = scan
            .skipped
            .iter()
            .map(|item| (item.path.as_str(), item.reason.as_str()))
            .collect();

        assert!(reasons["big.txt"].starts_with("oversize:"));
        assert_eq!(reasons["blob.bin"], "binary");
        assert!(scan.index.entries.contains_key("ok.txt"));
        Ok(())
    }

    #[test]
    fn verified_cache_hit_avoids_reupload() -> Result<()> {
        let project = tempfile::tempdir()?;
        let cache = tempfile::tempdir()?;
        fs::write(project.path().join("a.txt"), "same")?;
        let manager = manager(project.path(), cache.path());

        let first = manager.scan()?;
        assert_eq!(first.to_upload.len(), 1);
        manager.commit(&first.index)?;

        let second = manager.scan()?;
        assert_eq!(second.to_upload.len(), 0);
        assert_eq!(second.cached_files, 1);
        Ok(())
    }

    #[test]
    fn changed_content_is_detected_even_when_size_is_equal() -> Result<()> {
        let project = tempfile::tempdir()?;
        let cache = tempfile::tempdir()?;
        let file = project.path().join("a.txt");
        fs::write(&file, "aaaa")?;
        let manager = manager(project.path(), cache.path());
        let first = manager.scan()?;
        manager.commit(&first.index)?;

        // 同长度不同内容（mtime+size 快路径会误判，content hash 不会）
        fs::write(&file, "bbbb")?;
        let second = manager.scan()?;

        assert_eq!(second.to_upload.len(), 1);
        assert_eq!(second.cached_files, 0);
        Ok(())
    }

    #[test]
    fn deleted_file_is_reported_for_server_notification() -> Result<()> {
        let project = tempfile::tempdir()?;
        let cache = tempfile::tempdir()?;
        let file = project.path().join("gone.txt");
        fs::write(&file, "bye")?;
        let manager = manager(project.path(), cache.path());
        let first = manager.scan()?;
        manager.commit(&first.index)?;

        fs::remove_file(&file)?;
        let second = manager.scan()?;

        assert_eq!(second.deleted, vec!["gone.txt".to_string()]);
        Ok(())
    }

    #[test]
    fn partial_upload_does_not_persist_the_file() -> Result<()> {
        let project = tempfile::tempdir()?;
        let cache = tempfile::tempdir()?;
        fs::write(project.path().join("a.txt"), "payload")?;
        let manager = manager(project.path(), cache.path());
        let mut scan = manager.scan()?;

        let rejected = IndexManager::apply_upload_outcome(
            &mut scan.index,
            &scan.to_upload,
            &HashSet::new(),
            &HashSet::new(),
        );

        assert_eq!(rejected.len(), 1);
        assert!(scan.index.entries.is_empty());
        Ok(())
    }

    #[test]
    fn server_skipped_path_is_not_persisted() -> Result<()> {
        let project = tempfile::tempdir()?;
        let cache = tempfile::tempdir()?;
        fs::write(project.path().join("a.txt"), "payload")?;
        let manager = manager(project.path(), cache.path());
        let mut scan = manager.scan()?;
        let accepted: HashSet<String> = vec![scan.to_upload[0].blob_hash.clone()]
            .into_iter()
            .collect();
        let skipped: HashSet<String> = vec!["a.txt".to_string()].into_iter().collect();

        let rejected = IndexManager::apply_upload_outcome(
            &mut scan.index,
            &scan.to_upload,
            &accepted,
            &skipped,
        );

        assert_eq!(rejected.len(), 1);
        assert_eq!(rejected[0].reason, "server_skipped");
        assert!(scan.index.entries.is_empty());
        Ok(())
    }

    #[test]
    fn corrupt_or_foreign_cache_loads_as_empty() -> Result<()> {
        let project = tempfile::tempdir()?;
        let cache = tempfile::tempdir()?;
        fs::write(project.path().join("a.txt"), "x")?;
        let manager = manager(project.path(), cache.path());
        let scan = manager.scan()?;
        manager.commit(&scan.index)?;

        // 换 project_id → 缓存自证不符 → 作废
        let other = IndexManager::new(
            project.path().to_path_buf(),
            "otherproject0000".to_string(),
            cache.path().to_path_buf(),
        );
        assert!(other.load()?.entries.is_empty());
        Ok(())
    }
}
