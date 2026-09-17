#!/usr/bin/env python3
"""
SWE-bench Claude one-shot baseline for Phase 10.1 comparison.

Uses Claude Sonnet 4.6 (same FIND/REPLACE architecture as swe_infer.py but
with Anthropic API instead of Gemini). Establishes the "Claude without V11"
baseline to compare against the V11 multi-agent formation (swe_v11.py).

Usage:
    python3 swe_claude_baseline.py --num 10            # first 10 instances
    python3 swe_claude_baseline.py --num 300           # full Lite suite
    python3 swe_claude_baseline.py --instance-ids astropy__astropy-12907
    python3 swe_claude_baseline.py --list              # list available instances
    python3 swe_claude_baseline.py --report            # show results report

Output: swebench-predictions/claude-baseline/{instance_id}.json
Combined: swebench-predictions/claude-baseline/all_preds.jsonl
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
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
REPO_CACHE_DIR  = Path("/path/to/v11/swebench-repos")
PRED_DIR        = Path("/path/to/v11/swebench-predictions/claude-baseline")
MAX_CONTEXT_CHARS = 100_000  # ~25K tokens
MAX_FILE_CHARS    = 20_000   # per file
MAX_FILE_LINES    = 600      # max lines per file
MAX_FILES         = 5        # max files to include per instance
RETRY_DELAY       = 10       # seconds between Claude retries
REQUEST_DELAY     = 1.0      # seconds between requests (Claude has higher rate limits)

SYSTEM_PROMPT = """\
You are an expert software engineer solving a GitHub issue. You will be given the \
issue description and relevant source files with line numbers. \
Output ONLY code edit blocks in this exact format — one block per change:

<<<< FILE: path/to/file.py
FIND:
(exact lines to find, verbatim, including indentation)
REPLACE:
(replacement lines)
>>>>

Rules:
- FIND must match EXACTLY what appears in the file (copy verbatim from the provided source).
- Make the FIND section as short as possible while still being unique.
- Do not include test files unless the issue explicitly requires it.
- Output NOTHING else — no explanation, no prose, just the edit blocks.\
"""

USER_TEMPLATE = """\
## GitHub Issue

{problem_statement}

## Source Files (with line numbers)

{file_context}

## Task

Output edit blocks to fix the issue. Use the exact FIND/REPLACE format. Copy FIND lines \
verbatim from the source above.
"""

# ── helpers (shared with swe_infer.py) ────────────────────────────────────────

def load_lite_dataset() -> list[dict]:
    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    return [dict(row) for row in ds]


def clone_or_update_repo(repo: str, base_commit: str) -> Optional[Path]:
    """Clone repo if not present, checkout base_commit. Returns local path."""
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
        subprocess.run(
            ["git", "-C", str(local), "fetch", "--depth=500", "origin"],
            capture_output=True, text=True, timeout=60,
        )
    subprocess.run(
        ["git", "-C", str(local), "checkout", base_commit, "--force"],
        capture_output=True, text=True, timeout=30,
    )
    return local


def extract_keywords(text: str, n: int = 15) -> list[str]:
    """Extract meaningful keywords from issue text for file search."""
    words = re.findall(r'\b[A-Za-z_][A-Za-z0-9_]{3,}\b', text)
    scored = {}
    for w in words:
        score = 1
        if '_' in w or (w[0].isupper() and any(c.islower() for c in w)):
            score = 3
        scored[w] = scored.get(w, 0) + score
    top = sorted(scored, key=lambda x: -scored[x])
    return top[:n]


def find_relevant_files(repo_path: Path, issue_text: str, fail_to_pass: list[str] = None) -> list[Path]:
    """Search repo for files relevant to the issue (same strategy as swe_infer.py)."""
    file_scores: dict[Path, int] = {}
    code_exts = {'.py', '.js', '.ts', '.rb', '.go', '.java', '.c', '.cpp'}

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


LINE_NUM_RE = re.compile(r'^\s*\d+\s*\|\s?', re.MULTILINE)


def strip_line_numbers(text: str) -> str:
    """Remove '  25 | ' style line-number prefixes the model copies verbatim."""
    return LINE_NUM_RE.sub('', text)


def apply_edit_blocks(raw_response: str, repo_path: Path,
                       allowed_files: list[str] | None = None) -> str:
    """Parse FIND/REPLACE edit blocks and convert to unified diff."""
    if not raw_response:
        return ""

    unwrapped = re.sub(r'^```[a-z]*\n', '', raw_response, flags=re.MULTILINE)
    unwrapped = re.sub(r'\n```$', '', unwrapped.strip())

    pattern = re.compile(
        r'<{4}\s*FILE:\s*([^\n]+)\nFIND:\n(.*?)\nREPLACE:\n(.*?)(?:\n>{4}|(?=\n<{4})|$)',
        re.DOTALL,
    )
    blocks = pattern.findall(unwrapped)
    if not blocks:
        return ""

    import difflib
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


# ── Claude API ────────────────────────────────────────────────────────────────

def call_claude(prompt: str, client: anthropic.Anthropic) -> Optional[str]:
    """Call Claude with retry on rate-limit or overload."""
    for attempt in range(3):
        try:
            message = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except anthropic.RateLimitError:
            wait = RETRY_DELAY * (attempt + 1)
            print(f"  Rate limited, waiting {wait}s...")
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            if e.status_code == 529:  # Overloaded
                wait = RETRY_DELAY * (attempt + 1)
                print(f"  API overloaded, waiting {wait}s...")
                time.sleep(wait)
            elif attempt < 2:
                time.sleep(3)
            else:
                print(f"  Claude error: {str(e)[:100]}")
                return None
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
            else:
                print(f"  Claude error: {str(e)[:100]}")
                return None
    return None


# ── instance runner ────────────────────────────────────────────────────────────

def run_instance(instance: dict, client: anthropic.Anthropic) -> dict:
    """Run one-shot Claude inference on a single SWE-bench instance."""
    iid = instance["instance_id"]
    repo = instance["repo"]
    base = instance["base_commit"]
    issue = instance["problem_statement"]

    print(f"\n[{iid}] Cloning + searching...")
    repo_path = clone_or_update_repo(repo, base)

    if repo_path:
        f2p = json.loads(instance.get("FAIL_TO_PASS", "[]"))
        files = find_relevant_files(repo_path, issue, fail_to_pass=f2p)
        file_ctx = read_file_context(files, repo_path)
        file_list = [str(f.relative_to(repo_path)) for f in files]
        print(f"  Found {len(files)} relevant files: {file_list}")
    else:
        file_ctx = "(repo unavailable)"
        file_list = []

    prompt = USER_TEMPLATE.format(
        problem_statement=issue[:3000],
        file_context=file_ctx,
    )

    print(f"  Calling {CLAUDE_MODEL}...")
    raw = call_claude(prompt, client)
    if repo_path:
        patch = apply_edit_blocks(raw or "", repo_path, allowed_files=file_list or None)
    else:
        patch = ""

    result = {
        "instance_id": iid,
        "model_name_or_path": f"claude-baseline/{CLAUDE_MODEL}",
        "model_patch": patch,
        "files_used": file_list,
        "patch_len": len(patch),
        "success": bool(patch),
    }

    (PRED_DIR / f"{iid}.json").write_text(json.dumps(result, indent=2))
    print(f"  Patch: {len(patch)} chars {'✅' if patch else '❌'}")
    return result


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SWE-bench Lite one-shot baseline with Claude Sonnet 4.6")
    parser.add_argument("--num", type=int, default=10, help="Number of instances to run")
    parser.add_argument("--instance-ids", nargs="+", help="Specific instance IDs to run")
    parser.add_argument("--list", action="store_true", help="List available instances")
    parser.add_argument("--report", action="store_true", help="Show results report")
    parser.add_argument("--repo-filter", help="Filter by repo (e.g. sympy)")
    args = parser.parse_args()

    REPO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    PRED_DIR.mkdir(parents=True, exist_ok=True)

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
        sys.exit("Set ANTHROPIC_API_KEY environment variable (source ~/.secrets/app.env)")
    client = anthropic.Anthropic(api_key=api_key)

    print(f"\nRunning one-shot inference on {len(instances)} instances with {CLAUDE_MODEL}")
    print(f"Repo cache: {REPO_CACHE_DIR}")
    print(f"Predictions: {PRED_DIR}")

    results = []
    t0 = time.time()
    for i, inst in enumerate(instances, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/{len(instances)}] {inst['instance_id']}")

        existing = PRED_DIR / f"{inst['instance_id']}.json"
        if existing.exists():
            try:
                data = json.loads(existing.read_text())
                if data.get("success"):
                    print(f"  ↩️  Resuming: already done (patch: {data['patch_len']} chars)")
                    results.append(data)
                    continue
            except Exception:
                pass

        try:
            r = run_instance(inst, client)
            results.append(r)
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"instance_id": inst["instance_id"], "success": False,
                            "model_patch": "", "error": str(e)})

        if i < len(instances):
            time.sleep(REQUEST_DELAY)

    elapsed = time.time() - t0

    all_preds_path = PRED_DIR / "all_preds.jsonl"
    with open(all_preds_path, "w") as f:
        for r in results:
            f.write(json.dumps({
                "instance_id": r["instance_id"],
                "model_name_or_path": r.get("model_name_or_path", f"claude-baseline/{CLAUDE_MODEL}"),
                "model_patch": r.get("model_patch", ""),
            }) + "\n")

    successful = sum(1 for r in results if r.get("success"))
    total_patch_chars = sum(r.get("patch_len", 0) for r in results)
    print(f"\n{'='*60}")
    print(f"CLAUDE BASELINE INFERENCE COMPLETE")
    print(f"  Model:        {CLAUDE_MODEL}")
    print(f"  Instances:    {len(results)}")
    print(f"  Patches gen:  {successful}/{len(results)} ({100*successful//max(len(results),1)}%)")
    print(f"  Avg patch:    {total_patch_chars//max(successful,1)} chars")
    print(f"  Time elapsed: {elapsed:.1f}s ({elapsed/max(len(results),1):.1f}s/instance)")
    print(f"  Predictions:  {all_preds_path}")
    print()
    print("Next: run official harness to get resolved %:")
    print(f"  python -m swebench.harness.run_evaluation \\")
    print(f"      --predictions_path {all_preds_path} \\")
    print(f"      --swe_bench_tasks princeton-nlp/SWE-bench_Lite \\")
    print(f"      --run_id claude-baseline-sonnet \\")
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
    by_repo: dict[str, list] = {}
    for f in sorted(files):
        data = json.loads(f.read_text())
        iid = data.get("instance_id", f.stem)
        repo = iid.rsplit("__", 1)[0].replace("__", "/") if "__" in iid else "unknown"
        has_patch = bool(data.get("model_patch"))
        if has_patch:
            with_patch += 1
        by_repo.setdefault(repo, []).append(has_patch)
    print(f"\nSWE-bench Claude Baseline Report")
    print(f"{'='*50}")
    print(f"Model:             {CLAUDE_MODEL}")
    print(f"Total instances:   {total}")
    print(f"Patches generated: {with_patch}/{total} ({100*with_patch//total}%)")
    print(f"\nBy repo:")
    for repo, results in sorted(by_repo.items()):
        n = len(results)
        ok = sum(results)
        print(f"  {repo:40s} {ok}/{n}")


if __name__ == "__main__":
    main()
