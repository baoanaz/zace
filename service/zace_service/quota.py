"""存储配额判定与 tool 内告警（TASK-094 §B2/§B3）。

用户需求原文（2026-09-14）：

> 用户存在内存上限，需要在 tool 的内容中报警，提示 Agent 提醒用户进行管理内存。

因此本模块的产出**不是日志、不是指标**，而是一段能直接放进 tool 返回内容、被 Agent **原话转述
给用户**的 Markdown（:func:`QuotaStatus.warning_markdown`）。日志里再写一份是补充，不是替代。

四条口径（本卡冻结）：

1. **告警不阻断**（用户拍板）：超限**不拒绝**索引上传与检索，只提醒。V1 刚有删除入口，
   硬性拒绝会把人突然卡死。
2. **旁路纪律**（与 TASK-084 审计同一纪律）：配额统计是**旁路**——统计失败、目录读不到、
   元数据库不可用，都**不得**让检索失败。两个入口分工：
   - :func:`warning_for` 给检索路径用，**吞掉所有异常**返回 ``None``；
   - :func:`check_quota` 给测试与只读端点用，抛异常以便暴露缺陷。
3. **两个上限都为 0 = 不限**（``Settings.storage_quota_enabled`` 为假）：判定恒为 ``ok``，
   tool 返回里**不出现告警节**（不打扰本地开发与测试）。
4. **口径诚实**（TASK-083 纪律）：不限时 ``ratio`` 是 ``None`` 而不是 0——"没有上限"与
   "用了 0%"是两件事；未测量同样不填 0。

尺寸来源：``{data_root}/projects/{id}`` 的递归求和（:func:`zace_service.stats.dir_size_bytes`），
即**索引数据的磁盘占用**（``index.db`` + ``vectors/`` + ``blobs/`` + 同步账本），
**不含**用户的源码仓库。真机实测：``cockpit-agents`` 项目 18 个文件 / 3416 chunks 的目录
求和约 0.8 ms（28 MiB），因此每次检索前做一次求和是可接受的成本。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from zace_service.config import Settings
from zace_service.logging import get_logger, redact_text

if TYPE_CHECKING:  # 仅类型：避免 stats ↔ quota 的导入环（见 project_usage_bytes）
    from zace_service.metadb import MetaDB
    from zace_service.runtime import EngineManager

__all__ = [
    "STATUS_EXCEEDED",
    "STATUS_OK",
    "STATUS_WARNING",
    "STORAGE_WARNING_HEADING",
    "QuotaDimension",
    "QuotaStatus",
    "append_warning",
    "check_quota",
    "format_bytes",
    "project_usage_bytes",
    "status_from_sizes",
    "user_usage_bytes",
    "visible_project_ids",
    "warning_for",
]

logger = get_logger("zace_service.quota")

#: 三态（:func:`check_quota` 的返回值与 web 的显示分支共用同一套词）。
STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_EXCEEDED = "exceeded"

#: tool 返回里那一节的标题（**冻结**：测试与 Agent 侧都以它为准）。
STORAGE_WARNING_HEADING = "### Storage Warning"

#: 控制台路径（告警文案指引用户去删项目；与 web 的路由一致）。
_CONSOLE_PATH = "/"


@dataclass(frozen=True, slots=True)
class QuotaDimension:
    """一个维度的用量（单用户总额 或 单项目）。"""

    used_bytes: int
    #: 上限；``0`` 表示**不限**（此时 :attr:`ratio` 与 :attr:`status` 见下）。
    limit_bytes: int
    #: 已用 / 上限；**不限时为 ``None``**（"没有上限"不是"用了 0%"）。
    ratio: float | None
    status: str

    @property
    def unlimited(self) -> bool:
        return self.limit_bytes <= 0

    def to_json(self) -> dict[str, Any]:
        return {
            "usedBytes": self.used_bytes,
            "limitBytes": self.limit_bytes,
            "ratio": self.ratio,
            "status": self.status,
            "unlimited": self.unlimited,
        }


@dataclass(frozen=True, slots=True)
class QuotaStatus:
    """一次配额判定的完整结果（用户维度 + 项目维度）。"""

    project_id: str
    user: QuotaDimension
    project: QuotaDimension
    #: 生效的告警阈值比例（回显给 UI，便于解释"为什么现在报警"）。
    warn_ratio: float

    @property
    def status(self) -> str:
        """总体状态 = 两个维度里**最差**的那个（``exceeded`` > ``warning`` > ``ok``）。"""
        order = {STATUS_OK: 0, STATUS_WARNING: 1, STATUS_EXCEEDED: 2}
        return max((self.user.status, self.project.status), key=lambda item: order[item])

    @property
    def should_warn(self) -> bool:
        return self.status != STATUS_OK

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "warnRatio": self.warn_ratio,
            "projectId": self.project_id,
            "user": self.user.to_json(),
            "project": self.project.to_json(),
        }

    def warning_markdown(self) -> str | None:
        """tool 返回里要追加的那一节；``ok``/不限 → ``None``（**不打扰**）。

        文案是给 **Agent 读并转述**的：每条都以"请提醒用户"收尾，并说清"去哪儿删、删了会怎样"
        （配合 §D 的删除入口形成闭环）。超限时**明确写出"不阻断"**——否则 Agent 可能自作主张
        停止索引，而那不是我们的行为。
        """
        if not self.should_warn:
            return None
        lines = [STORAGE_WARNING_HEADING]
        lines.extend(_dimension_lines(self.user, subject="当前账户的索引数据"))
        if self.project.status != STATUS_OK:
            lines.extend(
                _dimension_lines(self.project, subject=f"项目 {self.project_id} 的索引数据")
            )
        if self.status == STATUS_EXCEEDED:
            lines.append(
                "- 已超出上限：**新索引与检索仍会照常进行（不阻断）**，"
                f"但请提醒用户去控制台（{_CONSOLE_PATH}）删除不再需要的项目以释放空间。"
                "删除只影响索引数据，源码文件不受影响，需要时重新索引即可。"
            )
        else:
            lines.append(
                f"- 请提醒用户：可在控制台（{_CONSOLE_PATH}）查看各项目占用，"
                "删除不再需要的项目以释放空间。删除只影响索引数据，源码文件不受影响。"
            )
        return "\n".join(lines)


def _dimension_lines(dimension: QuotaDimension, *, subject: str) -> list[str]:
    """一个维度的一行（用量 / 上限 / 百分比；不限时如实说"未设上限"）。"""
    if dimension.unlimited:
        return [f"- {subject}已用 {format_bytes(dimension.used_bytes)}（未设上限）。"]
    percent = f"{dimension.ratio * 100:.0f}%" if dimension.ratio is not None else "—"
    over = "，已超出上限" if dimension.status == STATUS_EXCEEDED else ""
    return [
        f"- {subject}已用 {format_bytes(dimension.used_bytes)} / "
        f"上限 {format_bytes(dimension.limit_bytes)}（{percent}{over}）。"
    ]


def format_bytes(size: int) -> str:
    """字节数 → 人读字符串（与 web 的 ``formatBytes`` 同一套单位与舍入）。"""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KiB"
    if size < 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MiB"
    return f"{size / 1024 / 1024 / 1024:.2f} GiB"


def project_usage_bytes(manager: EngineManager, project_id: str) -> int:
    """单项目的索引数据磁盘占用（递归求和；目录不存在 → 0）。

    局部导入 :func:`zace_service.stats.dir_size_bytes`（而不是模块抬头）：``stats`` 反过来要用
    本模块的 :func:`status_from_sizes`（概览页的配额判定），模块级互相 import 会形成导入环
    （先被导入的那一侧在环里拿不到尚未定义的名字）。本仓库已有同类的局部导入先例
    （``mcp.build_answer_provider`` / ``auth._embedding_config``）。
    """
    from zace_service.stats import dir_size_bytes

    return dir_size_bytes(manager.project_dir(project_id))


def user_usage_bytes(manager: EngineManager, project_ids: Iterable[str]) -> int:
    """一个用户的索引数据总额（其**全部**项目之和）。"""
    return sum(project_usage_bytes(manager, project_id) for project_id in project_ids)


def visible_project_ids(
    manager: EngineManager, db: MetaDB | None, user_id: str | None
) -> list[str]:
    """当前身份可见的 projectId（**与 ops/projects 路由同一口径**）。

    - 无账户（本地模式 R34）或元数据库缺失 → 全量（``None`` 用户语义）；
    - 有账户 → 只取其已归属的项目（TASK-061 的逻辑授权层）。

    为什么复用同一口径而不是各写一份：用量统计若把别人的项目算进来，告警数字就是假的
    （DoD 的"多用户隔离：A 的用量不计入 B 的额度"正是钉这一点）。
    """
    all_ids = [str(item["projectId"]) for item in manager.list_projects()]
    if db is None or user_id is None:
        return all_ids
    owned = set(db.list_projects(user_id))
    return [project_id for project_id in all_ids if project_id in owned]


def check_quota(
    manager: EngineManager,
    settings: Settings,
    *,
    project_id: str,
    project_ids: Sequence[str] | None = None,
) -> QuotaStatus:
    """判定当前用量落在哪个状态（**可能抛异常**：给测试与只读端点用）。

    检索路径请用 :func:`warning_for`——它吞掉异常（旁路纪律）。

    ``project_ids`` 是"该用户全部项目"的列表。**给了就用给的**（哪怕空列表——那如实地表示
    "这个账户没有项目"，用量就是 0）；不传（``None``）才退化成只算当前项目（调用方拿不到
    归属信息时至少给出项目维度的真话，**不编造**一个用户总额）。
    """
    ids = list(project_ids) if project_ids is not None else [project_id]
    return status_from_sizes(
        {candidate: project_usage_bytes(manager, candidate) for candidate in ids},
        settings,
        project_id=project_id,
    )


def status_from_sizes(
    sizes: Mapping[str, int], settings: Settings, *, project_id: str
) -> QuotaStatus:
    """已知各项目占用时的判定（**不重复遍历目录**）。

    给已经拿到 ``describe_project`` 的 ``diskBytes`` 的调用方用（如 ``/api/account/overview``：
    它本来就有每个项目的占用，再走一遍 :func:`check_quota` 会把同一批目录重算一次）。
    两个入口共用 :func:`_judge`，因此"怎么才算 warning"只有一份实现。
    """
    return QuotaStatus(
        project_id=project_id,
        user=_judge(
            sum(max(0, int(value)) for value in sizes.values()),
            settings.storage_limit_per_user_bytes,
            settings.storage_warn_ratio,
        ),
        project=_judge(
            max(0, int(sizes.get(project_id, 0))),
            settings.storage_limit_per_project_bytes,
            settings.storage_warn_ratio,
        ),
        warn_ratio=settings.storage_warn_ratio,
    )


def _judge(used: int, limit: int, warn_ratio: float) -> QuotaDimension:
    """用量 → 三态（``limit <= 0`` → 不限，恒 ``ok``）。"""
    if limit <= 0:
        return QuotaDimension(used_bytes=used, limit_bytes=0, ratio=None, status=STATUS_OK)
    ratio = used / limit
    if used >= limit:
        status = STATUS_EXCEEDED
    elif ratio >= warn_ratio:
        status = STATUS_WARNING
    else:
        status = STATUS_OK
    return QuotaDimension(used_bytes=used, limit_bytes=limit, ratio=ratio, status=status)


def warning_for(
    manager: EngineManager,
    settings: Settings,
    *,
    project_id: str,
    db: MetaDB | None = None,
    user_id: str | None = None,
) -> str | None:
    """给 tool 返回用的告警 Markdown（**绝不让检索失败**，TASK-084 同一纪律）。

    三条防线：

    1. 两侧配额都为 0（不限）→ 直接返回 ``None``，连目录都不去遍历；
    2. 归属解析与目录求和包在 ``try`` 里：任何失败只记 WARN 并返回 ``None``；
    3. 文案生成同样包住——"提醒"这件事不该有让请求 500 的能力。

    调用方拿到的是 ``str | None``，直接接在 tool 文本之后即可（:func:`append_warning`）。
    """
    if not settings.storage_quota_enabled:
        return None
    try:
        ids = visible_project_ids(manager, db, user_id)
        status = check_quota(manager, settings, project_id=project_id, project_ids=ids)
        return status.warning_markdown()
    except Exception as exc:  # noqa: BLE001 - 旁路：配额判定失败不得让检索失败
        logger.warning(
            "存储配额判定失败（检索照常）：%s → %s",
            project_id,
            redact_text(f"{type(exc).__name__}: {exc}"),
        )
        return None


def append_warning(text: str, warning: str | None) -> str:
    """把告警节追加到 tool 文本末尾（``None`` 时**原样返回**，不产生多余空行）。"""
    if not warning:
        return text
    return f"{text}\n\n{warning}"
