"""账户资料与用量/历史聚合（TASK-062/064 的服务层合成）。

为什么单独成文件：**"平均耗时/成功失败次数"来自两个不同的源**——

- **内存态进度**（:class:`~zace_service.indexer.ProjectIndexer`）：当前这一次跑到哪了，
  服务重启即丢（D-30 的如实呈现）；
- **落库历史**（``zace-meta.db`` 的 ``index_runs`` / ``query_audit``）：跨次、跨重启的统计。

两者含义不同、生命周期不同，合成规则集中在这里（唯一一处），页面只消费结果，
不各自拼凑——否则"成功次数"在首页与历史页会给出不同的数。

口径（冻结给 web）：

- ``avgDurationMs`` **只统计成功**的索引（失败 run 的耗时是"失败得多快"，混入即误导）；
- ``processedFiles`` 与 ``totalFiles`` **不同量纲**（前者只数真正解析的文件），不做除法；
- 无数据时一律 ``None`` / ``0``，**不填假值**。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zace_service.metadb import MetaDB

__all__ = ["IndexStatsBundle", "account_overview", "dir_size_bytes"]


@dataclass(frozen=True, slots=True)
class IndexStatsBundle:
    """索引统计（内存态当前进度 + 落库历史聚合 + 磁盘占用）。"""

    project_id: str
    display_name: str
    attached_root: str | None
    #: 内存态：本次进度的六字段（服务重启后为 idle，口径见 M2a 手册 §2）。
    current: dict[str, Any]
    #: 落库聚合：total/succeeded/failed/avgDurationMs/...（``index_stats().to_json()``）。
    history: dict[str, Any]
    #: 磁盘占用（字节；data_root/projects/{id} 的 du）。
    disk_bytes: int

    def to_json(self) -> dict[str, Any]:
        return {
            "projectId": self.project_id,
            "displayName": self.display_name,
            "attachedRoot": self.attached_root,
            "current": self.current,
            "history": self.history,
            "diskBytes": self.disk_bytes,
        }


def dir_size_bytes(path: Path) -> int:
    """目录占用（递归求和；不存在 → 0）。**只统计、不改动**。"""
    if not path.is_dir():
        return 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:  # 并发删除/权限：跳过该文件，不让统计失败
            continue
    return total


def account_overview(
    *,
    user_name: str,
    user_created_at: int,
    is_local: bool,
    project_ids: list[str],
    projects: list[dict[str, Any]],
    db: MetaDB,
    days: int = 30,
) -> dict[str, Any]:
    """首页账户面板的数据：账户资料 + 跨项目索引统计 + 查询用量。

    ``projects`` 是 ``EngineManager.list_projects()`` 的原始项（含 ``sync`` 与 ``indexProgress``），
    本函数**不改写**它们，只做聚合与转名——保证"页面看到的项目数"与"项目列表页"一致。
    """
    index = db.all_index_stats(project_ids, limit=10)
    usage = db.usage_summary(project_ids, days=days, recent_limit=10)
    return {
        "account": {
            "name": user_name,
            "createdAt": user_created_at,
            "isLocal": is_local,
            "projectCount": len(project_ids),
        },
        "index": index.to_json(),
        "usage": usage.to_json(),
        "projects": projects,
        "days": days,
    }
