"""V11 Memory Search: BM25 keyword search via SQLite FTS5.

FTS5 provides built-in BM25 ranking with porter stemming.
This module wraps FTS5 queries with score normalization.
"""

import sqlite3
from typing import List, NamedTuple, Optional


class BM25Result(NamedTuple):
    chunk_id: int
    score: float
    chunk_text: str
    file_path: str
    line_start: int
    line_end: int
    heading: str
    source_type: str


def search_bm25(
    conn: sqlite3.Connection,
    query: str,
    top_k: int = 10,
    source_types: Optional[List[str]] = None,
) -> List[BM25Result]:
    """Search chunks using FTS5 BM25 ranking.

    Args:
        conn: SQLite connection with FTS5 tables
        query: Search query (supports FTS5 syntax: AND, OR, NOT, phrases)
        top_k: Maximum results to return
        source_types: Filter by source type (spec, tasks, notes, etc.)

    Returns:
        List of BM25Result sorted by relevance score (higher = better)
    """
    if not query.strip():
        return []

    # Sanitize query for FTS5 (escape special chars)
    safe_query = _sanitize_fts_query(query)
    if not safe_query:
        return []

    # Build query with optional source type filter
    if source_types:
        placeholders = ",".join("?" for _ in source_types)
        sql = f"""
            SELECT
                c.id, -rank as score,
                c.chunk_text, c.file_path,
                c.line_start, c.line_end,
                c.heading, c.source_type
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            WHERE chunks_fts MATCH ?
              AND c.source_type IN ({placeholders})
            ORDER BY rank
            LIMIT ?
        """
        params = [safe_query] + source_types + [top_k]
    else:
        sql = """
            SELECT
                c.id, -rank as score,
                c.chunk_text, c.file_path,
                c.line_start, c.line_end,
                c.heading, c.source_type
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            WHERE chunks_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        params = [safe_query, top_k]

    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        # Query syntax error — try simpler approach
        simple_query = " OR ".join(
            f'"{w}"' for w in query.split() if w.strip()
        )
        if not simple_query:
            return []
        params[0] = simple_query
        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []

    if not rows:
        return []

    # Normalize scores to 0-1 range
    max_score = max(r[1] for r in rows) if rows else 1.0
    if max_score <= 0:
        max_score = 1.0

    results = []
    for row in rows:
        results.append(BM25Result(
            chunk_id=row[0],
            score=row[1] / max_score,  # Normalize to 0-1
            chunk_text=row[2],
            file_path=row[3],
            line_start=row[4],
            line_end=row[5],
            heading=row[6],
            source_type=row[7],
        ))

    return results


def _sanitize_fts_query(query: str) -> str:
    """Sanitize a query string for FTS5.

    Wraps individual words in quotes to prevent FTS5 syntax errors.
    Preserves explicit AND/OR/NOT operators.
    """
    words = query.split()
    safe_parts = []

    for word in words:
        upper = word.upper()
        if upper in ("AND", "OR", "NOT"):
            safe_parts.append(upper)
        elif word.startswith('"') and word.endswith('"'):
            safe_parts.append(word)  # Already quoted
        else:
            # Remove FTS5 special chars
            clean = word.replace("*", "").replace("(", "").replace(")", "")
            clean = clean.replace("{", "").replace("}", "").replace(":", "")
            if clean:
                safe_parts.append(f'"{clean}"')

    return " ".join(safe_parts)
