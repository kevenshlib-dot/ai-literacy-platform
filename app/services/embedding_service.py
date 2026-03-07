"""Embedding service - generates vector embeddings for text content.

Provides a pluggable embedding backend:
- Default (dev): simple hash-based 128-dim vectors for testing without ML deps
- Production: sentence-transformers with BGE model (BAAI/bge-small-zh-v1.5)
"""
import hashlib
import struct
import logging
from abc import ABC, abstractmethod

from app.core.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 128  # Dimension for development embeddings


class BaseEmbedder(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        raise NotImplementedError

    @property
    @abstractmethod
    def dim(self) -> int:
        """Return the embedding dimension."""
        raise NotImplementedError


class HashEmbedder(BaseEmbedder):
    """Development-only embedder using deterministic hash-based vectors.
    Produces consistent vectors for the same input text.
    Not for production use - swap with SentenceTransformerEmbedder.
    """

    @property
    def dim(self) -> int:
        return EMBEDDING_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            # Generate deterministic pseudo-random vector from text hash
            # Use bytes as unsigned ints, map to [-1, 1] range to avoid NaN
            raw = b""
            seed = text.encode("utf-8")
            while len(raw) < EMBEDDING_DIM:
                seed = hashlib.sha512(seed).digest()
                raw += seed

            vector = [(b / 255.0) * 2 - 1 for b in raw[:EMBEDDING_DIM]]
            # Normalize to unit vector
            norm = sum(v * v for v in vector) ** 0.5
            if norm > 0:
                vector = [v / norm for v in vector]
            results.append(vector)
        return results


# Singleton embedder
_embedder: BaseEmbedder = None


def get_embedder() -> BaseEmbedder:
    global _embedder
    if _embedder is None:
        _embedder = HashEmbedder()
        logger.info(f"Using HashEmbedder (dim={_embedder.dim}) for development")
    return _embedder


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts."""
    return get_embedder().embed(texts)


def get_embedding_dim() -> int:
    """Return the current embedding dimension."""
    return get_embedder().dim
