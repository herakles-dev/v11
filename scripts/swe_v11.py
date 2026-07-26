#!/usr/bin/env python3
"""
SWE-bench V11 Multi-Agent Formation Orchestrator (Phase 10.2).

Implements the V11 'swebench-solver' formation: a 3-wave pipeline using
Claude Sonnet 4.6 with role-specific system prompts that mirror V11's
spec-architect-v11 → spec-implementer-v11 → spec-tester-v11 agents.

Architecture:
  Wave 0: INVESTIGATOR (spec-architect-v11 prompt)
    - Reads issue + repo file tree
    - Identifies root cause + top target files
    - Outputs artifact: { hypothesis, target_files, complexity }

  Wave 1: IMPLEMENTER (spec-implementer-v11 prompt)
    - Reads investigator artifact + target file contents
    - Generates FIND/REPLACE patch
    - Outputs artifact: { patch, confidence, reasoning }

  Wave 2: VALIDATOR  (spec-tester-v11 prompt, + real test execution)
    - Applies patch + runs FAIL_TO_PASS tests
    - If tests fail → sends error back to implementer (max 3 loops)
    - Outputs final patch

Usage:
    python3 swe_v11.py --num 10                     # first 10 instances
    python3 swe_v11.py --num 50 --repo-filter django # pilot run
    python3 swe_v11.py --num 300 --max-attempts 3   # full run
    python3 swe_v11.py --instance-ids astropy__astropy-12907
    python3 swe_v11.py --list                        # list instances
    python3 swe_v11.py --report                      # show results

Output: swebench-predictions/v11-formation/{instance_id}.json
Traces: swebench-predictions/v11-formation/trajs/{instance_id}.jsonl
Combined: swebench-predictions/v11-formation/all_preds.jsonl
"""

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

# ── deps ─────────────────────────────────────────────────────────────────────

try:
    import anthropic
except ImportError:
    sys.exit("Install anthropic: pip install anthropic")

try:
    from datasets import load_dataset
except ImportError:
    sys.exit("Install datasets: pip install datasets")

# ── config ────────────────────────────────────────────────────────────────────

CLAUDE_MODEL    = "claude-sonnet-4-6"
REPO_CACHE_DIR  = Path(os.path.expanduser("~/v11/swebench-repos"))
PRED_DIR        = Path(os.path.expanduser("~/v11/swebench-predictions/v11-formation"))
TRAJ_DIR        = PRED_DIR / "trajs"
MAX_CONTEXT_CHARS = 100_000
MAX_FILE_CHARS    = 20_000
MAX_FILE_LINES    = 600
MAX_FILES         = 5
DEFAULT_MAX_ATTEMPTS = 3
RETRY_DELAY       = 10
REQUEST_DELAY     = 1.0

# ── Wave 0: Investigator (spec-architect-v11 role) ────────────────────────────

INVESTIGATOR_SYSTEM = """\
You are an expert software investigator (V11 spec-architect-v11 role).

Your task is to analyze a GitHub issue and identify EXACTLY which source files need to change
AND provide a concrete implementation strategy for the fix.

Analyze the issue and output a JSON object (ONLY JSON, no prose):
{
  "hypothesis": "one sentence describing root cause",
  "target_files": ["path/to/most/likely/file.py", "path/to/second/file.py"],
  "fix_strategy": "Concrete code-level steps: e.g. 'In method get_order_by() around line 43, before calling ordering_parts.search(sql), add: sql = sql.replace(chr(10), chr(32)) to collapse newlines. This ensures the regex matches the full SQL not just the last line.'",
  "complexity": "routine|medium|complex|novel",
  "reasoning": "brief explanation of why these files"
}

Rules:
- target_files must be relative paths from repo root (e.g. "django/db/models/query.py")
- List at most 3 files, ordered by likelihood of needing changes
- fix_strategy must be ACTIONABLE: name the function, describe the exact code change, not just "fix the bug"
- complexity: routine=boilerplate fix, medium=known pattern, complex=subtle logic, novel=new territory
- Output ONLY the JSON object, nothing else\
"""

INVESTIGATOR_TEMPLATE = """\
## GitHub Issue

{problem_statement}

## Repository File Tree (relevant portion)

{file_tree}

## FAIL_TO_PASS Test Hints

{fail_to_pass}

Identify the root cause and target files. Output JSON only.
"""

# ── Wave 0: Agentic Investigator Tools ────────────────────────────────────────

INVESTIGATOR_TOOLS = [
    {
        "name": "grep_code",
        "description": "Search code in the repository using git grep. Returns matching lines with file paths and line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex/literal pattern to search for"},
                "path": {"type": "string", "description": "Optional subdirectory to limit search (e.g. 'django/db/')"},
                "case_insensitive": {"type": "boolean", "description": "Case-insensitive search", "default": False},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the repository, optionally a specific line range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to repo root (e.g. 'django/db/models/sql/compiler.py')"},
                "start_line": {"type": "integer", "description": "First line to read (1-indexed)"},
                "end_line": {"type": "integer", "description": "Last line to read (inclusive)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "search_files",
        "description": "Find files by name pattern (find -name). Returns matching file paths.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Filename pattern (e.g. 'compiler.py', 'storage*.py')"},
                "exclude_tests": {"type": "boolean", "description": "Exclude test files", "default": True},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "git_log",
        "description": "Show recent git commits for a file to understand change history.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to show log for"},
                "n": {"type": "integer", "description": "Number of commits to show", "default": 5},
            },
            "required": ["path"],
        },
    },
]

# ── Wave 1: Implementer (spec-implementer-v11 role) ───────────────────────────

IMPLEMENTER_SYSTEM = """\
You are an expert software implementer (V11 spec-implementer-v11 role).

You receive an investigation artifact identifying the root cause of a GitHub issue,
plus the relevant source files. Generate a patch to fix the issue.

Output ONLY code edit blocks in this exact format — one block per change:

<<<< FILE: path/to/file.py
FIND:
(exact lines to find, verbatim, including indentation)
REPLACE:
(replacement lines)
>>>>

Rules:
- FIND must match EXACTLY what appears in the file (copy verbatim from the provided source).
- Make the FIND section as short as possible while still being unique (3–8 lines max).
- Do NOT add new test functions or test classes — fix the production source code that makes tests pass.
- Do NOT modify test files unless the Fix Strategy explicitly says to.
- Address the root cause identified by the investigator.
- Output NOTHING else — no explanation, no prose, just the edit blocks.\
"""

IMPLEMENTER_TEMPLATE = """\
## Investigation Artifact

Hypothesis: {hypothesis}
Complexity: {complexity}
Reasoning: {reasoning}

## Fix Strategy (FOLLOW THIS EXACTLY)

{fix_strategy}

## GitHub Issue

{problem_statement}

## Tests That Must Pass

{test_context}

## Target Source Files (with line numbers)

{file_context}

## Task

Implement the Fix Strategy above. Use FIND/REPLACE format.
Copy FIND lines verbatim from the source (line numbers shown but do NOT include them in FIND).
"""

IMPLEMENTER_REVISE_TEMPLATE = """\
## Previous Patch (attempt {attempt})

{previous_patch}

## Validator Feedback

{error_context}

## Fix Strategy (re-read carefully)

{fix_strategy}

## GitHub Issue (reminder)

{problem_statement}

## Tests That Must Pass

{test_context}

## Target Source Files (with line numbers)

{file_context}

## Task

The previous patch did not resolve the tests. Reconsider the Fix Strategy above and generate
a revised patch. Common mistakes to avoid:
- Changing config flags when the real fix is in the calling code
- FIND text that doesn't exactly match the source (check indentation and spacing)
- Fixing the wrong method or file
Use FIND/REPLACE format. Copy FIND lines verbatim from the source above.
"""

# ── helpers (shared with swe_infer.py logic) ─────────────────────────────────

def load_lite_dataset() -> list[dict]:
    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    return [dict(row) for row in ds]


def clone_or_update_repo(repo: str, base_commit: str) -> Optional[Path]:
    """Clone repo if not present, checkout base_commit."""
    org, name = repo.split("/")
    local = REPO_CACHE_DIR / name
    if not local.exists():
        print(f"  Cloning {repo}...")
        r = subprocess.run(
            ["git", "clone", "--depth=500", f"https://github.com/{repo}.git", str(local)],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            print(f"  Clone failed: {r.stderr[:200]}")
            return None
    result = subprocess.run(
        ["git", "-C", str(local), "cat-file", "-t", base_commit],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        # Try a deeper fetch first
        subprocess.run(
            ["git", "-C", str(local), "fetch", "--depth=500", "origin"],
            capture_output=True, text=True, timeout=60,
        )
        result2 = subprocess.run(
            ["git", "-C", str(local), "cat-file", "-t", base_commit],
            capture_output=True, text=True,
        )
        if result2.returncode != 0:
            # Commit not found even after depth-500 fetch — unshallow the repo
            print(f"  Commit {base_commit[:8]} not found, fetching full history...")
            subprocess.run(
                ["git", "-C", str(local), "fetch", "--unshallow", "origin"],
                capture_output=True, text=True, timeout=300,
            )
    subprocess.run(
        ["git", "-C", str(local), "checkout", base_commit, "--force"],
        capture_output=True, text=True, timeout=30,
    )
    return local


def extract_keywords(text: str, n: int = 15) -> list[str]:
    words = re.findall(r'\b[A-Za-z_][A-Za-z0-9_]{3,}\b', text)
    scored = {}
    for w in words:
        score = 1
        if '_' in w or (w[0].isupper() and any(c.islower() for c in w)):
            score = 3
        scored[w] = scored.get(w, 0) + score
    top = sorted(scored, key=lambda x: -scored[x])
    return top[:n]


def find_relevant_files(repo_path: Path, issue_text: str,
                        fail_to_pass: list[str] = None,
                        investigator_files: list[str] = None) -> list[Path]:
    """
    Enhanced file discovery for the V11 formation.
    Adds a Wave 0 priority: if investigator_files are provided, try those first.
    Falls back to keyword search if investigator files don't exist.
    """
    file_scores: dict[Path, int] = {}
    code_exts = {'.py', '.js', '.ts', '.rb', '.go', '.java', '.c', '.cpp'}

    # Wave 0 boost: investigator-identified files get highest priority
    if investigator_files:
        for rel_path in investigator_files:
            p = repo_path / rel_path.lstrip('/')
            if p.exists() and p.suffix in code_exts:
                file_scores[p] = file_scores.get(p, 0) + 50  # very high score
                print(f"  Investigator target: {rel_path}")
            elif not p.exists() and p.suffix == '.py':
                # File may have been refactored into a package directory
                pkg_dir = p.parent / p.stem
                if pkg_dir.is_dir():
                    # Try __init__.py first (common package entry point)
                    init = pkg_dir / '__init__.py'
                    if init.exists():
                        file_scores[init] = file_scores.get(init, 0) + 40
                        print(f"  Investigator target (→ package __init__): {init.relative_to(repo_path)}")
                    # Also score other .py files in the package
                    for candidate in sorted(pkg_dir.glob('*.py')):
                        if candidate != init:
                            file_scores[candidate] = file_scores.get(candidate, 0) + 20
                    if not init.exists():
                        print(f"  Investigator target '{rel_path}' not found; scored package dir {pkg_dir.name}/")
                else:
                    print(f"  Investigator target '{rel_path}' not found in repo (skipping)")

    # FAIL_TO_PASS hint strategy
    if fail_to_pass:
        for test_id in fail_to_pass[:5]:
            if "::" in test_id and ".py" in test_id:
                test_file_rel = test_id.split("::")[0]
                test_path = repo_path / test_file_rel
                src_rel = re.sub(r'/tests/test_', '/', test_file_rel)
                src_path = repo_path / src_rel
                if src_path.exists() and src_path.suffix in code_exts:
                    file_scores[src_path] = file_scores.get(src_path, 0) + 10
                if test_path.exists():
                    file_scores[test_path] = file_scores.get(test_path, 0) + 3
            else:
                func_name = test_id.strip()
                try:
                    r = subprocess.run(
                        ["git", "-C", str(repo_path), "grep", "-l",
                         f"def {func_name}", "--", "*/tests/*.py", "*/test_*.py"],
                        capture_output=True, text=True, timeout=8,
                    )
                    test_hits = r.stdout.splitlines()
                    for line in test_hits:
                        test_file_rel = line.strip()
                        test_path = repo_path / test_file_rel
                        if test_path.exists():
                            file_scores[test_path] = file_scores.get(test_path, 0) + 3
                        src_rel = re.sub(r'/tests/test_', '/', test_file_rel)
                        src_path = repo_path / src_rel
                        if src_path.exists() and src_path.suffix in code_exts:
                            specificity_bonus = max(0, 10 - len(test_hits))
                            file_scores[src_path] = file_scores.get(src_path, 0) + 15 + specificity_bonus
                except subprocess.TimeoutExpired:
                    pass

                clean = re.sub(r'^test_?', '', func_name)
                clean = re.sub(r'_test$', '', clean)
                if len(clean) >= 3:
                    try:
                        r = subprocess.run(
                            ["find", str(repo_path), "-name", f"*{clean}*",
                             "-not", "-path", "*/test*", "-not", "-path", "*/.git/*"],
                            capture_output=True, text=True, timeout=5,
                        )
                        for line in r.stdout.splitlines():
                            p = Path(line.strip())
                            if p.suffix in code_exts and p.exists():
                                file_scores[p] = file_scores.get(p, 0) + 5
                    except subprocess.TimeoutExpired:
                        pass

    # Keyword grep fallback
    keywords = extract_keywords(issue_text)
    for kw in keywords[:10]:
        try:
            r = subprocess.run(
                ["git", "-C", str(repo_path), "grep", "-l", "--", kw],
                capture_output=True, text=True, timeout=10,
            )
            for line in r.stdout.splitlines():
                p = repo_path / line.strip()
                if p.suffix in code_exts:
                    name_bonus = 2 if any(kw.lower() in p.stem.lower() for kw in keywords[:5]) else 0
                    test_penalty = -1 if "test" in str(p).lower() else 0
                    file_scores[p] = file_scores.get(p, 0) + 1 + name_bonus + test_penalty
        except subprocess.TimeoutExpired:
            continue

    if not file_scores:
        return []

    ranked = sorted(file_scores, key=lambda p: (-file_scores[p], len(str(p))))
    impl = [p for p in ranked if "test" not in str(p).lower()]
    tests = [p for p in ranked if "test" in str(p).lower()]
    return (impl[:4] + tests[:1])[:MAX_FILES]


def read_file_context(files: list[Path], repo_path: Path) -> str:
    """Format file contents with line numbers for model context."""
    parts = []
    total = 0
    for f in files:
        try:
            raw = f.read_text(errors='replace')
            lines = raw.splitlines()[:MAX_FILE_LINES]
            numbered = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(lines))
            if len(numbered) > MAX_FILE_CHARS:
                numbered = numbered[:MAX_FILE_CHARS] + "\n... (truncated)"
            rel = f.relative_to(repo_path)
            parts.append(f"### {rel}\n```\n{numbered}\n```\n")
            total += len(numbered)
            if total > MAX_CONTEXT_CHARS:
                break
        except Exception:
            continue
    return "\n".join(parts) if parts else "(no relevant files found)"


def get_file_tree(repo_path: Path, max_lines: int = 200) -> str:
    """Get a condensed file tree for the repo (Python files only)."""
    try:
        r = subprocess.run(
            ["find", str(repo_path), "-name", "*.py",
             "-not", "-path", "*/.git/*",
             "-not", "-path", "*/node_modules/*",
             "-not", "-path", "*/__pycache__/*"],
            capture_output=True, text=True, timeout=10,
        )
        lines = sorted(r.stdout.splitlines())
        # Make relative
        rel_lines = []
        for line in lines:
            try:
                rel = Path(line).relative_to(repo_path)
                rel_lines.append(str(rel))
            except ValueError:
                pass
        if len(rel_lines) > max_lines:
            rel_lines = rel_lines[:max_lines] + [f"... ({len(rel_lines) - max_lines} more files)"]
        return "\n".join(rel_lines)
    except Exception:
        return "(file tree unavailable)"


LINE_NUM_RE = re.compile(r'^\s*\d+\s*\|\s?', re.MULTILINE)


def strip_line_numbers(text: str) -> str:
    return LINE_NUM_RE.sub('', text)


def apply_edit_blocks(raw_response: str, repo_path: Path,
                       allowed_files: list[str] | None = None) -> str:
    """Parse FIND/REPLACE edit blocks and convert to unified diff."""
    if not raw_response:
        return ""

    import difflib

    unwrapped = re.sub(r'^```[a-z]*\n', '', raw_response, flags=re.MULTILINE)
    unwrapped = re.sub(r'\n```$', '', unwrapped.strip())

    pattern = re.compile(
        r'<{4}\s*FILE:\s*([^\n]+)\nFIND:\n(.*?)\nREPLACE:\n(.*?)(?:\n>{4}|(?=\n<{4})|$)',
        re.DOTALL,
    )
    blocks = pattern.findall(unwrapped)
    if not blocks:
        return ""

    diff_parts = []
    for file_path, find_text, replace_text in blocks:
        file_path = file_path.strip()

        if allowed_files is not None:
            if not any(file_path == af or file_path.endswith(af) or af.endswith(file_path)
                       for af in allowed_files):
                print(f"  Skipping hallucinated file: {file_path} (not in context)")
                continue

        full_path = repo_path / file_path
        if not full_path.exists():
            continue
        try:
            original = full_path.read_text(errors='replace')
        except Exception:
            continue

        find_text = strip_line_numbers(find_text).rstrip('\n')
        replace_text = strip_line_numbers(replace_text).rstrip('\n')

        if find_text not in original:
            find_stripped = '\n'.join(l.rstrip() for l in find_text.splitlines())
            orig_stripped = '\n'.join(l.rstrip() for l in original.splitlines())
            if find_stripped not in orig_stripped:
                continue

        new_content = original.replace(find_text, replace_text, 1)
        if new_content == original:
            continue

        orig_lines = original.splitlines()
        new_lines  = new_content.splitlines()
        diff = list(difflib.unified_diff(
            orig_lines, new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm='',
        ))
        if diff:
            diff_parts.append('\n'.join(diff) + '\n')

    return ''.join(diff_parts)


def run_single_test(repo_path: Path, test_id: str) -> bool:
    """Run a single test, return True if it passes."""
    has_pytest = (repo_path / "setup.py").exists() or (repo_path / "pyproject.toml").exists()
    if has_pytest:
        cmd = ["python3", "-m", "pytest", test_id, "-x", "--tb=short", "-q"]
    else:
        cmd = ["python3", "-m", "unittest", test_id, "-q"]
    try:
        r = subprocess.run(
            cmd, cwd=str(repo_path), capture_output=True, text=True, timeout=60,
            env={**os.environ, "PYTHONPATH": str(repo_path)},
        )
        return r.returncode == 0
    except Exception:
        return False


def apply_and_test(instance: dict, patch: str, repo_path: Path) -> dict:
    """Apply patch, run FAIL_TO_PASS tests, reset repo. Returns result dict."""
    iid = instance["instance_id"]
    fail_to_pass = json.loads(instance.get("FAIL_TO_PASS", "[]"))

    if not patch:
        return {"instance_id": iid, "resolved": False, "reason": "empty_patch",
                "error_log": "No patch generated"}

    base_commit = instance.get("base_commit", "HEAD")
    subprocess.run(
        ["git", "-C", str(repo_path), "checkout", base_commit, "--force"],
        capture_output=True, text=True, timeout=30,
    )

    patch_file = repo_path / "_swebench_patch.diff"
    patch_file.write_text(patch)
    apply = subprocess.run(
        ["git", "-C", str(repo_path), "apply", "--whitespace=fix", str(patch_file)],
        capture_output=True, text=True, timeout=30,
    )
    patch_file.unlink(missing_ok=True)

    if apply.returncode != 0:
        subprocess.run(["git", "-C", str(repo_path), "checkout", "."], capture_output=True)
        error_log = f"Patch apply failed:\n{apply.stderr[:500]}"
        return {"instance_id": iid, "resolved": False, "reason": "apply_failed",
                "error_log": error_log}

    # Run failing tests
    test_results = {}
    test_outputs = {}
    for test_id in fail_to_pass[:5]:
        has_pytest = (repo_path / "setup.py").exists() or (repo_path / "pyproject.toml").exists()
        cmd = ["python3", "-m", "pytest", test_id, "-x", "--tb=short", "-q"] if has_pytest else \
              ["python3", "-m", "unittest", test_id, "-q"]
        try:
            r = subprocess.run(
                cmd, cwd=str(repo_path), capture_output=True, text=True, timeout=60,
                env={**os.environ, "PYTHONPATH": str(repo_path)},
            )
            test_results[test_id] = (r.returncode == 0)
            if r.returncode != 0:
                test_outputs[test_id] = (r.stdout + r.stderr)[-800:]
        except Exception as e:
            test_results[test_id] = False
            test_outputs[test_id] = str(e)

    subprocess.run(["git", "-C", str(repo_path), "checkout", "."], capture_output=True)

    f2p_pass = sum(1 for v in test_results.values() if v)
    resolved = f2p_pass == len(test_results) and len(test_results) > 0

    # Summarize failures for implementer feedback
    failure_lines = []
    for tid, output in test_outputs.items():
        failure_lines.append(f"FAILED {tid}:\n{output}")
    error_log = "\n\n".join(failure_lines) if failure_lines else ""

    return {
        "instance_id": iid,
        "resolved": resolved,
        "f2p_tested": len(test_results),
        "f2p_passed": f2p_pass,
        "test_results": test_results,
        "error_log": error_log,
    }


# ── Claude API ────────────────────────────────────────────────────────────────

def call_claude(system_prompt: str, user_prompt: str,
                client: anthropic.Anthropic,
                max_tokens: int = 4096) -> Optional[str]:
    """Call Claude with role-specific system prompt and retry logic."""
    for attempt in range(3):
        try:
            message = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=max_tokens,
                temperature=0,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return message.content[0].text.strip()
        except anthropic.RateLimitError:
            wait = RETRY_DELAY * (attempt + 1)
            print(f"  Rate limited, waiting {wait}s...")
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            if e.status_code == 529:
                wait = RETRY_DELAY * (attempt + 1)
                print(f"  API overloaded, waiting {wait}s...")
                time.sleep(wait)
            elif attempt < 2:
                time.sleep(3)
            else:
                print(f"  Claude API error: {str(e)[:100]}")
                return None
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
            else:
                print(f"  Unexpected error: {str(e)[:100]}")
                return None
    return None


def parse_investigator_output(raw: str) -> dict:
    """Parse JSON from investigator wave output."""
    if not raw:
        return {}
    # Strip markdown fences if present
    raw = re.sub(r'^```(?:json)?\n', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'\n```$', '', raw.strip())
    # Find JSON object
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def execute_investigator_tool(name: str, inputs: dict, repo_path: Path) -> str:
    """Execute a single investigator tool call. Returns string output (truncated to 4000 chars)."""
    try:
        if name == "grep_code":
            cmd = ["git", "grep", "-n", "--no-color"]
            if inputs.get("case_insensitive"):
                cmd.append("-i")
            cmd.append(inputs["pattern"])
            if "path" in inputs:
                cmd.extend(["--", inputs["path"]])
            result = subprocess.run(cmd, cwd=str(repo_path), capture_output=True, text=True, timeout=15)
            output = result.stdout or result.stderr or "(no matches)"

        elif name == "read_file":
            fpath = repo_path / inputs["path"]
            if not fpath.exists():
                return f"File not found: {inputs['path']}"
            lines = fpath.read_text(errors="replace").splitlines(keepends=True)
            start = max(0, inputs.get("start_line", 1) - 1)
            end = inputs.get("end_line", len(lines))
            output = "".join(f"{i + start + 1}: {l}" for i, l in enumerate(lines[start:end]))

        elif name == "search_files":
            cmd = ["find", ".", "-name", inputs["pattern"], "-type", "f"]
            if inputs.get("exclude_tests", True):
                cmd.extend(["!", "-path", "*/tests/*", "!", "-name", "test_*"])
            result = subprocess.run(cmd, cwd=str(repo_path), capture_output=True, text=True, timeout=15)
            output = result.stdout or "(no files found)"

        elif name == "git_log":
            n = inputs.get("n", 5)
            cmd = ["git", "log", f"-{n}", "--oneline", "--", inputs["path"]]
            result = subprocess.run(cmd, cwd=str(repo_path), capture_output=True, text=True, timeout=15)
            output = result.stdout or "(no commits found)"

        else:
            return f"Unknown tool: {name}"

    except subprocess.TimeoutExpired:
        return "(tool timed out after 15s)"
    except Exception as e:
        return f"(tool error: {e})"

    return output[:4000]


def run_investigator_agentic(instance: dict, repo_path: Path, client,
                              max_steps: int = 10) -> tuple[dict, list]:
    """
    Multi-turn agentic investigator using Anthropic tool use API.
    Returns (artifact_dict, traj_steps) where traj_steps is list of events for logging.
    """
    repo_tree = get_file_tree(repo_path)
    problem_statement = instance["problem_statement"]

    user_msg = (
        f"<issue>\n{problem_statement[:3000]}\n</issue>\n\n"
        f"<repo_structure>\n{repo_tree[:5000]}\n</repo_structure>\n\n"
        "Use the available tools to explore the repository and identify the root cause. "
        "When you have enough information, respond with your JSON artifact (no tool calls)."
    )

    messages = [{"role": "user", "content": user_msg}]
    traj_steps = []
    steps_used = 0

    while steps_used < max_steps:
        for attempt in range(3):
            try:
                response = client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=4096,
                    temperature=0,
                    system=INVESTIGATOR_SYSTEM,
                    tools=INVESTIGATOR_TOOLS,
                    tool_choice={"type": "auto"},
                    messages=messages,
                )
                break
            except anthropic.RateLimitError:
                wait = RETRY_DELAY * (attempt + 1)
                print(f"  Rate limited (investigator), waiting {wait}s...")
                time.sleep(wait)
            except anthropic.APIStatusError as e:
                if e.status_code == 529:
                    wait = RETRY_DELAY * (attempt + 1)
                    print(f"  API overloaded (investigator), waiting {wait}s...")
                    time.sleep(wait)
                elif attempt < 2:
                    time.sleep(3)
                else:
                    artifact = {"steps_used": steps_used}
                    return artifact, traj_steps
            except Exception as e:
                if attempt < 2:
                    time.sleep(3)
                else:
                    artifact = {"steps_used": steps_used}
                    return artifact, traj_steps
        else:
            artifact = {"steps_used": steps_used}
            return artifact, traj_steps

        step_log = {
            "type": f"wave_0_step_{steps_used}",
            "stop_reason": response.stop_reason,
            "content_types": [b.type for b in response.content],
        }
        traj_steps.append(step_log)

        # Append assistant response to messages
        messages.append({"role": "assistant", "content": response.content})

        # If no tool calls → extract artifact from text
        if response.stop_reason == "end_turn":
            text_blocks = [b.text for b in response.content if hasattr(b, "text")]
            full_text = "\n".join(text_blocks)
            artifact = parse_investigator_output(full_text)
            artifact["steps_used"] = steps_used
            return artifact, traj_steps

        # Process tool_use blocks
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                output = execute_investigator_tool(block.name, block.input, repo_path)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })
                step_log[f"tool_{block.name}"] = block.input

        if not tool_results:
            break  # no tools called despite tool_use stop_reason

        messages.append({"role": "user", "content": tool_results})
        steps_used += 1

    # Exceeded max_steps — ask for final answer
    messages.append({
        "role": "user",
        "content": "You've reached the step limit. Provide your JSON artifact now with what you know.",
    })
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            temperature=0,
            system=INVESTIGATOR_SYSTEM,
            messages=messages,
        )
        text_blocks = [b.text for b in response.content if hasattr(b, "text")]
        artifact = parse_investigator_output("\n".join(text_blocks))
    except Exception:
        artifact = {}
    artifact["steps_used"] = steps_used
    return artifact, traj_steps


ENV_ERROR_MARKERS = [
    "ImportError", "ModuleNotFoundError", "No module named",
    "ImproperlyConfigured", "django.setup()", "Apps aren't loaded yet",
    "command not found", "No such file or directory",
]


def classify_error(error_log: str) -> str:
    """Return 'env' if error is a setup/import issue, 'logic' if it's a real test failure."""
    for marker in ENV_ERROR_MARKERS:
        if marker in error_log:
            return "env"
    return "logic"


def read_test_context(f2p: list[str], repo_path: Path, max_chars: int = 3000) -> str:
    """
    Read the actual test function bodies for FAIL_TO_PASS tests.
    Shows the implementer exactly what assertions must pass.
    """
    if not f2p:
        return "(no test IDs provided)"
    parts = []
    seen_files: set[str] = set()
    total = 0
    for test_id in f2p[:4]:
        if "::" not in test_id:
            parts.append(f"  - {test_id}")
            continue
        segments = test_id.split("::")
        test_file_rel = segments[0]
        test_func = segments[-1]  # last segment = method name
        test_path = repo_path / test_file_rel
        if not test_path.exists():
            parts.append(f"  - {test_id}  (test file not found)")
            continue
        try:
            r = subprocess.run(
                ["grep", "-n", "-A", "40", f"def {test_func}\\b", str(test_path)],
                capture_output=True, text=True, timeout=5,
            )
            if r.stdout:
                snippet = r.stdout[:1200]
                entry = f"# {test_id}\n{snippet}"
                if total + len(entry) > max_chars:
                    break
                parts.append(entry)
                total += len(entry)
                seen_files.add(test_file_rel)
            else:
                parts.append(f"  - {test_id}  (function def not found in file)")
        except Exception:
            parts.append(f"  - {test_id}")
    return "\n\n".join(parts) if parts else "(test code unavailable)"


def save_traj(traj_path: Path, event: str, data: dict) -> None:
    """Append an event to the trajectory log for this instance."""
    with open(traj_path, "a") as f:
        f.write(json.dumps({"event": event, "timestamp": time.time(), **data}) + "\n")


# ── V11 Formation: Main Instance Runner ───────────────────────────────────────

def run_instance_v11(instance: dict, client: anthropic.Anthropic,
                     max_attempts: int = DEFAULT_MAX_ATTEMPTS,
                     max_steps: int = 10) -> dict:
    """
    Run V11 swebench-solver formation on a single SWE-bench instance.

    3-wave pipeline:
      Wave 0: INVESTIGATOR → identifies root cause + target files
      Wave 1: IMPLEMENTER → generates FIND/REPLACE patch
      Wave 2: VALIDATOR (real tests) → feedback loop to implementer
    """
    iid = instance["instance_id"]
    repo = instance["repo"]
    base = instance["base_commit"]
    issue = instance["problem_statement"]
    f2p = json.loads(instance.get("FAIL_TO_PASS", "[]"))
    trace_id = str(uuid.uuid4())[:8]

    traj_path = TRAJ_DIR / f"{iid}.jsonl"
    traj_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n[{iid}] Setting up repo...")
    repo_path = clone_or_update_repo(repo, base)

    if not repo_path:
        return {
            "instance_id": iid,
            "model_name_or_path": f"v11-formation/{CLAUDE_MODEL}",
            "model_patch": "",
            "trace_id": trace_id,
            "success": False,
            "error": "repo_clone_failed",
        }

    # ── Wave 0: AGENTIC INVESTIGATOR ─────────────────────────────────────────
    print(f"  Wave 0 (agentic, max {max_steps} steps)...")
    investigation, inv_traj = run_investigator_agentic(instance, repo_path, client, max_steps)
    save_traj(traj_path, "wave_0_investigator", {
        "parsed": investigation,
        "trace_id": trace_id,
        "steps_used": investigation.get("steps_used", 0),
        "steps": inv_traj,
    })

    hypothesis = investigation.get("hypothesis", "unknown root cause")
    complexity = investigation.get("complexity", "medium")
    investigator_files = investigation.get("target_files", [])
    reasoning = investigation.get("reasoning", "")
    fix_strategy = investigation.get("fix_strategy", "(not provided — reason from hypothesis)")
    print(f"  Hypothesis: {hypothesis[:80]}")
    print(f"  Fix strategy: {fix_strategy[:80]}")
    print(f"  Target files: {investigator_files}")

    # ── File retrieval (Wave 0 artifact → enhanced file targeting) ────────────
    files = find_relevant_files(
        repo_path, issue,
        fail_to_pass=f2p,
        investigator_files=investigator_files,
    )
    file_ctx = read_file_context(files, repo_path)
    file_list = [str(f.relative_to(repo_path)) for f in files]
    test_ctx = read_test_context(f2p, repo_path)
    print(f"  Files loaded: {file_list}")

    # ── Waves 1+2: IMPLEMENTER + VALIDATOR feedback loop ─────────────────────
    final_patch = ""
    final_result = {"resolved": False, "reason": "no_attempt"}
    previous_patch = ""
    error_context = ""

    for attempt in range(max_attempts):
        print(f"  Wave 1: Implementer (attempt {attempt+1}/{max_attempts})...")

        if attempt == 0:
            implementer_prompt = IMPLEMENTER_TEMPLATE.format(
                hypothesis=hypothesis,
                complexity=complexity,
                reasoning=reasoning,
                fix_strategy=fix_strategy,
                problem_statement=issue[:2000],
                test_context=test_ctx,
                file_context=file_ctx,
            )
        else:
            print(f"  Revising patch based on validator feedback...")
            # Detect if validator gave us env noise vs real test failure
            error_type = classify_error(error_context or "")
            if error_type == "env":
                feedback_text = (
                    "The local test environment could not run the tests (missing dependencies).\n"
                    "Do NOT change your approach based on import errors.\n"
                    "Instead, reason from the Fix Strategy and the test assertions below to "
                    "verify your patch logic is correct. The most common issue is that the FIND "
                    "text didn't match — double-check indentation and exact whitespace."
                )
                print(f"  (Env error detected — suppressing garbage feedback)")
            else:
                feedback_text = error_context[:2000] if error_context else "(no error details)"
            implementer_prompt = IMPLEMENTER_REVISE_TEMPLATE.format(
                attempt=attempt + 1,
                previous_patch=previous_patch[:3000] if previous_patch else "(empty)",
                error_context=feedback_text,
                fix_strategy=fix_strategy,
                problem_statement=issue[:1500],
                test_context=test_ctx,
                file_context=file_ctx,
            )

        raw_patch = call_claude(IMPLEMENTER_SYSTEM, implementer_prompt, client)
        patch = apply_edit_blocks(raw_patch or "", repo_path, allowed_files=file_list or None)
        save_traj(traj_path, f"wave_1_implementer_attempt_{attempt+1}", {
            "raw_response_len": len(raw_patch or ""),
            "patch_len": len(patch),
            "attempt": attempt + 1,
            "trace_id": trace_id,
        })
        print(f"  Patch: {len(patch)} chars {'✅' if patch else '❌'}")

        if not patch:
            # No patch generated; don't bother testing
            print(f"  No patch generated, skipping validation")
            previous_patch = ""
            error_context = "No patch was generated — FIND text did not match source files."
            continue

        # Wave 2: VALIDATOR — run real tests
        print(f"  Wave 2: Validator (running tests)...")
        test_result = apply_and_test(instance, patch, repo_path)
        save_traj(traj_path, f"wave_2_validator_attempt_{attempt+1}", {
            "resolved": test_result["resolved"],
            "f2p_tested": test_result.get("f2p_tested", 0),
            "f2p_passed": test_result.get("f2p_passed", 0),
            "error_log_len": len(test_result.get("error_log", "")),
            "attempt": attempt + 1,
            "trace_id": trace_id,
        })

        resolved = test_result["resolved"]
        print(f"  Validation: {'✅ RESOLVED' if resolved else '❌ tests failed'}")

        if resolved:
            final_patch = patch
            final_result = test_result
            break

        # Not resolved — prepare feedback for next attempt
        previous_patch = patch
        error_context = test_result.get("error_log", "Tests failed (no details)")
        final_patch = patch  # Keep last patch as fallback

    if not final_patch and previous_patch:
        final_patch = previous_patch  # use last generated patch even if unverified

    result = {
        "instance_id": iid,
        "model_name_or_path": f"v11-formation/{CLAUDE_MODEL}",
        "model_patch": final_patch,
        "trace_id": trace_id,
        "files_used": file_list,
        "patch_len": len(final_patch),
        "success": bool(final_patch),
        "resolved": final_result.get("resolved", False),
        "complexity": complexity,
        "investigator_files": investigator_files,
        "attempts_used": min(attempt + 1, max_attempts) if 'attempt' in dir() else 0,
    }

    (PRED_DIR / f"{iid}.json").write_text(json.dumps(result, indent=2))
    save_traj(traj_path, "final_result", {
        "resolved": result["resolved"],
        "patch_len": result["patch_len"],
        "attempts_used": result["attempts_used"],
        "trace_id": trace_id,
    })

    status = "✅ RESOLVED" if result["resolved"] else ("📝 patch" if final_patch else "❌ no patch")
    print(f"  Result: {status} (patch: {len(final_patch)} chars, "
          f"attempts: {result['attempts_used']})")
    return result


# ── Parallel batch runner ─────────────────────────────────────────────────────

def run_batch_parallel(instances: list, client: anthropic.Anthropic,
                       max_workers: int, max_attempts: int, max_steps: int) -> list:
    """Run multiple instances in parallel using ThreadPoolExecutor."""
    results = []
    lock = threading.Lock()

    def process_one(instance):
        result = run_instance_v11(instance, client,
                                  max_attempts=max_attempts, max_steps=max_steps)
        with lock:
            results.append(result)
            print(f"  [{len(results)}/{len(instances)}] {instance['instance_id']}: "
                  f"{len(result.get('model_patch', ''))} chars")
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_one, inst) for inst in instances]
        concurrent.futures.wait(futures)

    return results


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SWE-bench V11 multi-agent formation (3-wave: investigator→implementer→validator)")
    parser.add_argument("--num", type=int, default=10, help="Number of instances to run")
    parser.add_argument("--instance-ids", nargs="+", help="Specific instance IDs to run")
    parser.add_argument("--list", action="store_true", help="List available instances")
    parser.add_argument("--report", action="store_true", help="Show results report")
    parser.add_argument("--repo-filter", help="Filter by repo (e.g. django, sympy)")
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS,
                        help=f"Max validator→implementer iterations (default: {DEFAULT_MAX_ATTEMPTS})")
    parser.add_argument("--max-steps", type=int, default=10,
                        help="Max investigator tool calls per instance (default: 10)")
    parser.add_argument("--workers", type=int, default=1,
                        help="Parallel workers for instance processing (default: 1 = sequential)")
    parser.add_argument("--out", type=str, default=None,
                        help="Override output directory (default: swebench-predictions/v11-formation)")
    args = parser.parse_args()

    global PRED_DIR, TRAJ_DIR
    if args.out:
        PRED_DIR = Path(args.out)
        TRAJ_DIR = PRED_DIR / "trajs"

    REPO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    TRAJ_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading SWE-bench Lite dataset (300 instances)...")
    dataset = load_lite_dataset()
    print(f"Loaded {len(dataset)} instances")

    if args.list:
        for inst in dataset[:20]:
            print(f"  {inst['instance_id']:50s}  {inst['repo']}")
        print(f"  ... ({len(dataset)} total)")
        return

    if args.report:
        show_report()
        return

    if args.instance_ids:
        instances = [i for i in dataset if i["instance_id"] in args.instance_ids]
    elif args.repo_filter:
        instances = [i for i in dataset if args.repo_filter.lower() in i["repo"].lower()][:args.num]
    else:
        instances = dataset[:args.num]

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Set ANTHROPIC_API_KEY (source your secrets env file, e.g. ~/.secrets/api-keys.env)")
    client = anthropic.Anthropic(api_key=api_key)

    print(f"\nRunning V11 formation inference on {len(instances)} instances")
    print(f"Model: {CLAUDE_MODEL} | Max attempts: {args.max_attempts} | "
          f"Max steps: {args.max_steps} | Workers: {args.workers}")
    print(f"Repo cache:  {REPO_CACHE_DIR}")
    print(f"Predictions: {PRED_DIR}")
    print(f"Trajectories: {TRAJ_DIR}")

    t0 = time.time()

    # Filter out already-completed instances
    pending = []
    results = []
    for inst in instances:
        existing = PRED_DIR / f"{inst['instance_id']}.json"
        if existing.exists():
            try:
                data = json.loads(existing.read_text())
                if data.get("success"):
                    print(f"  ↩️  Resuming: {inst['instance_id']} already done")
                    results.append(data)
                    continue
            except Exception:
                pass
        pending.append(inst)

    if args.workers > 1 and len(pending) > 1:
        print(f"\nParallel mode: {args.workers} workers, {len(pending)} instances")
        parallel_results = run_batch_parallel(
            pending, client,
            max_workers=args.workers,
            max_attempts=args.max_attempts,
            max_steps=args.max_steps,
        )
        results.extend(parallel_results)
    else:
        for i, inst in enumerate(pending, 1):
            print(f"\n{'='*60}")
            print(f"[{i}/{len(pending)}] {inst['instance_id']}")
            try:
                r = run_instance_v11(inst, client,
                                     max_attempts=args.max_attempts,
                                     max_steps=args.max_steps)
                results.append(r)
            except Exception as e:
                print(f"  ERROR: {e}")
                results.append({
                    "instance_id": inst["instance_id"],
                    "success": False,
                    "model_patch": "",
                    "error": str(e),
                    "model_name_or_path": f"v11-formation/{CLAUDE_MODEL}",
                })
            if i < len(pending):
                time.sleep(REQUEST_DELAY)

    elapsed = time.time() - t0

    all_preds_path = PRED_DIR / "all_preds.jsonl"
    with open(all_preds_path, "w") as f:
        for r in results:
            f.write(json.dumps({
                "instance_id": r["instance_id"],
                "model_name_or_path": r.get("model_name_or_path", f"v11-formation/{CLAUDE_MODEL}"),
                "model_patch": r.get("model_patch", ""),
            }) + "\n")

    successful = sum(1 for r in results if r.get("success"))
    resolved = sum(1 for r in results if r.get("resolved"))
    total_patch_chars = sum(r.get("patch_len", 0) for r in results)
    avg_attempts = (sum(r.get("attempts_used", 0) for r in results if r.get("attempts_used"))
                    / max(successful, 1))

    print(f"\n{'='*60}")
    print(f"V11 FORMATION INFERENCE COMPLETE")
    print(f"  Model:          {CLAUDE_MODEL}")
    print(f"  Formation:      swebench-solver (agentic-investigator→implementer→validator)")
    print(f"  Max attempts:   {args.max_attempts}")
    print(f"  Max steps:      {args.max_steps}")
    print(f"  Workers:        {args.workers}")
    print(f"  Instances:      {len(results)}")
    print(f"  Patches gen:    {successful}/{len(results)} ({100*successful//max(len(results),1)}%)")
    print(f"  Quick-resolved: {resolved}/{len(results)} ({100*resolved//max(len(results),1)}%)")
    print(f"  Avg patch:      {total_patch_chars//max(successful,1)} chars")
    print(f"  Avg attempts:   {avg_attempts:.1f}")
    print(f"  Time elapsed:   {elapsed:.1f}s ({elapsed/max(len(results),1):.1f}s/instance)")
    print(f"  Predictions:    {all_preds_path}")
    print(f"  Traces:         {TRAJ_DIR}/")
    print()
    print("Next: run official harness evaluation:")
    print(f"  python -m swebench.harness.run_evaluation \\")
    print(f"      --predictions_path {all_preds_path} \\")
    print(f"      --swe_bench_tasks princeton-nlp/SWE-bench_Lite \\")
    print(f"      --run_id v11-formation-claude-sonnet \\")
    print(f"      --max_workers 4")

    return results


def show_report():
    """Show results from existing prediction files."""
    if not PRED_DIR.exists():
        print("No predictions directory found.")
        return
    files = list(PRED_DIR.glob("*.json"))
    if not files:
        print("No prediction files found.")
        return
    total = len(files)
    with_patch = 0
    resolved_count = 0
    by_repo: dict[str, list] = {}
    attempt_dist: dict[int, int] = {}
    for f in sorted(files):
        data = json.loads(f.read_text())
        iid = data.get("instance_id", f.stem)
        repo = iid.rsplit("__", 1)[0].replace("__", "/") if "__" in iid else "unknown"
        has_patch = bool(data.get("model_patch"))
        is_resolved = bool(data.get("resolved"))
        attempts = data.get("attempts_used", 0)
        if has_patch:
            with_patch += 1
        if is_resolved:
            resolved_count += 1
        by_repo.setdefault(repo, {"patches": 0, "resolved": 0, "total": 0})
        by_repo[repo]["total"] += 1
        if has_patch:
            by_repo[repo]["patches"] += 1
        if is_resolved:
            by_repo[repo]["resolved"] += 1
        attempt_dist[attempts] = attempt_dist.get(attempts, 0) + 1

    print(f"\nSWE-bench V11 Formation Report")
    print(f"{'='*55}")
    print(f"Model:             {CLAUDE_MODEL}")
    print(f"Formation:         swebench-solver (3-wave)")
    print(f"Total instances:   {total}")
    print(f"Patches generated: {with_patch}/{total} ({100*with_patch//total}%)")
    print(f"Quick-resolved:    {resolved_count}/{total} ({100*resolved_count//total}%)")
    print(f"\nAttempts distribution:")
    for k in sorted(attempt_dist):
        print(f"  {k} attempt(s): {attempt_dist[k]} instances")
    print(f"\nBy repo:")
    for repo, stats in sorted(by_repo.items()):
        n = stats["total"]
        p = stats["patches"]
        r = stats["resolved"]
        print(f"  {repo:40s} patches={p}/{n}  resolved={r}/{n}")


if __name__ == "__main__":
    main()
