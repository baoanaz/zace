"""zace-core 冻结接口（CF-07/CF-09）。

来源：Module/04 §2（AnswerProvider）、Module/06 §1（ContextEngine）、
Module/01 §2.4 + D-44（EmbeddingProvider）、Module/01 §2.2（Parser）。
维护者：编排者；变更必须走 docs/plan/orchestration.md §4 契约变更协议。

实现位置约定（各卡交付物）：
  ContextEngine      → core/zace_core/engine.py        （TASK-007/013 组装，Phase 2 接入 service）
  EmbeddingProvider  → core/zace_core/embedding/       （TASK-008）
  AnswerProvider     → core/zace_core/llm/             （Phase 3，Module/04）
  Parser             → core/zace_core/parsing/         （TASK-002..005）
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from zace_core.types import (
    AskResult,
    ChangeSet,
    ContextPack,
    ParsedFile,
    ProjectHandle,
    SyncStatus,
)

# ---------------------------------------------------------------------------
# ContextEngine：core 对 service 暴露的唯一接口面（Module/06 §1）
# ---------------------------------------------------------------------------


@runtime_checkable
class ContextEngine(Protocol):
    """进程内对象，per service 进程；零 HTTP / 零鉴权 / 零用户概念（D-34）。"""

    @classmethod
    def open(cls, data_root: Path) -> ContextEngine:
        """打开/初始化引擎（数据根如 ~/.zace；core 只管 projects/）。"""
        ...

    def resolve_project(self, identity_key: str, display_name: str = "") -> ProjectHandle:
        """project identity（D-29）幂等解析/创建；identity_key 由调用方按 D-29 规则计算。"""
        ...

    def ingest(self, project_id: str, changes: ChangeSet) -> str:
        """写入变更集并排队索引（异步 job）；返回 job_id。幂等语义见 Module/06 §2.1。"""
        ...

    def sync_status(self, project_id: str) -> SyncStatus: ...

    def search(self, project_id: str, query: str, max_tokens: int = 10_000) -> ContextPack:
        """Fast 模式：检索 + 组装（Module/02+03），不调 LLM。"""
        ...

    def ask(self, project_id: str, question: str) -> AskResult:
        """Deep 模式：检索 + 组装 + AnswerProvider（Module/02/03/04）。"""
        ...

    def delete_project(self, project_id: str) -> None:
        """级联删除（D-03：rm -rf 项目目录 + 元数据行）。"""
        ...


# ---------------------------------------------------------------------------
# EmbeddingProvider：TASK-008 双实现（D-44）
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EmbeddingProfile:
    """embedding 指纹（写入 index_config；变更触发 D-07 二级失效）。"""

    model_id: str                 # 如 "local:onnx:multilingual-e5-small" / "api:bge-m3"
    dim: int
    max_input_tokens: int         # 超长输入由 provider 内部截断（Module/01 §2.4：默认 ≤2048）


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def profile(self) -> EmbeddingProfile: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """批量嵌入；输入为完整文本，截断策略由 provider 按 profile.max_input_tokens 执行。"""
        ...


# ---------------------------------------------------------------------------
# AnswerProvider：Module/04 §2（Phase 3）
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    system: str
    user: str
    max_tokens: int = 3072
    temperature: float = 0.2


@runtime_checkable
class AnswerProvider(Protocol):
    def complete(self, req: CompletionRequest) -> str: ...


# ---------------------------------------------------------------------------
# Parser：TASK-002..005（纯函数，无 I/O，可并行开发）
# ---------------------------------------------------------------------------


@runtime_checkable
class Parser(Protocol):
    language: str                 # python / c / cpp / markdown

    def parse(self, path: str, content: str) -> ParsedFile:
        """解析单文件；不抛异常（失败 → ParsedFile(fallback=True, parse_errors=[...])）。"""
        ...
