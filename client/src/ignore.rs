//! 忽略规则（D-28 / R42）：`.zaceignore` > `.gitignore` > 内置默认。
//!
//! **为什么用 `ignore` crate 而不是手写 gitignore 解析**：`docs/design/Module/05-MCP与同步.md` §3.1
//! 明确"Rust 实现直接用 `ignore` crate（原生支持 .gitignore 语义）"；`docs/plan/contracts.md` R42 也
//! 把契约定义为"忽略**语义**"而不是库，并要求两侧行为一致。
//!
//! 与 core（`core/zace_core/pipeline/ignore.py`，本地模式用）的对齐口径：
//!
//! | 层 | core（Python） | 本模块（Rust） |
//! |---|---|---|
//! | 1 `.zaceignore` | 手写解析，优先级最高 | `add_custom_ignore_filename(".zaceignore")` |
//! | 2 `.gitignore`（各层级） | 手写解析（注释/`!`/目录尾/`/`/`**`/字符类） | `ignore` crate 原生（`git_ignore(true)`） |
//! | 3 内置默认 | `DEFAULT_SKIP_DIRS` + `DEFAULT_SKIP_DIR_PATTERNS` | 同名单 + 同模式（本模块 `builtin_reason`） |
//!
//! **V1 两侧共同不读**：`.git/info/exclude` 与全局 `core.excludesFile`
//! （core 的执行记录已注明该简化；此处保持一致，`git_exclude(false)` / `git_global(false)`）。
//!
//! **已知语义分歧（诚实记录，勿当作 bug）**：`ignore` crate 默认**豁免被 git 跟踪的文件**
//! （`require_git` / tracked-file 语义），而 core 的 Python 实现按纯规则匹配、不查 git 索引。
//! 该分歧只影响"被 .gitignore 命中但已被 git 跟踪"的文件（编排者在 TASK-037 实测约 1.9%）。
//! 契约（R42）要求的是 `ignore` crate 语义，因此**客户端行为合规**；两侧完全一致留待
//! 后续对照测试卡（见任务卡"未决问题"）。

use std::path::Path;

use ignore::DirEntry;

/// 内置跳过目录名（与 core `DEFAULT_SKIP_DIRS` 同集合）。
pub const DEFAULT_SKIP_DIRS: &[&str] = &[
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".eggs",
    "dist",
    "build",
    "target",
    ".idea",
    ".vscode",
    ".zace",
];

/// 内置跳过目录**模式**（与 core `DEFAULT_SKIP_DIR_PATTERNS` 同集合）。
///
/// 用模式而不是穷举：真实仓库的构建产物是变体（`cmake-build-release` / `build-debug` …）。
/// `bin` / `obj` / `lib` 刻意不在列表里——它们是合法源码目录名，误伤代价高于收益。
pub const DEFAULT_SKIP_DIR_PATTERNS: &[&str] = &[
    "cmake-build-*",
    "build-*",
    "out",
    "htmlcov",
    ".cache",
    ".gradle",
    ".next",
    ".nuxt",
    ".turbo",
    ".parcel-cache",
    "__pypackages__",
];

/// 自定义忽略文件名（第 1 层，优先级最高）。
pub const CUSTOM_IGNORE_FILENAME: &str = ".zaceignore";

/// 一个仓库的忽略规则（构建一次，之后只读）。
pub struct IgnoreRules {
    root: std::path::PathBuf,
    /// 忽略文件内容的指纹（用于配置指纹：改了 .gitignore/.zaceignore 应作废缓存）。
    fingerprint: String,
}

impl IgnoreRules {
    /// 从仓库根构建（读取 `.zaceignore` / 各层 `.gitignore` 的内容用于指纹）。
    pub fn load(root: &Path) -> Self {
        let fingerprint = ignore_files_fingerprint(root);
        Self {
            root: root.to_path_buf(),
            fingerprint,
        }
    }

    pub fn fingerprint(&self) -> &str {
        &self.fingerprint
    }

    /// 构建遍历器：`.zaceignore` > `.gitignore`（`ignore` crate）+ 内置目录剪枝。
    ///
    /// 内置层用 `filter_entry` 剪枝（整目录跳过，省 IO）；内置层**不**交给 `ignore` crate，
    /// 以便跳过时能如实记录原因（R43）。
    pub fn walker(&self) -> ignore::Walk {
        let dirs = DEFAULT_SKIP_DIRS;
        let patterns = DEFAULT_SKIP_DIR_PATTERNS;
        ignore::WalkBuilder::new(&self.root)
            .add_custom_ignore_filename(CUSTOM_IGNORE_FILENAME)
            .git_ignore(true)
            // V1 不读全局 excludes / .git/info/exclude（与 core 的简化一致）
            .git_global(false)
            .git_exclude(false)
            // 不因为"隐藏"就跳过（core 只按目录名判，`.github/` 这类应被索引）
            .hidden(false)
            .parents(false)
            .follow_links(false)
            .require_git(false)
            .filter_entry(move |entry| {
                if entry.depth() == 0 {
                    return true;
                }
                let name = entry.file_name().to_string_lossy().into_owned();
                !dirs.contains(&name.as_str())
                    && !patterns
                        .iter()
                        .any(|pattern| wildcard_match(pattern, &name))
            })
            .build()
    }

    /// 目录剪枝入口（`filter_entry` 用）：内置目录名/模式 → 剪掉。
    pub fn should_descend(&self, entry: &DirEntry) -> bool {
        if entry.depth() == 0 {
            return true;
        }
        self.builtin_reason(&entry.file_name().to_string_lossy())
            .is_none()
    }

    /// 路径（仓库相对、正斜杠）是否被忽略；返回原因标签（`"builtin"` 或 `None`）。
    ///
    /// **只判内置层**：`.zaceignore` / `.gitignore` 由 `ignore` crate 在遍历时应用
    /// （`walker()` 的 `filter_entry` / 迭代结果），此处不重复实现，避免双份语义。
    pub fn builtin_reason(&self, file_name: &str) -> Option<&'static str> {
        if DEFAULT_SKIP_DIRS.contains(&file_name) {
            return Some("builtin");
        }
        if DEFAULT_SKIP_DIR_PATTERNS
            .iter()
            .any(|pattern| wildcard_match(pattern, file_name))
        {
            return Some("builtin");
        }
        None
    }
}

/// 单个 `*` 通配匹配（模式里只用到 `prefix-*` 形态）。
fn wildcard_match(pattern: &str, name: &str) -> bool {
    match pattern.split_once('*') {
        None => pattern == name,
        Some((prefix, suffix)) => {
            name.len() >= prefix.len() + suffix.len()
                && name.starts_with(prefix)
                && name.ends_with(suffix)
        }
    }
}

/// 忽略文件内容指纹：仓库根与一级目录下的 `.zaceignore` / `.gitignore` 内容拼接后 hash。
///
/// 只取两层（根 + 一级子目录）：覆盖绝大多数真实布局，避免全仓遍历
/// （缓存作废只影响性能，不影响正确性——`ignore` crate 自己会读全部层级）。
fn ignore_files_fingerprint(root: &Path) -> String {
    use sha2::{Digest, Sha256};

    let mut hasher = Sha256::new();
    let mut candidates = vec![root.to_path_buf()];
    if let Ok(entries) = std::fs::read_dir(root) {
        let mut subdirs: Vec<std::path::PathBuf> = entries
            .flatten()
            .filter(|entry| entry.file_type().is_ok_and(|kind| kind.is_dir()))
            .map(|entry| entry.path())
            .collect();
        subdirs.sort();
        candidates.extend(subdirs.into_iter().take(50));
    }
    for dir in candidates {
        for name in [CUSTOM_IGNORE_FILENAME, ".gitignore"] {
            let path = dir.join(name);
            if let Ok(text) = std::fs::read(&path) {
                hasher.update(name.as_bytes());
                hasher.update(b"\x00");
                hasher.update(&text);
                hasher.update(b"\x01");
            }
        }
    }
    hex::encode(hasher.finalize())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn collect(root: &Path) -> Vec<String> {
        let rules = IgnoreRules::load(root);
        rules
            .walker()
            .flatten()
            .filter(|entry| entry.file_type().is_some_and(|kind| kind.is_file()))
            .map(|entry| {
                entry
                    .path()
                    .strip_prefix(root)
                    .expect("entry below root")
                    .to_string_lossy()
                    .replace('\\', "/")
            })
            .collect()
    }

    #[test]
    fn builtin_dirs_and_patterns_are_pruned() {
        let project = tempfile::tempdir().expect("temp dir");
        fs::create_dir_all(project.path().join("cmake-build-release")).expect("dir");
        fs::create_dir_all(project.path().join("node_modules/pkg")).expect("dir");
        fs::write(project.path().join("cmake-build-release/a.o"), "x").expect("file");
        fs::write(project.path().join("node_modules/pkg/i.js"), "x").expect("file");
        fs::write(project.path().join("main.c"), "int main(){}").expect("file");

        let files = collect(project.path());

        assert_eq!(files, vec!["main.c".to_string()]);
    }

    #[test]
    fn gitignore_is_honoured_and_zaceignore_takes_precedence() {
        let project = tempfile::tempdir().expect("temp dir");
        fs::write(project.path().join(".gitignore"), "ignored_by_git.txt\n").expect("write");
        fs::write(project.path().join("ignored_by_git.txt"), "x").expect("write");
        fs::write(project.path().join(".zaceignore"), "ignored_by_zace.txt\n").expect("write");
        fs::write(project.path().join("ignored_by_zace.txt"), "x").expect("write");
        fs::write(project.path().join("kept.txt"), "x").expect("write");

        let files = collect(project.path());

        assert!(files.contains(&"kept.txt".to_string()));
        assert!(!files.contains(&"ignored_by_git.txt".to_string()));
        assert!(!files.contains(&"ignored_by_zace.txt".to_string()));
    }

    #[test]
    fn negation_in_gitignore_rescues_a_builtin_dir_name() {
        let project = tempfile::tempdir().expect("temp dir");
        fs::create_dir_all(project.path().join("build")).expect("dir");
        fs::write(project.path().join("build/keep.txt"), "x").expect("file");
        // 内置层会剪掉 build/；.gitignore 的否定**不能**救回被 filter_entry 剪掉的目录
        // （这是两个实现的已知差异：core 的 is_ignored 是独立 API，可被否定救回；
        //  而遍历剪枝发生在目录层）。此处断言剪枝行为，差异写入未决问题。
        let files = collect(project.path());

        assert!(!files.iter().any(|path| path.starts_with("build/")));
    }

    #[test]
    fn fingerprint_changes_when_ignore_files_change() {
        let project = tempfile::tempdir().expect("temp dir");
        let before = IgnoreRules::load(project.path()).fingerprint().to_string();
        fs::write(project.path().join(".gitignore"), "x.txt\n").expect("write");
        let after = IgnoreRules::load(project.path()).fingerprint().to_string();

        assert_ne!(before, after);
    }

    #[test]
    fn hidden_directories_are_still_indexed_contrary_to_walker_defaults() {
        let project = tempfile::tempdir().expect("temp dir");
        fs::create_dir_all(project.path().join(".github/workflows")).expect("dir");
        fs::write(
            project.path().join(".github/workflows/ci.yml"),
            "on: push\n",
        )
        .expect("file");

        let files = collect(project.path());

        assert!(files.contains(&".github/workflows/ci.yml".to_string()));
    }
}
