"""本地 / API embedding 模型注册表（TASK-008 §B/§C）。

设计要点：
- ``dim`` 与 ``max_input_tokens`` 只在这里定义，实现（local.py / api.py）不得写死，
  这样 TASK-015 bake-off 调整默认模型或截断值时只需改本文件；
- 本注册表也是 TASK-015 的候选清单来源与 ``EmbeddingProfile`` 的唯一构造依据；
- ``model_id`` 命名按 TASK-008 §A：``local:<model_slug>`` / ``api:<model_name>``，
  写入 ``index_config`` 后参与 D-07 二级失效判定（TASK-007/009 消费）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from zace_core.embedding.base import EmbeddingConfigError

#: 池化方式：``mean`` = 注意力掩码加权平均（e5 系列）；``cls`` = 取首 token（bge / arctic）。
Pooling = Literal["mean", "cls"]

#: 暂定默认本地模型；最终由 TASK-015 bake-off 钉死（D-44）。
DEFAULT_LOCAL_SLUG = "multilingual-e5-small"


@dataclass(frozen=True, slots=True)
class LocalModelSpec:
    """本地 ONNX 模型条目。"""

    slug: str
    repo_id: str
    onnx_file: str
    dim: int
    pooling: Pooling
    max_input_tokens: int = 512
    query_prefix: str = ""
    passage_prefix: str = ""
    tokenizer_file: str = "tokenizer.json"
    notes: str = ""

    @property
    def model_id(self) -> str:
        """指纹 id（卡内 §A）：``local:<model_slug>``。"""
        return f"local:{self.slug}"

    @property
    def repo_file(self) -> str:
        """人类可读的模型文件坐标（错误信息用）。"""
        return f"{self.repo_id}/{self.onnx_file}"


@dataclass(frozen=True, slots=True)
class ApiModelSpec:
    """OpenAI-compatible API 模型条目。

    未登记的模型名允许通过 ``dim`` 显式声明（见 factory），但必须显式给维度：
    猜维度会让 ``profile.dim`` 失真，进而让 D-07 失效判定失效。
    """

    name: str
    dim: int
    max_input_tokens: int = 2048
    query_prefix: str = ""
    passage_prefix: str = ""
    notes: str = ""

    @property
    def model_id(self) -> str:
        """指纹 id（卡内 §A）：``api:<model_name>``。"""
        return f"api:{self.name}"


# 维度 / 截断值的来源核实（2026-09-10 查 HuggingFace config.json 与 tokenizer_config.json）：
# - intfloat/multilingual-e5-small：hidden_size=384，max_position_embeddings=512，
#   model_max_length=512
# - Snowflake/snowflake-arctic-embed-xs：hidden_size=384，max_position_embeddings=512
# - Xenova/bge-small-zh-v1.5：hidden_size=512，max_position_embeddings=512
# zace 侧 2048 token 假设见 Module/01 §2.4；本地候选的实际原生上限是 512，最终由 TASK-015 校准。
_LOCAL_CANDIDATES: tuple[LocalModelSpec, ...] = (
    LocalModelSpec(
        slug="multilingual-e5-small",
        repo_id="intfloat/multilingual-e5-small",
        onnx_file="onnx/model.onnx",
        dim=384,
        pooling="mean",
        query_prefix="query: ",
        passage_prefix="passage: ",
        notes="暂定默认；e5 系列必须带 query:/passage: 前缀，否则质量明显下降（卡内 §B）",
    ),
    LocalModelSpec(
        slug="bge-small-zh-v1.5",
        repo_id="Xenova/bge-small-zh-v1.5",
        onnx_file="onnx/model.onnx",
        dim=512,
        pooling="cls",
        notes="官方 BAAI 仓库未发布 ONNX 导出，这里指 transformers.js 镜像（含 tokenizer.json）",
    ),
    LocalModelSpec(
        slug="arctic-embed-xs",
        repo_id="Snowflake/snowflake-arctic-embed-xs",
        onnx_file="onnx/model.onnx",
        dim=384,
        pooling="cls",
        notes="英文对照基线（Background/04 §3：GitNexus 的本地 ONNX 先例，22M 参数 / 90MB）",
    ),
)

# HuggingFace 上另存的量化版本，供 TASK-015 对比耗时/显存时替换 onnx_file：
# - intfloat/multilingual-e5-small: onnx/model_qint8_avx512_vnni.onnx
# - Snowflake/snowflake-arctic-embed-xs: onnx/model_quantized.onnx
LOCAL_MODELS: dict[str, LocalModelSpec] = {spec.slug: spec for spec in _LOCAL_CANDIDATES}

API_MODELS: dict[str, ApiModelSpec] = {
    spec.name: spec
    for spec in (
        ApiModelSpec(
            name="bge-m3",
            dim=1024,
            max_input_tokens=8192,
            notes="TASK-015 的 API 对照候选",
        ),
        ApiModelSpec(name="text-embedding-3-small", dim=1536, max_input_tokens=8191),
        ApiModelSpec(name="text-embedding-3-large", dim=3072, max_input_tokens=8191),
    )
}


def get_local_spec(slug: str) -> LocalModelSpec:
    """按 slug 取本地模型条目；未登记时给出可用候选清单（可读错误）。"""
    try:
        return LOCAL_MODELS[slug]
    except KeyError:
        known = ", ".join(sorted(LOCAL_MODELS))
        raise EmbeddingConfigError(f"未登记的本地模型 slug: {slug!r}；可用候选：{known}") from None


def find_api_spec(name: str) -> ApiModelSpec | None:
    """按模型名取 API 条目；未登记返回 ``None``（由 factory 决定是否要求显式 dim）。"""
    return API_MODELS.get(name)
