"""V11 Memory Search: Content-hash embedding cache.

Prevents redundant embedding computations by caching results
keyed on content hash. Uses a simple SQLite table.
"""

import sqlite3
import struct
from pathlib import Path
from typing import List, Optional


class EmbeddingCache:
    """Cache embeddings keyed by content hash in SQLite."""

    def __init__(self, cache_path: Path):
        self.conn = sqlite3.connect(str(cache_path))
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS embedding_cache (
                content_hash TEXT PRIMARY KEY,
                embedding BLOB NOT NULL,
                dims INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self.conn.commit()
        self._hits = 0
        self._misses = 0

    def get(self, content_hash: str, expected_dims: int = 0) -> Optional[List[float]]:
        """Retrieve cached embedding by content hash.

        If expected_dims > 0, entries with mismatched dimensions are treated as cache misses
        and evicted, preventing numpy shape errors when the embedder's dims change.
        """
        row = self.conn.execute(
            "SELECT embedding, dims FROM embedding_cache WHERE content_hash = ?",
            (content_hash,),
        ).fetchone()
        if row:
            stored_dims = row[1]
            if expected_dims > 0 and stored_dims != expected_dims:
                # Evict stale entry — dims changed (e.g. TF-IDF projection size updated)
                self.conn.execute(
                    "DELETE FROM embedding_cache WHERE content_hash = ?", (content_hash,)
                )
                self.conn.commit()
                self._misses += 1
                return None
            self._hits += 1
            return _blob_to_floats(row[0], stored_dims)
        self._misses += 1
        return None

    def put(self, content_hash: str, embedding: List[float]):
        """Store embedding in cache."""
        blob = _floats_to_blob(embedding)
        self.conn.execute(
            "INSERT OR REPLACE INTO embedding_cache (content_hash, embedding, dims) VALUES (?, ?, ?)",
            (content_hash, blob, len(embedding)),
        )
        self.conn.commit()

    def hit_rate(self) -> float:
        """Return cache hit rate."""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def stats(self) -> dict:
        total = self.conn.execute("SELECT COUNT(*) FROM embedding_cache").fetchone()[0]
        return {
            "total_cached": total,
            "session_hits": self._hits,
            "session_misses": self._misses,
            "hit_rate": f"{self.hit_rate():.1%}",
        }

    def close(self):
        self.conn.close()


def _floats_to_blob(floats: List[float]) -> bytes:
    """Pack float list into binary blob."""
    return struct.pack(f"{len(floats)}f", *floats)


def _blob_to_floats(blob: bytes, dims: int) -> List[float]:
    """Unpack binary blob into float list."""
    return list(struct.unpack(f"{dims}f", blob))
