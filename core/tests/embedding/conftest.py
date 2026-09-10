"""TASK-008 测试公共夹具：微型 tokenizer（本地文件，无网络）+ ONNX 会话替身。

设计原则（卡内 DoD）：CI 不依赖网络与真实模型文件，因此
- tokenizer 用 ``tokenizers`` 现场构造的微型 WordLevel 词表，写进 tmp 目录后按生产路径加载；
- ONNX 会话用 stub 替身（token id → one-hot 行向量），把"池化/归一化/批切分"的数学行为
  变成可判定断言，而不必下载 90MB+ 的真实模型。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from tokenizers import Tokenizer, models, pre_tokenizers, processors

#: 微型词表：覆盖 e5 前缀 token、中英文样例词与特殊符号。
TINY_VOCAB: dict[str, int] = {
    "[PAD]": 0,
    "[UNK]": 1,
    "[CLS]": 2,
    "[SEP]": 3,
    "hello": 4,
    "world": 5,
    "token": 6,
    "过期": 7,
    "刷新": 8,
    "def": 9,
    "pass": 10,
    "query:": 11,
    "passage:": 12,
    "passage": 13,
    "query": 14,
    ":": 15,
}

#: 特殊 token id（断言 CLS 池化时使用）。
CLS_ID = TINY_VOCAB["[CLS]"]
PAD_ID = TINY_VOCAB["[PAD]"]


def build_tiny_tokenizer(path: Path) -> Path:
    """写一个带 [CLS]/[SEP] 后处理的微型 tokenizer.json（等价生产加载路径）。"""
    tokenizer = Tokenizer(models.WordLevel(vocab=TINY_VOCAB, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    tokenizer.post_processor = processors.TemplateProcessing(
        single="[CLS] $A [SEP]",
        pair="[CLS] $A [SEP] $B:1 [SEP]:1",
        special_tokens=[("[CLS]", CLS_ID), ("[SEP]", TINY_VOCAB["[SEP]"])],
    )
    tokenizer.save(str(path))
    return path


class StubOnnxSession:
    """``onnxruntime.InferenceSession`` 替身：每个 token id → 一维 one-hot 行向量。

    ``pooled=True`` 时直接返回二维输出，模拟"导出时已池化"的 ONNX 包。
    """

    def __init__(
        self,
        *,
        dim: int = 32,
        input_names: tuple[str, ...] = ("input_ids", "attention_mask"),
        pooled: bool = False,
    ) -> None:
        self.dim = dim
        self.input_names = tuple(input_names)
        self.pooled = pooled
        self.feeds: list[dict[str, np.ndarray]] = []

    def get_inputs(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(name=name) for name in self.input_names]

    def run(
        self, output_names: Any, input_feed: dict[str, np.ndarray]
    ) -> list[np.ndarray]:
        self.feeds.append(dict(input_feed))
        ids = np.asarray(input_feed["input_ids"])
        if self.pooled:
            pooled = np.zeros((ids.shape[0], self.dim), dtype=np.float32)
            for row in range(ids.shape[0]):
                pooled[row, int(ids[row, 0]) % self.dim] = 1.0
            return [pooled]
        hidden = np.zeros((*ids.shape, self.dim), dtype=np.float32)
        for row in range(ids.shape[0]):
            for col in range(ids.shape[1]):
                hidden[row, col, int(ids[row, col]) % self.dim] = 1.0
        return [hidden]


class RecordingTokenizer:
    """包装真实 tokenizer，记录 ``encode_batch`` 收到的原文（断言前缀注入）。"""

    def __init__(self, inner: Tokenizer) -> None:
        self._inner = inner
        self.batches: list[list[str]] = []

    def encode_batch(
        self, texts: list[str], add_special_tokens: bool = True
    ) -> list[Any]:
        self.batches.append(list(texts))
        return self._inner.encode_batch(texts, add_special_tokens=add_special_tokens)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def one_hot_rows(ids: list[int], dim: int) -> np.ndarray:
    """与 stub 会话一致的 one-hot 行（测试侧独立重算期望值）。"""
    rows = np.zeros((len(ids), dim), dtype=np.float32)
    for index, token_id in enumerate(ids):
        rows[index, token_id % dim] = 1.0
    return rows


@pytest.fixture(scope="session")
def tiny_tokenizer_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("tiny-tokenizer")
    return build_tiny_tokenizer(directory / "tokenizer.json")


@pytest.fixture
def tokenizer(tiny_tokenizer_path: Path) -> Tokenizer:
    return Tokenizer.from_file(str(tiny_tokenizer_path))


@pytest.fixture
def model_dir(tmp_path: Path, tiny_tokenizer_path: Path) -> Path:
    """伪造本地模型目录：只放 tokenizer.json（ONNX 用注入 session，避免大文件）。"""
    target = tmp_path / "model"
    target.mkdir()
    (target / "tokenizer.json").write_bytes(tiny_tokenizer_path.read_bytes())
    return target


@pytest.fixture
def padded_tokenizer_path(tmp_path: Path, tiny_tokenizer_path: Path) -> Path:
    """带 padding 的 tokenizer.json（回归真机发现：arctic 仓库自带 batch 级 padding）。"""
    tokenizer = Tokenizer.from_file(str(tiny_tokenizer_path))
    tokenizer.enable_padding(pad_id=PAD_ID, pad_token="[PAD]")
    path = tmp_path / "tokenizer-padded.json"
    tokenizer.save(str(path))
    return path


@pytest.fixture
def padded_tokenizer(padded_tokenizer_path: Path) -> Tokenizer:
    return Tokenizer.from_file(str(padded_tokenizer_path))
