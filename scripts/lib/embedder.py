"""V11 Memory Search: Vector embedding module.

Supports multiple backends with automatic fallback:
1. sentence-transformers (all-MiniLM-L6-v2) - best available
2. TF-IDF with numpy - always available fallback
3. None - BM25-only mode (no vector search)

Uses content-hash caching to avoid redundant computations.
"""

import os
import sys
from pathlib import Path
from typing import List, Optional

# Import cache
from cache import EmbeddingCache


class Embedder:
    """Unified embedding interface with fallback chain."""

    def __init__(self, model_name: str = "auto", cache_dir: Optional[Path] = None):
        self.model_name = model_name
        self.dims = 0
        self._model = None
        self._cache = None
        self._backend = "none"

        if cache_dir:
            cache_path = cache_dir / "embeddings.cache"
            self._cache = EmbeddingCache(cache_path)

        self._init_backend(model_name)

    def _init_backend(self, model_name: str):
        """Initialize the best available embedding backend."""
        if model_name == "none":
            self._backend = "none"
            return

        # Try sentence-transformers first
        if model_name in ("auto", "all-MiniLM-L6-v2", "embedding-gemma-300m"):
            try:
                from sentence_transformers import SentenceTransformer
                actual_model = "all-MiniLM-L6-v2" if model_name == "auto" else model_name
                self._model = SentenceTransformer(actual_model)
                self.dims = self._model.get_sentence_embedding_dimension()
                self._backend = "sentence-transformers"
                return
            except ImportError:
                pass

        # Fallback: TF-IDF with numpy
        if model_name in ("auto", "tfidf"):
            try:
                import numpy as np
                self._backend = "tfidf"
                self.dims = 512  # Fixed dimension for TF-IDF projection
                self._tfidf_vocab = {}
                return
            except ImportError:
                pass

        # No backend available
        self._backend = "none"

    def embed(self, text: str, content_hash: Optional[str] = None) -> Optional[List[float]]:
        """Generate embedding for text. Returns None if no backend available."""
        if self._backend == "none":
            return None

        # Check cache first (pass expected_dims to evict stale entries from old backends)
        if self._cache and content_hash:
            cached = self._cache.get(content_hash, expected_dims=self.dims)
            if cached is not None:
                return cached

        # Generate embedding
        embedding = None
        if self._backend == "sentence-transformers":
            embedding = self._embed_st(text)
        elif self._backend == "tfidf":
            embedding = self._embed_tfidf(text)

        # Cache result
        if embedding and self._cache and content_hash:
            self._cache.put(content_hash, embedding)

        return embedding

    def embed_batch(self, texts: List[str], content_hashes: Optional[List[str]] = None) -> List[Optional[List[float]]]:
        """Batch embed multiple texts."""
        results = []
        hashes = content_hashes or [None] * len(texts)

        if self._backend == "sentence-transformers" and self._model:
            # Check cache for all, embed only uncached
            uncached_indices = []
            uncached_texts = []

            for i, (text, h) in enumerate(zip(texts, hashes)):
                if self._cache and h:
                    cached = self._cache.get(h)
                    if cached is not None:
                        results.append(cached)
                        continue
                uncached_indices.append(i)
                uncached_texts.append(text)
                results.append(None)  # Placeholder

            if uncached_texts:
                embeddings = self._model.encode(uncached_texts, show_progress_bar=False)
                for idx, emb in zip(uncached_indices, embeddings):
                    emb_list = emb.tolist()
                    results[idx] = emb_list
                    if self._cache and hashes[idx]:
                        self._cache.put(hashes[idx], emb_list)
        else:
            # Fallback: embed one by one
            for text, h in zip(texts, hashes):
                results.append(self.embed(text, h))

        return results

    def _embed_st(self, text: str) -> List[float]:
        """Embed using sentence-transformers."""
        return self._model.encode(text, show_progress_bar=False).tolist()

    def _embed_tfidf(self, text: str) -> List[float]:
        """Simple TF-IDF-like embedding using numpy."""
        import numpy as np

        # Tokenize
        words = text.lower().split()
        if not words:
            return [0.0] * self.dims

        # Build/update vocabulary
        for w in words:
            if w not in self._tfidf_vocab:
                self._tfidf_vocab[w] = len(self._tfidf_vocab)

        # Create sparse term frequency vector
        tf = {}
        for w in words:
            idx = self._tfidf_vocab[w]
            tf[idx] = tf.get(idx, 0) + 1.0 / len(words)

        # Project to fixed dimension using simple hash projection
        vec = np.zeros(self.dims)
        for idx, freq in tf.items():
            # Deterministic hash to project sparse vector
            projected_idx = idx % self.dims
            vec[projected_idx] += freq

        # Normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        return vec.tolist()

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def cache_stats(self) -> dict:
        if self._cache:
            return self._cache.stats
        return {"total_cached": 0, "hit_rate": "N/A"}

    def close(self):
        if self._cache:
            self._cache.close()
