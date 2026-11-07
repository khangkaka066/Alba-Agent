"""Text embedders for rollout diversity: a dependency-free lexical one, and the paper's sentence encoder run locally.

`LexicalEmbedder` needs nothing beyond the standard library, is deterministic and free, so it is the default and what the tests use.
`MiniLMOnnxEmbedder` runs all-MiniLM-L6-v2 (the encoder arXiv:2608.05643 uses for its redundancy analysis, Appendix A.6) through
onnxruntime. Its libraries (numpy, onnxruntime, tokenizers) are imported only when it is built, and the model files are never bundled
here: point it at a folder holding `model.onnx` and `tokenizer.json`.

Both return unit-length vectors. Cosine values are NOT comparable across embedders (see `diversity.py`).
"""

from __future__ import annotations

import importlib
import math
import re
import zlib
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol, cast

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_STOP = frozenset(
    "a an and are as at be been by for from has have had in is it its of on or that the this to was were with we i you they he she "
    "not but if then so than also can will would should do does did into over under such these those there their our your".split()
)


class EmbedderUnavailableError(RuntimeError):
    """The embedder cannot run here: a library or a model file is missing."""


class Embedder(Protocol):
    """`reliable_for_diversity` (optional, read with getattr, default True): False when the vectors cannot tell solution approaches apart."""

    name: str

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class LexicalEmbedder:
    """Hashed bag of words and word pairs with sub-linear term frequency and, by default, IDF over the batch.

    Batch IDF down-weights words that every rollout of the same problem shares (the problem's own vocabulary), which would otherwise
    make unrelated solutions look alike. The price: a vector depends on the batch it was embedded with.
    """

    reliable_for_diversity = False  # measured: adjusted Rand index 0.15 on unseen problems, against 0.5-0.6 for the sentence encoders

    def __init__(self, *, dims: int = 2048, bigrams: bool = True, batch_idf: bool = True) -> None:
        if dims < 16:
            raise ValueError("dims must be at least 16")
        self.name = "lexical-hash"
        self._dims, self._bigrams, self._batch_idf = dims, bigrams, batch_idf

    def _features(self, text: str) -> Counter[str]:
        words = [word for word in (item.lower() for item in _WORD.findall(text)) if word not in _STOP and (len(word) > 1 or word.isdigit())]
        counts: Counter[str] = Counter(words)
        if self._bigrams:
            counts.update(f"{left}_{right}" for left, right in zip(words, words[1:]))
        return counts

    def embed_sync(self, texts: Sequence[str]) -> list[list[float]]:
        features = [self._features(text) for text in texts]
        document_frequency: Counter[str] = Counter()
        for counts in features:
            document_frequency.update(counts.keys())
        total = len(features)
        vectors: list[list[float]] = []
        for counts in features:
            vector = [0.0] * self._dims
            for feature, count in counts.items():
                weight = 1.0 + math.log(count)
                if self._batch_idf and total > 1:
                    weight *= math.log((1 + total) / (1 + document_frequency[feature])) + 1.0
                vector[zlib.crc32(feature.encode("utf-8")) % self._dims] += weight
            norm = math.sqrt(sum(value * value for value in vector))
            vectors.append([value / norm for value in vector] if norm else vector)
        return vectors

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return self.embed_sync(texts)


class OnnxSentenceEmbedder:
    """A sentence encoder exported to ONNX, run on CPU with onnxruntime: mean or CLS pooling, L2-normalised.

    `model_dir` holds `model.onnx` and `tokenizer.json`. Texts longer than `max_tokens` are truncated (sentence-transformers' own
    default for the MiniLM family is 256).
    """

    reliable_for_diversity = True

    def __init__(self, model_dir: Path | str, *, pooling: str = "mean", max_tokens: int = 256, threads: int = 1, name: str = "onnx-sentence") -> None:
        if pooling not in ("mean", "cls"):
            raise ValueError("pooling must be 'mean' or 'cls'")
        directory = Path(model_dir)
        model_file, tokenizer_file = directory / "model.onnx", directory / "tokenizer.json"
        if not model_file.is_file() or not tokenizer_file.is_file():
            raise EmbedderUnavailableError(f"model.onnx and tokenizer.json are required in {directory}")
        try:
            self._np: Any = importlib.import_module("numpy")
            ort: Any = importlib.import_module("onnxruntime")
            tokenizers: Any = importlib.import_module("tokenizers")
        except ImportError as error:
            raise EmbedderUnavailableError("numpy, onnxruntime and tokenizers are required for ONNX embedders") from error
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self._session: Any = ort.InferenceSession(str(model_file), sess_options=options, providers=["CPUExecutionProvider"])
        self._input_names = {item.name for item in self._session.get_inputs()}
        self._tokenizer: Any = tokenizers.Tokenizer.from_file(str(tokenizer_file))
        self._tokenizer.enable_truncation(max_length=max_tokens)
        self._tokenizer.enable_padding()
        self._pooling = pooling
        self.name = name

    def embed_sync(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        np = self._np
        encoded = self._tokenizer.encode_batch(list(texts))
        ids = np.array([item.ids for item in encoded], dtype=np.int64)
        mask = np.array([item.attention_mask for item in encoded], dtype=np.int64)
        feed: dict[str, Any] = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._input_names:
            feed["token_type_ids"] = np.zeros_like(ids)
        hidden = self._session.run(None, feed)[0]
        if self._pooling == "cls":
            pooled = hidden[:, 0, :]
        else:
            weights = mask[:, :, None].astype(hidden.dtype)
            pooled = (hidden * weights).sum(axis=1) / np.maximum(weights.sum(axis=1), 1e-9)
        pooled = pooled / np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)
        return cast(list[list[float]], pooled.tolist())

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return self.embed_sync(texts)


class MiniLMOnnxEmbedder(OnnxSentenceEmbedder):
    """all-MiniLM-L6-v2 (384-d, mean pooling), the encoder arXiv:2608.05643 uses for its redundancy analysis."""

    def __init__(self, model_dir: Path | str, *, max_tokens: int = 256, threads: int = 1) -> None:
        super().__init__(model_dir, pooling="mean", max_tokens=max_tokens, threads=threads, name="minilm-l6-v2-onnx")
