# V11 Memory Search Library
#
# Modules:
#   chunker  - Markdown-aware content chunking
#   cache    - Content-hash embedding cache (SQLite)
#   embedder - Vector embedding with fallback chain
#   bm25     - FTS5 BM25 keyword search
#   search   - Hybrid search (vector + BM25) with reranking
#
# Usage from scripts (after sys.path.insert):
#   from chunker import chunk_markdown, Chunk
#   from search import hybrid_search, search_context
#   from embedder import Embedder
#   from bm25 import search_bm25, BM25Result
#   from cache import EmbeddingCache

import os as _os
import sys as _sys

# Ensure this directory is on sys.path so bare imports work
_lib_dir = _os.path.dirname(_os.path.abspath(__file__))
if _lib_dir not in _sys.path:
    _sys.path.insert(0, _lib_dir)
