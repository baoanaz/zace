"""service 侧 MCP 端点（TASK-040；R38 裁定：M2a 由 service 直出 Streamable HTTP）。

为什么 MCP 在 service 里（而不是 Rust client）：Module/05 原设计把 MCP 放在 client，前提是
**服务在远端**（client 要扫描本地代码、算 hash、上传 blob）。本地单用户模式下 service 与代码
同机同文件系统，同步环节整体消失（TASK-034 改为服务端懒重扫），client 的厚同步层没有存在理由；
Rust client 保留给 M2c 的远端场景。

本模块只做三件事（薄壳，D-34）：

1. **协议装配**：``MCPServer``（``mcp.server.mcpserver``；2.x 起 FastMCP 更名为此）+
   两个工具（CF-06 冻结）+ 挂到 FastAPI 的 ``/mcp``（见 :func:`mount`）；
2. **参数与错误映射**：Schema 校验由 CF-06 的 inputSchema 表达；预期内的失败一律
   :class:`ToolError`（``isError=true`` + 人类可读文本，Module/05 §2.2），不让裸异常变成
   协议层 crash；
3. **阻塞调用隔离**：core 的检索是同步阻塞的（~0.5s，大仓库更久），一律经
   :func:`starlette.concurrency.run_in_threadpool`，**不在事件循环里跑**。

检索/组装/渲染**一律复用下游**：检索走 ``EngineManager.search``（= core），meta 走 TASK-032 的
:func:`zace_service.packmeta.pack_meta`，Markdown 走 core 的 ``render_markdown``。
本文件不出现任何检索、排序、装填或渲染逻辑（render_markdown 的规则与合同强耦合，只此一份）。

与 HTTP 面的关系：``/api/query/*`` 是 REST 面，``/mcp`` 是 MCP 面，两者共用同一套 core 调用与
meta；区别只在返回形态（REST 返回 ``{markdown, meta}``，MCP 返回文本）与错误形态（CF-05 信封
vs ``isError``）。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Annotated, Any

from fastapi import FastAPI
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.tools import Tool
from pydantic import Field
from starlette.concurrency import run_in_threadpool
from starlette.routing import Route
from zace_core.contextpack import render_markdown
from zace_core.engine import (
    EngineError,
    repo_identity,
)
from zace_core.engine import (
    project_id_for as engine_project_id_for,
)

from zace_service.config import Settings
from zace_service.errors import (
    PROVIDER_UNAVAILABLE_HINT,
    map_engine_error,
)
from zace_service.logging import get_logger, redact_text
from zace_service.packmeta import pack_meta
from zace_service.routers.query import (
    DEFAULT_MAX_TOKENS,
    DEGRADED_NOTICE,
    MAX_MAX_TOKENS,
    MAX_QUERY_CHARS,
)
from zace_service.runtime import EngineManager

__all__ = [
    "MCP_MOUNT_PATH",
    "MCP_SERVER_NAME",
    "ASK_TOOL",
    "SEARCH_TOOL",
    "TOOL_NAMES",
    "build_mcp",
    "manager_for_app",
    "mount",
    "session_lifespan",
]

logger = get_logger("zace_service.mcp")

#: 挂载点（编辑器 URL 为 ``http://<host>:<port>/mcp``）。
MCP_MOUNT_PATH = "/mcp"
#: ``initialize`` 里的 server 名（编辑器侧显示用）。
MCP_SERVER_NAME = "zace"
#: ``search_context`` 的 ``max_tokens`` 上限（**CF-06 冻结值**：16000）。
MAX_TOKENS_LIMIT = 16_000

SEARCH_TOOL = "search_context"
ASK_TOOL = "ask_project"
#: CF-06 冻结的两个工具名（测试断言"恰好这两个"）。
TOOL_NAMES: frozenset[str] = frozenset({SEARCH_TOOL, ASK_TOOL})

#: 工具 description（CF-06 的文案：description 是"行为控制"，含与 grep/read 的分工边界）。
_SEARCH_DESCRIPTION = (
    "在当前项目工作区检索与问题最相关的上下文（代码/调用链/文档证据包）。"
    "适合'XX 在哪里实现/谁在调用它'这类需要跨文件定位的问题；已知精确标识符的全量引用请用 grep，"
    "已知文件请直接 read。返回 ContextPack 的 Markdown 渲染（含证据 id、行号与 Missing Evidence）。"
)
_ASK_DESCRIPTION = (
    "就当前项目提出调查性问题，返回基于证据包（含代码与设计文档）的带引用回答，并在证据不足时"
    "给出缺口说明与改问建议。需要直接结论（'为什么/如何设计/实现与设计是否一致'）时用它；"
    "只想要原始上下文时用 search_context。"
)

#: 懒构造 EngineManager 的互斥（MCP 工具没有 ``Request``，不能直接用 ``deps.get_engine_manager``）。
_manager_lock = Lock()


# --------------------------------------------------------------------------- 装配


def build_mcp(
    engine_manager: EngineManager | Callable[[], EngineManager],
    *,
    settings: Settings | None = None,
) -> MCPServer:
    """装配 MCPServer + 两个工具（冻结入口：``build_mcp(engine_manager) -> MCPServer``）。

    ``engine_manager`` 可以是 :class:`~zace_service.runtime.EngineManager` 实例，也可以是**零参
    可调用对象**（懒解析）：``create_app`` 不知道引擎何时建（TASK-030 的"起服务不加载模型 / 懒构造"
    纪律），因此应用侧传 ``lambda: manager_for_app(app)``，工具被调用时才真正拿管理器。

    ``settings`` 只用于本地模式的懒重扫间隔（TASK-034 §C）；缺省从环境变量解析，便于单测直接
    用冻结的一参形式。
    """
    resolved_settings = settings if settings is not None else Settings.from_env()
    resolve = engine_manager if callable(engine_manager) else (lambda: engine_manager)

    async def search_context(
        query: Annotated[
            str, Field(min_length=1, description="自然语言或符号混合查询，中英均可")
        ],
        project_root: Annotated[
            str, Field(min_length=1, description="项目根绝对路径，正斜杠")
        ],
        max_tokens: Annotated[int, Field(ge=1, le=MAX_TOKENS_LIMIT)] = DEFAULT_MAX_TOKENS,
    ) -> str:
        """CF-06 的 ``search_context``（Fast 模式：检索 + 组装 + 服务端渲染）。"""
        _require_query(query)
        manager = resolve()
        project_id = _project_id_for(manager, project_root)
        _require_index(manager, project_id)
        return await run_in_threadpool(
            _search_text, manager, resolved_settings, project_id, query.strip(), max_tokens
        )

    async def ask_project(
        question: Annotated[
            str, Field(min_length=1, description="需要项目级回答的问题，中英均可")
        ],
        project_root: Annotated[
            str, Field(min_length=1, description="项目根绝对路径，正斜杠")
        ],
        max_tokens: Annotated[
            int, Field(ge=1, description="answer 输出上限（token）")
        ] = DEFAULT_MAX_TOKENS,
    ) -> str:
        """CF-06 的 ``ask_project``（Phase 2 一律走 D-26 降级包，不假装有 LLM 总结）。"""
        _require_query(question, field="question")
        _require_service_max_tokens(max_tokens)
        manager = resolve()
        project_id = _project_id_for(manager, project_root)
        _require_index(manager, project_id)
        return await run_in_threadpool(
            _ask_text, manager, resolved_settings, project_id, question.strip(), max_tokens
        )

    return MCPServer(
        name=MCP_SERVER_NAME,
        tools=[
            _cf06_tool(search_context, name=SEARCH_TOOL, description=_SEARCH_DESCRIPTION),
            _cf06_tool(ask_project, name=ASK_TOOL, description=_ASK_DESCRIPTION),
        ],
    )


def mount(app: FastAPI, mcp: MCPServer, *, json_response: bool = False) -> None:
    """把 MCP 挂到 ``app`` 的 ``/mcp``（由 ``create_app`` 调用一次）。

    **必须**传 ``streamable_http_path="/"``：``streamable_http_app`` 的内层路径默认也是 ``/mcp``，
    与挂载前缀叠加会变成 ``/mcp/mcp`` → 所有 MCP 请求 404。

    ``json_response``：默认 ``False``（SDK 的 SSE 形态，``Content-Type: text/event-stream``）；
    ``True`` 时返回纯 JSON（``application/json``）。生产装配保持默认——编排者在 2.2.0 上实测的
    就是 SSE 形态（见任务卡"已验证的实现要点"），不额外引入与编辑器兼容性相关的未知量。

    Origin / DNS-rebinding 防护**保持 SDK 默认**（``host="127.0.0.1"`` → 自动放行
    ``127.0.0.1:*`` / ``localhost:*`` / ``[::1]:*``；其它 Origin 403）：本地单用户模式下这是
    唯一挡住"浏览器里的任意网页访问本机服务"的机制，**不得为了跑通顺手关掉**。

    **另加一条无重定向的别名路由**（实测发现）：Starlette 的 ``Mount`` 只匹配 ``/mcp/...``，
    请求 ``POST /mcp`` 会先被 307 重定向到 ``/mcp/``。我们对外给的 URL 恰好是 ``/mcp``，
    跟随重定向与否取决于各编辑器的 HTTP 客户端，因此这里把 SDK 生成的内层 ASGI 端点直接注册到
    ``/mcp``（与挂载同一个 session manager / 同一个 Starlette 应用），使**两个 URL 都直接可用、
    行为一致**。
    """
    starlette_app = mcp.streamable_http_app(streamable_http_path="/", json_response=json_response)
    app.mount(MCP_MOUNT_PATH, starlette_app)
    app.router.routes.append(
        Route(MCP_MOUNT_PATH, endpoint=starlette_app.routes[0].endpoint)
    )


@asynccontextmanager
async def _session_manager_running(mcp: MCPServer) -> Iterator[None]:
    async with mcp.session_manager.run():
        yield


def session_lifespan(mcp: MCPServer) -> Callable[[Any], AbstractAsyncContextManager[None]]:
    """Starlette/FastAPI 形状的 lifespan（``Callable[[app], AsyncContextManager]``）。

    跑 session manager 的 lifespan（**必须**，否则 ``initialize`` 建不了会话）：
    ``session_manager`` 由 :func:`mount`（即 ``streamable_http_app``）创建，因此本 lifespan 只能
    在挂载之后启动；TASK-030 的 app 没有自己的 lifespan（起服务不加载模型），所以直接接管
    ``app.router.lifespan_context``——将来若出现别的 lifespan，在 ``async with`` 里嵌套组合，
    不要覆盖。
    """

    def _lifespan(_app: Any) -> AbstractAsyncContextManager[None]:
        return _session_manager_running(mcp)

    return _lifespan


def _cf06_tool(fn: Callable[..., Any], *, name: str, description: str) -> Tool:
    """按函数签名建工具，并把 inputSchema 对齐到 CF-06。

    SDK 从签名生成 schema（``Tool.from_function``），但**不会**生成 ``additionalProperties``，
    而 CF-06 声明了 ``additionalProperties: false``——这里补上这一个键，使 ``tools/list`` 与冻结
    合同逐字段一致（纯声明性，不改变运行时行为：多余参数本来就被 pydantic 忽略）。

    ``structured_output=False``：工具只返回**文本**（ContextPack 的 Markdown + 一行 zace 状态），
    与 Module/05 §5"客户端只透传 Markdown"一致，不给编辑器再塞一份 JSON。
    """
    tool = Tool.from_function(fn, name=name, description=description, structured_output=False)
    tool.parameters["additionalProperties"] = False
    return tool


def manager_for_app(app: FastAPI) -> EngineManager:
    """取应用级 EngineManager（懒构造；与 ``deps.get_engine_manager`` 同口径）。

    为什么不在 ``deps`` 里复用：那个入口要一个 ``Request``，而 MCP 工具没有 HTTP 请求对象。
    这里复刻"双重检查 + 加锁"的几行；出现第三个入口时抽成公共函数。
    """
    manager = getattr(app.state, "engine_manager", None)
    if isinstance(manager, EngineManager):
        return manager
    with _manager_lock:
        manager = getattr(app.state, "engine_manager", None)
        if not isinstance(manager, EngineManager):
            manager = EngineManager.open(app.state.settings.data_root)
            app.state.engine_manager = manager
    return manager


# --------------------------------------------------------------------------- 工具实现（线程池）


def _search_text(
    manager: EngineManager,
    settings: Settings,
    project_id: str,
    query: str,
    max_tokens: int,
) -> str:
    """``search_context`` 的正体（同步；由调用方放进线程池）。"""
    _rescan_if_due(manager, settings, project_id)
    trace = _call_engine(lambda: manager.search(project_id, query, max_tokens))
    meta = pack_meta(
        trace.pack,
        project_id=project_id,
        channels=trace.channels_used,
        degraded=trace.degraded,
        # core 的降级原因可能带 provider 原始报错（TASK-035 §A 的同一纪律：secret 不进响应）。
        reason=redact_text(trace.degraded_reason) if trace.degraded_reason else None,
        candidate_count=trace.candidate_count,
    )
    return f"{_status_line(meta)}\n\n{render_markdown(trace.pack)}"


def _ask_text(
    manager: EngineManager,
    settings: Settings,
    project_id: str,
    question: str,
    max_tokens: int,
) -> str:
    """``ask_project`` 的正体：Phase 2 固定返回**降级包**（D-26），不假装有 LLM 总结。"""
    _rescan_if_due(manager, settings, project_id)
    trace = _call_engine(lambda: manager.search(project_id, question, max_tokens))
    meta = pack_meta(
        trace.pack,
        project_id=project_id,
        channels=trace.channels_used,
        degraded=True,
        reason=DEGRADED_NOTICE,
        candidate_count=trace.candidate_count,
    )
    return f"{DEGRADED_NOTICE}\n\n{_status_line(meta)}\n\n{render_markdown(trace.pack)}"


def _status_line(meta: dict[str, Any]) -> str:
    """一行 zace 状态（``answerable`` / ``confidence`` / 证据计数）。

    **为什么要有这一行**：``render_markdown`` 只渲染 ``confidence``（``### Meta`` 段），不含
    ``answerable``；而 Module/03 §4.4 要求工具返回值如实反映 answerable 的语义，编辑器也要据此
    决定"要不要说证据不足"。故在 Markdown **之前**加这一行——正文仍逐字来自
    ``render_markdown(pack)``，本行只是 TASK-032 ``pack_meta`` 输出的一行摘要（不重新推导任何值）。
    """
    answerable = "true" if meta["answerable"] else "false"
    degraded = "true" if meta["degraded"] else "false"
    return (
        f"[zace] answerable={answerable} · confidence={meta['confidence']} · "
        f"evidence={meta['evidenceCount']} · docs={meta['docsCount']} · "
        f"mode={meta['mode']} · channels={','.join(meta['channelsUsed']) or '-'} · "
        f"degraded={degraded}"
    )


def _rescan_if_due(manager: EngineManager, settings: Settings, project_id: str) -> None:
    """本地模式：检索前的增量懒重扫（TASK-034 §C 的冻结接口，**MCP 侧入口**）。

    HTTP 面（``routers/query.py``）是 §C 指定的触发点；编辑器（本模块）是同一语义的第二个入口——
    本地模式下用户改完代码直接在编辑器里提问，没有这一步就会一直看到"启动那一刻"的索引。

    纪律与 §C 一致：**重扫失败不得让检索失败**，只记日志（HTTP 面额外把它写进
    ``meta.freshness.rescanError``；MCP 面不往给编辑器的 Markdown 里塞这个信号）。
    """
    try:
        manager.rescan_if_due(project_id, min_interval_s=settings.local_rescan_interval_s)
    except Exception as exc:
        logger.warning(
            "懒重扫失败（检索照常）：%s → %s",
            project_id,
            redact_text(f"{type(exc).__name__}: {exc}"),
        )


# --------------------------------------------------------------------------- 参数与错误面


def _require_query(raw: str, *, field: str = "query") -> None:
    """空/纯空白/超长查询 → 可读的 ``isError`` 文本（Module/05 §2.2 的参数错误面）。"""
    if not raw.strip():
        raise ToolError(f"{field} 不能为空或纯空白：请给出自然语言或符号混合的问题（中英均可）。")
    if len(raw) > MAX_QUERY_CHARS:
        raise ToolError(
            f"{field} 过长（{len(raw)} 字符，上限 {MAX_QUERY_CHARS}）：请把问题聚焦成一句话。"
        )


def _require_service_max_tokens(max_tokens: int) -> None:
    """``ask_project`` 的 ``max_tokens`` 上限。

    CF-06 只给 ``ask_project.max_tokens`` 声明 ``minimum: 1``（无上限），但套餐预算直接把
    ``max_tokens`` 当硬上限（``Engine._budget``），所以服务端必须有兜底：与 HTTP 面
    ``routers/query.py`` 同值（20000）。这是**服务端限制**，不是 schema 变更。
    """
    if max_tokens > MAX_MAX_TOKENS:
        raise ToolError(
            f"max_tokens={max_tokens} 超出服务端上限 {MAX_MAX_TOKENS}：请调小"
            f"（search_context 的 schema 上限更低，为 {MAX_TOKENS_LIMIT}）。"
        )


def _project_id_for(manager: EngineManager, project_root: str) -> str:
    """``project_root`` → projectId（D-29 身份），并确认该项目在本服务里存在。

    CF-06 的参数是 ``project_root``（绝对路径），因此 MCP 面用**同一套身份规则**反解 projectId：
    与 ``POST /api/projects/resolve``/``attach`` 完全一致，不新增映射表、不落额外状态。
    """
    raw = project_root.strip()
    if "\\" in raw:
        raise ToolError(
            "project_root 含反斜杠，必须是**正斜杠**的绝对路径（本地模式下服务跑在 WSL/Linux，"
            f"Windows 路径如 C:\\... 在这里不存在）：收到 {project_root!r}"
        )
    try:
        identity = repo_identity(Path(raw))
    except Exception as exc:  # 路径本身非法（如含空字节）：如实报参数问题
        raise ToolError(f"project_root 无法解析为路径：{redact_text(str(exc))}") from exc
    project_id = engine_project_id_for(identity.identity_key)
    if not manager.project_exists(project_id):
        raise ToolError(
            f"未知项目：{raw} 对应的 projectId {project_id} 在本服务里没有索引记录（D-29 身份）。"
            f"本地模式请用 `zace-service local --repo {raw}` 起服务，"
            "或先 POST /api/projects/attach；远端模式请先同步（POST /api/sync/batch-upload）。"
        )
    return project_id


def _require_index(manager: EngineManager, project_id: str) -> None:
    """空索引 → 可操作的 ``isError`` 文本（含 TASK-034 的进度 + 重试提示）。

    三岔口（与 ``routers/query.py`` 的 TASK-035 §B 同口径，**根因优先**）：

    1. provider 不可用 → 直接说根因（否则用户会一直"稍后重试"而永远好不了）；
    2. 索引中/从未跑过 → 报当前状态与已处理文件数（**不伪造百分比**，D-30）；
    3. 给出"下一步做什么"（重试 / 看 indexProgress / 触发 rescan）。
    """
    if manager.sync_status(project_id)["chunks"] > 0:
        return

    ok, reason = manager.provider_health()
    if not ok:
        raise ToolError(
            f"项目 {project_id} 的索引为空，且 embedding provider 当前不可用（{reason}）："
            f"这不是「索引还没跑完」，重试不会好。{PROVIDER_UNAVAILABLE_HINT}"
        )

    progress = manager.index_progress(project_id)
    state = (
        f"{progress.state}（已处理 {progress.processed_files}/{progress.total_files} 个文件）"
        if progress.state != "idle"
        else "idle（本进程还没为它跑过索引）"
    )
    raise ToolError(
        f"项目 {project_id} 暂无可用索引（chunks=0），当前索引状态：{state}。\n"
        "如果刚启动本地服务，后台索引可能还在跑：**稍后重试本查询**，"
        f"或用 GET /api/projects/{project_id} 查看 indexProgress；\n"
        "如果一直是空，请确认仓库路径正确并重新 `zace-service local --repo <根目录>`"
        "（或 POST /api/projects/{id}/rescan 手动触发增量重扫）。"
    )


def _call_engine(call: Callable[[], Any]) -> Any:
    """执行 core 调用并把失败映射成 ``isError``（**不让裸异常冒到协议层**）。

    - provider / 存储类故障 → 复用 TASK-035 的 :func:`map_engine_error`（同一份可操作指引文案；
      MCP 面没有 HTTP 状态码，只取 message）；
    - ``EngineError``（core 的通用错误）→ 脱敏后原样告知；
    - 其它异常 → 全量堆栈进日志，对外只给一行摘要（secret 不进响应）。
    """
    try:
        return call()
    except Exception as exc:
        mapped = map_engine_error(exc)
        if mapped is not None:
            logger.warning("MCP 工具调用失败（依赖类）：%s", mapped.code)
            raise ToolError(mapped.message) from exc
        if isinstance(exc, EngineError):
            raise ToolError(redact_text(f"检索失败：{exc}")) from exc
        logger.exception("MCP 工具调用出现未预期异常")
        raise ToolError(
            redact_text(f"检索失败（{type(exc).__name__}）：{exc}；服务端日志含完整堆栈")
        ) from exc
