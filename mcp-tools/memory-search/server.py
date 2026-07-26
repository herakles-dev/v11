#!/usr/bin/env python3
"""V11 MCP Server: Project Memory Search

Provides two MCP tools for semantic memory search:
- project_memory_search: Query project memory index
- project_memory_context: Get topic-focused context for agent injection

Runs as a stdio MCP server. Shells out to Python search scripts.
"""

import json
import os
import sys
from pathlib import Path

# Add V11 scripts lib to path
V11_HOME = os.environ.get("V11_HOME", os.path.expanduser("~/v11"))
_v11_from_env = "V11_HOME" in os.environ
_scripts_lib = os.path.join(V11_HOME, "scripts", "lib")
sys.path.insert(0, _scripts_lib)

# Startup diagnostic: warn if scripts lib is missing
if not os.path.isdir(_scripts_lib):
    print(
        f"[memory-search] WARNING: V11 scripts lib not found: {_scripts_lib}\n"
        f"  V11_HOME={V11_HOME} ({'from env' if _v11_from_env else 'default — set V11_HOME to override'})\n"
        f"  Search tools will fail. Run: export V11_HOME=/path/to/v11",
        file=sys.stderr,
    )

SESSIONS_ROOT = os.environ.get("SESSIONS_ROOT", os.path.expanduser("~/sessions"))
V11_WORKSPACE_ROOT = os.environ.get("V11_WORKSPACE_ROOT", os.path.expanduser("~"))


def get_index_path(project: str) -> Path:
    """Find memory index for a project."""
    candidates = [
        Path(SESSIONS_ROOT) / project / ".memory-index" / "memory.sqlite",
        Path(V11_WORKSPACE_ROOT) / project / ".memory-index" / "memory.sqlite",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]  # Default to sessions path


def handle_search(args: dict) -> dict:
    """Handle project_memory_search tool call."""
    from search import hybrid_search

    query = args.get("query", "")
    project = args.get("project", "")
    top_k = args.get("top_k", 5)
    sources = args.get("sources")

    if not query or not project:
        return {"error": "Both 'query' and 'project' are required"}

    db_path = get_index_path(project)
    if not db_path.exists():
        return {
            "error": f"No memory index found for project '{project}'",
            "hint": f"Run: ./scripts/index-project-memory {project}",
        }

    # Initialize embedder (optional, falls back to BM25-only)
    embedder = None
    try:
        from embedder import Embedder
        cache_dir = db_path.parent
        embedder = Embedder(model_name="auto", cache_dir=cache_dir)
    except Exception:
        pass

    results = hybrid_search(
        db_path, query, top_k=top_k,
        source_types=sources, embedder=embedder,
    )

    if embedder:
        embedder.close()

    return {
        "results": [
            {
                "source": r.source,
                "chunk": r.chunk,
                "score": r.score,
                "file": r.file,
                "lines": r.lines,
                "heading": r.heading,
            }
            for r in results
        ],
        "total": len(results),
        "backend": embedder.backend if embedder else "bm25-only",
    }


def handle_context(args: dict) -> dict:
    """Handle project_memory_context tool call."""
    from search import search_context

    project = args.get("project", "")
    topic = args.get("topic", "")
    max_tokens = args.get("max_tokens", 2000)

    if not project or not topic:
        return {"error": "Both 'project' and 'topic' are required"}

    db_path = get_index_path(project)
    if not db_path.exists():
        return {
            "error": f"No memory index found for project '{project}'",
            "hint": f"Run: ./scripts/index-project-memory {project}",
        }

    embedder = None
    try:
        from embedder import Embedder
        embedder = Embedder(model_name="auto", cache_dir=db_path.parent)
    except Exception:
        pass

    context = search_context(db_path, project, topic, max_tokens, embedder)

    if embedder:
        embedder.close()

    return {"context": context, "topic": topic, "project": project}


# MCP protocol implementation (stdio JSON-RPC)
TOOLS = {
    "project_memory_search": {
        "description": "Search project memory for relevant context. Returns ranked chunks from spec, tasks, notes, and artifacts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g., 'what authentication approach did we choose?')",
                },
                "project": {
                    "type": "string",
                    "description": "Project identifier (e.g., 'audio-suite')",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Max results to return (default: 5)",
                    "default": 5,
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by source types: spec, tasks, notes, artifacts, claude_md",
                },
            },
            "required": ["query", "project"],
        },
    },
    "project_memory_context": {
        "description": "Get topic-focused context text suitable for injection into agent prompts. Returns concatenated chunks with source citations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {
                    "type": "string",
                    "description": "Project identifier",
                },
                "topic": {
                    "type": "string",
                    "description": "Topic to retrieve context for (e.g., 'authentication decisions')",
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Maximum tokens in returned context (default: 2000)",
                    "default": 2000,
                },
            },
            "required": ["project", "topic"],
        },
    },
}


def handle_request(request: dict) -> dict:
    """Handle a JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "v11-memory-search",
                    "version": "1.0.0",
                },
            },
        }

    elif method == "notifications/initialized":
        return None  # No response for notifications

    elif method == "tools/list":
        tool_list = []
        for name, spec in TOOLS.items():
            tool_list.append({
                "name": name,
                "description": spec["description"],
                "inputSchema": spec["inputSchema"],
            })
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": tool_list},
        }

    elif method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})

        if tool_name == "project_memory_search":
            result = handle_search(tool_args)
        elif tool_name == "project_memory_context":
            result = handle_context(tool_args)
        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {"type": "text", "text": json.dumps(result, indent=2)}
                ]
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main():
    """Run MCP server on stdio."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            sys.stderr.write(f"Invalid JSON: {line}\n")
            continue

        response = handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
