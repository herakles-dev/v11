"""V11 Memory Search: Hybrid search (70% vector + 30% BM25) with reranking.

Combines vector similarity search with BM25 keyword search,
then optionally reranks results for higher accuracy.
Target: <200ms search latency.
"""

import json
import sqlite3
import struct
import time
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

from bm25 import BM25Result, search_bm25


class SearchResult(NamedTuple):
    source: str       # Source type (spec, tasks, notes, etc.)
    chunk: str        # Chunk text
    score: float      # Combined score (0-1)
    file: str         # File path
    lines: str        # "start-end"
    source_type: str  # Source type
    heading: str      # Nearest heading


def hybrid_search(
    db_path: Path,
    query: str,
    top_k: int = 5,
    source_types: Optional[List[str]] = None,
    vector_weight: float = 0.7,
    bm25_weight: float = 0.3,
    embedder=None,
    rerank: bool = False,
) -> List[SearchResult]:
    """Perform hybrid vector + BM25 search.

    Args:
        db_path: Path to memory.sqlite
        query: Search query string
        top_k: Number of results to return
        source_types: Filter by source type
        vector_weight: Weight for vector search (default 0.7)
        bm25_weight: Weight for BM25 search (default 0.3)
        embedder: Embedder instance (None = BM25-only mode)
        rerank: Enable reranking step

    Returns:
        List of SearchResult sorted by combined score
    """
    if not query.strip():
        return []

    conn = sqlite3.connect(str(db_path))

    # Phase 1: BM25 search
    bm25_results = search_bm25(conn, query, top_k=top_k * 3, source_types=source_types)

    # Phase 2: Vector search (if embedder available)
    vector_scores: Dict[int, float] = {}
    if embedder and embedder.backend != "none":
        query_embedding = embedder.embed(query)
        if query_embedding:
            vector_scores = _vector_search(
                conn, query_embedding, top_k=top_k * 3, source_types=source_types
            )

    # Phase 3: Merge scores (pass conn so vector-only results can be hydrated)
    merged = _merge_scores(
        bm25_results, vector_scores,
        vector_weight=vector_weight,
        bm25_weight=bm25_weight,
        conn=conn,
        source_types=source_types,
    )

    # Phase 4: Optional reranking
    if rerank and len(merged) > top_k:
        merged = _rerank(merged, query)

    # Convert to SearchResult and limit
    results = []
    for item in merged[:top_k]:
        results.append(SearchResult(
            source=item["source_type"],
            chunk=item["chunk_text"],
            score=round(item["score"], 4),
            file=item["file_path"],
            lines=f"{item['line_start']}-{item['line_end']}",
            source_type=item["source_type"],
            heading=item.get("heading", ""),
        ))

    conn.close()
    return results


def _vector_search(
    conn: sqlite3.Connection,
    query_embedding: List[float],
    top_k: int = 15,
    source_types: Optional[List[str]] = None,
) -> Dict[int, float]:
    """Search by vector cosine similarity. Returns {chunk_id: score}."""
    import numpy as np

    query_vec = np.array(query_embedding, dtype=np.float32)
    query_norm = np.linalg.norm(query_vec)
    if query_norm == 0:
        return {}

    query_vec = query_vec / query_norm

    # Fetch all embeddings (for small indices this is fast enough)
    if source_types:
        placeholders = ",".join("?" for _ in source_types)
        sql = f"SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL AND source_type IN ({placeholders})"
        rows = conn.execute(sql, source_types).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL"
        ).fetchall()

    scores = {}
    for row_id, emb_blob in rows:
        if not emb_blob:
            continue
        dims = len(emb_blob) // 4  # float32 = 4 bytes
        emb = np.array(struct.unpack(f"{dims}f", emb_blob), dtype=np.float32)
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        similarity = float(np.dot(query_vec, emb))
        scores[row_id] = max(0.0, similarity)  # Clamp negatives

    # Return top_k
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return dict(sorted_scores[:top_k])


def _merge_scores(
    bm25_results: List[BM25Result],
    vector_scores: Dict[int, float],
    vector_weight: float = 0.7,
    bm25_weight: float = 0.3,
    conn: Optional["sqlite3.Connection"] = None,
    source_types: Optional[List[str]] = None,
) -> List[dict]:
    """Merge BM25 and vector scores with weighted combination."""
    # Build unified result map
    results: Dict[int, dict] = {}

    # Add BM25 results
    for r in bm25_results:
        results[r.chunk_id] = {
            "chunk_id": r.chunk_id,
            "chunk_text": r.chunk_text,
            "file_path": r.file_path,
            "line_start": r.line_start,
            "line_end": r.line_end,
            "heading": r.heading,
            "source_type": r.source_type,
            "bm25_score": r.score,
            "vector_score": 0.0,
            "score": 0.0,
        }

    # Add vector scores — hydrate vector-only results from DB
    vector_only_ids = [cid for cid in vector_scores if cid not in results]
    if vector_only_ids and conn is not None:
        placeholders = ",".join("?" for _ in vector_only_ids)
        sql = (
            f"SELECT id, chunk_text, file_path, line_start, line_end, heading, source_type "
            f"FROM chunks WHERE id IN ({placeholders})"
        )
        rows = conn.execute(sql, vector_only_ids).fetchall()
        for row in rows:
            cid, chunk_text, file_path, line_start, line_end, heading, source_type = row
            if source_types and source_type not in source_types:
                continue
            results[cid] = {
                "chunk_id": cid,
                "chunk_text": chunk_text or "",
                "file_path": file_path or "",
                "line_start": line_start or 0,
                "line_end": line_end or 0,
                "heading": heading or "",
                "source_type": source_type or "",
                "bm25_score": 0.0,
                "vector_score": 0.0,
                "score": 0.0,
            }

    for chunk_id, vscore in vector_scores.items():
        if chunk_id in results:
            results[chunk_id]["vector_score"] = vscore

    # Compute combined score
    has_vectors = bool(vector_scores)
    for item in results.values():
        if has_vectors:
            item["score"] = (
                vector_weight * item["vector_score"]
                + bm25_weight * item["bm25_score"]
            )
        else:
            # BM25-only mode
            item["score"] = item["bm25_score"]

    # Sort by combined score
    sorted_results = sorted(results.values(), key=lambda x: x["score"], reverse=True)
    return sorted_results


def _rerank(results: List[dict], query: str) -> List[dict]:
    """Simple reranking based on query term density in chunk text.

    For more sophisticated reranking, a cross-encoder model could be used,
    but this lightweight approach adds minimal latency.
    """
    query_terms = set(query.lower().split())

    for item in results:
        chunk_lower = item["chunk_text"].lower()
        chunk_words = set(chunk_lower.split())

        # Term overlap ratio
        overlap = len(query_terms & chunk_words) / max(len(query_terms), 1)

        # Exact phrase bonus
        phrase_bonus = 0.1 if query.lower() in chunk_lower else 0.0

        # Heading match bonus
        heading_bonus = 0.05 if any(
            t in item.get("heading", "").lower() for t in query_terms
        ) else 0.0

        # Rerank score = 80% original + 20% rerank signals
        item["score"] = 0.8 * item["score"] + 0.2 * (overlap + phrase_bonus + heading_bonus)

    return sorted(results, key=lambda x: x["score"], reverse=True)


def search_context(
    db_path: Path,
    project: str,
    topic: str,
    max_tokens: int = 2000,
    embedder=None,
) -> str:
    """Get context text for a topic, suitable for injection into agent prompts.

    Returns concatenated chunks up to max_tokens, formatted with source citations.
    Results injected at START of context per Lost-in-Middle research.
    """
    results = hybrid_search(
        db_path, topic, top_k=10, embedder=embedder
    )

    if not results:
        return f"No memory found for: {topic}"

    context_parts = []
    token_count = 0
    chars_per_token = 4

    for r in results:
        chunk_tokens = len(r.chunk) // chars_per_token
        if token_count + chunk_tokens > max_tokens:
            break

        source_label = f"[{r.source_type}:{r.file}:{r.lines}]"
        context_parts.append(f"{source_label}\n{r.chunk}")
        token_count += chunk_tokens

    return "\n\n---\n\n".join(context_parts)
