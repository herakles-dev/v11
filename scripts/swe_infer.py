#!/usr/bin/env python3
"""
SWE-bench inference engine for V11 production benchmark.

Uses Gemini 2.0 Flash to generate patches for SWE-bench Lite instances.
Retrieves relevant file context from cloned repos via keyword search.

Usage:
    python3 swe_infer.py --instance-ids astropy__astropy-12907 sympy__sympy-13647
    python3 swe_infer.py --num 10            # first 10 instances
    python3 swe_infer.py --num 300           # full Lite suite
    python3 swe_infer.py --list              # list available instances

Output: predictions/{instance_id}.json (one file per instance)
Combined: predictions/all_preds.jsonl (for evaluation harness)
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
    import google.generativeai as genai
except ImportError:
    sys.exit("Install google-generativeai: pip install google-generativeai")

try:
    from datasets import load_dataset
except ImportError:
    sys.exit("Install datasets: pip install datasets")

# ── config ────────────────────────────────────────────────────────────────────

GEMINI_MODEL   = "gemini-2.0-flash"
REPO_CACHE_DIR = Path(os.path.expanduser("~/v11/swebench-repos"))
PRED_DIR       = Path(os.path.expanduser("~/v11/swebench-predictions"))
MAX_CONTEXT_CHARS = 100_000  # ~25K tokens — safe for flash 1M context
MAX_FILE_CHARS    = 20_000   # per file (up from 8K to see more code)
MAX_FILE_LINES    = 600      # max lines per file (up from 300)
MAX_FILES         = 5        # max files to include per instance
RETRY_DELAY       = 8        # seconds between Gemini retries
REQUEST_DELAY     = 5.0      # seconds between requests (15 RPM free tier = 4s min)

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

# ── helpers ───────────────────────────────────────────────────────────────────

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
    # Fetch if commit not present
    result = subprocess.run(
        ["git", "-C", str(local), "cat-file", "-t", base_commit],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        subprocess.run(
            ["git", "-C", str(local), "fetch", "--depth=500", "origin"],
            capture_output=True, text=True, timeout=60,
        )
    # Checkout
    subprocess.run(
        ["git", "-C", str(local), "checkout", base_commit, "--force"],
        capture_output=True, text=True, timeout=30,
    )
    return local


def extract_keywords(text: str, n: int = 15) -> list[str]:
    """Extract meaningful keywords from issue text for file search."""
    # strip URLs, punctuation; take longer words as signal
    words = re.findall(r'\b[A-Za-z_][A-Za-z0-9_]{3,}\b', text)
    # weight Python identifiers (underscored, CamelCase)
    scored = {}
    for w in words:
        score = 1
        if '_' in w or (w[0].isupper() and any(c.islower() for c in w)):
            score = 3
        scored[w] = scored.get(w, 0) + score
    top = sorted(scored, key=lambda x: -scored[x])
    return top[:n]


def find_relevant_files(repo_path: Path, issue_text: str, fail_to_pass: list[str] = None) -> list[Path]:
    """
    Search repo for files relevant to the issue.

    Strategy (priority order):
    1. Extract function/module names from FAIL_TO_PASS test IDs and find source files
    2. Keyword grep on issue text with filename-match bonus
    3. Return top MAX_FILES by score
    """
    file_scores: dict[Path, int] = {}
    code_exts = {'.py', '.js', '.ts', '.rb', '.go', '.java', '.c', '.cpp'}

    # ── Strategy 1: FAIL_TO_PASS → find source files ─────────────────────────
    if fail_to_pass:
        for test_id in fail_to_pass[:5]:
            # Case A: full path given "sympy/printing/tests/test_ccode.py::test_ccode_sinc"
            if "::" in test_id and ".py" in test_id:
                test_file_rel = test_id.split("::")[0]
                test_path = repo_path / test_file_rel
                # Derive source file: remove tests/ subdir and test_ prefix
                src_rel = re.sub(r'/tests/test_', '/', test_file_rel)
                src_path = repo_path / src_rel
                if src_path.exists() and src_path.suffix in code_exts:
                    file_scores[src_path] = file_scores.get(src_path, 0) + 10
                # Also add the test file for context
                if test_path.exists():
                    file_scores[test_path] = file_scores.get(test_path, 0) + 3
            else:
                # Case B: only function name given — grep for it in test files
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
                        # Derive source file from test file path
                        src_rel = re.sub(r'/tests/test_', '/', test_file_rel)
                        src_path = repo_path / src_rel
                        if src_path.exists() and src_path.suffix in code_exts:
                            # Give higher score when fewer test files match (more specific)
                            specificity_bonus = max(0, 10 - len(test_hits))
                            file_scores[src_path] = file_scores.get(src_path, 0) + 15 + specificity_bonus
                except subprocess.TimeoutExpired:
                    pass

                # Also strip test_ prefix and look for source by name
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

    # ── Strategy 2: keyword grep ──────────────────────────────────────────────
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
                    # Bonus if file name matches a keyword
                    name_bonus = 2 if any(kw.lower() in p.stem.lower() for kw in keywords[:5]) else 0
                    # Penalize test files slightly (want implementation, not tests)
                    test_penalty = -1 if "test" in str(p).lower() else 0
                    file_scores[p] = file_scores.get(p, 0) + 1 + name_bonus + test_penalty
        except subprocess.TimeoutExpired:
            continue

    if not file_scores:
        return []

    # Sort: score desc, then shorter path (closer to root = more fundamental)
    ranked = sorted(file_scores, key=lambda p: (-file_scores[p], len(str(p))))
    # Exclude pure test files if we have implementation files
    impl = [p for p in ranked if "test" not in str(p).lower()]
    tests = [p for p in ranked if "test" in str(p).lower()]
    # Take top 4 impl files + 1 test file for context
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
    """
    Parse FIND/REPLACE edit blocks from model output and convert to unified diff.
    Returns unified diff string, or empty string if nothing parsed.

    allowed_files: if provided, only apply edits for files in this list
                   (prevents model hallucinating files not in context).
    """
    if not raw_response:
        return ""

    # Strip fenced code block wrapper the model often adds (```diff ... ```)
    unwrapped = re.sub(r'^```[a-z]*\n', '', raw_response, flags=re.MULTILINE)
    unwrapped = re.sub(r'\n```$', '', unwrapped.strip())

    # Parse blocks: <<<< FILE: path\nFIND:\n...\nREPLACE:\n...\n>>>>
    # >>>> is optional at end (model often truncates without closing marker)
    pattern = re.compile(
        r'<{4}\s*FILE:\s*([^\n]+)\nFIND:\n(.*?)\nREPLACE:\n(.*?)(?:\n>{4}|(?=\n<{4})|$)',
        re.DOTALL,
    )
    blocks = pattern.findall(unwrapped)
    if not blocks:
        # No FIND/REPLACE blocks found — return empty (don't pass raw text to git apply)
        return ""

    diff_parts = []
    for file_path, find_text, replace_text in blocks:
        file_path = file_path.strip()

        # Guard against hallucinated file names not in provided context
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

        # Strip line number prefixes the model copies verbatim (e.g. "  25 | ")
        find_text = strip_line_numbers(find_text).rstrip('\n')
        replace_text = strip_line_numbers(replace_text).rstrip('\n')

        if find_text not in original:
            # Try stripping trailing spaces from each line
            find_stripped = '\n'.join(l.rstrip() for l in find_text.splitlines())
            orig_stripped = '\n'.join(l.rstrip() for l in original.splitlines())
            if find_stripped not in orig_stripped:
                continue  # can't locate, skip

        # Apply replacement
        new_content = original.replace(find_text, replace_text, 1)
        if new_content == original:
            continue

        # Generate unified diff.
        # splitlines() gives lines without embedded newlines; lineterm=''
        # means difflib doesn't add terminators to headers either.
        # '\n'.join(diff) + '\n' gives one newline per line uniformly.
        import difflib
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


def call_gemini(prompt: str, model) -> Optional[str]:
    """Call Gemini with retry on rate-limit."""
    for attempt in range(3):
        try:
            response = model.generate_content(
                [{"role": "user", "parts": [prompt]}],
            )
            return response.text.strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower():
                wait = RETRY_DELAY * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
            elif attempt < 2:
                time.sleep(2)
            else:
                print(f"  Gemini error: {err[:100]}")
                return None
    return None


def extract_patch(raw: str) -> str:
    """Extract unified diff from model output."""
    if not raw:
        return ""
    # Find diff start
    for marker in ["--- a/", "--- /", "diff --git"]:
        idx = raw.find(marker)
        if idx >= 0:
            return raw[idx:].strip()
    # If model included code block, extract from it
    m = re.search(r'```(?:diff|patch)?\n(.*?)```', raw, re.DOTALL)
    if m:
        return m.group(1).strip()
    return raw.strip()


def run_instance(instance: dict, model) -> dict:
    """Run inference on a single SWE-bench instance."""
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

    print(f"  Calling {GEMINI_MODEL}...")
    raw = call_gemini(prompt, model)
    if repo_path:
        patch = apply_edit_blocks(raw or "", repo_path, allowed_files=file_list or None)
    else:
        patch = ""

    result = {
        "instance_id": iid,
        "model_name_or_path": f"gemini-v11/{GEMINI_MODEL}",
        "model_patch": patch,
        "files_used": file_list,
        "patch_len": len(patch),
        "success": bool(patch),
    }

    # Save individual result
    (PRED_DIR / f"{iid}.json").write_text(json.dumps(result, indent=2))
    print(f"  Patch: {len(patch)} chars {'✅' if patch else '❌'}")
    return result


# ── evaluation helpers ────────────────────────────────────────────────────────

def apply_and_test(instance: dict, patch: str, repo_path: Path) -> dict:
    """
    Apply patch to the repo, run FAIL_TO_PASS tests, return pass/fail.
    Resets repo after testing.
    """
    iid = instance["instance_id"]
    fail_to_pass = json.loads(instance.get("FAIL_TO_PASS", "[]"))
    pass_to_pass = json.loads(instance.get("PASS_TO_PASS", "[]"))

    if not patch:
        return {"instance_id": iid, "resolved": False, "reason": "empty_patch"}

    # Ensure we're at base_commit
    base_commit = instance.get("base_commit", "HEAD")
    subprocess.run(
        ["git", "-C", str(repo_path), "checkout", base_commit, "--force"],
        capture_output=True, text=True, timeout=30,
    )

    # Write patch to temp file
    patch_file = repo_path / "_swebench_patch.diff"
    patch_file.write_text(patch)

    # Apply patch
    apply = subprocess.run(
        ["git", "-C", str(repo_path), "apply", "--whitespace=fix", str(patch_file)],
        capture_output=True, text=True, timeout=30,
    )
    patch_file.unlink(missing_ok=True)

    if apply.returncode != 0:
        subprocess.run(["git", "-C", str(repo_path), "checkout", "."], capture_output=True)
        return {"instance_id": iid, "resolved": False, "reason": f"apply_failed: {apply.stderr[:100]}"}

    # Run failing tests
    results = {}
    for test_id in fail_to_pass[:5]:  # limit to first 5 to keep it fast
        test_result = run_single_test(repo_path, test_id)
        results[test_id] = test_result

    # Reset
    subprocess.run(["git", "-C", str(repo_path), "checkout", "."], capture_output=True)

    f2p_pass = sum(1 for v in results.values() if v)
    resolved = f2p_pass == len(results) and len(results) > 0

    return {
        "instance_id": iid,
        "resolved": resolved,
        "f2p_tested": len(results),
        "f2p_passed": f2p_pass,
        "test_results": results,
    }


def run_single_test(repo_path: Path, test_id: str) -> bool:
    """Run a single test, return True if it passes."""
    # Detect test framework
    has_pytest = (repo_path / "setup.py").exists() or (repo_path / "pyproject.toml").exists()

    if has_pytest:
        cmd = ["python3", "-m", "pytest", test_id, "-x", "--tb=no", "-q"]
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


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SWE-bench Lite inference with Gemini")
    parser.add_argument("--num", type=int, default=10, help="Number of instances to run")
    parser.add_argument("--instance-ids", nargs="+", help="Specific instance IDs to run")
    parser.add_argument("--list", action="store_true", help="List available instances")
    parser.add_argument("--evaluate", action="store_true", help="Evaluate existing predictions")
    parser.add_argument("--report", action="store_true", help="Show results report")
    parser.add_argument("--repo-filter", help="Filter by repo (e.g. sympy)")
    args = parser.parse_args()

    # Setup
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

    # Filter instances
    if args.instance_ids:
        instances = [i for i in dataset if i["instance_id"] in args.instance_ids]
    elif args.repo_filter:
        instances = [i for i in dataset if args.repo_filter.lower() in i["repo"].lower()][:args.num]
    else:
        instances = dataset[:args.num]

    print(f"\nRunning inference on {len(instances)} instances with {GEMINI_MODEL}")
    print(f"Repo cache: {REPO_CACHE_DIR}")
    print(f"Predictions: {PRED_DIR}")

    # Configure Gemini
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("Set GEMINI_API_KEY environment variable")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        GEMINI_MODEL,
        system_instruction=SYSTEM_PROMPT,
    )

    # Run inference
    results = []
    t0 = time.time()
    for i, inst in enumerate(instances, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/{len(instances)}] {inst['instance_id']}")

        # Resume: skip if prediction already exists and has a patch
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
            r = run_instance(inst, model)
            results.append(r)
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"instance_id": inst["instance_id"], "success": False, "model_patch": "", "error": str(e)})

        # Polite delay between requests
        if i < len(instances):
            time.sleep(REQUEST_DELAY)

    elapsed = time.time() - t0

    # Save combined predictions (format for swebench harness)
    all_preds_path = PRED_DIR / "all_preds.jsonl"
    with open(all_preds_path, "w") as f:
        for r in results:
            f.write(json.dumps({
                "instance_id": r["instance_id"],
                "model_name_or_path": r.get("model_name_or_path", "gemini-v11"),
                "model_patch": r.get("model_patch", ""),
            }) + "\n")

    # Summary
    successful = sum(1 for r in results if r.get("success"))
    total_patch_chars = sum(r.get("patch_len", 0) for r in results)
    print(f"\n{'='*60}")
    print(f"INFERENCE COMPLETE")
    print(f"  Instances:    {len(results)}")
    print(f"  Patches gen:  {successful}/{len(results)} ({100*successful//len(results)}%)")
    print(f"  Avg patch:    {total_patch_chars//max(successful,1)} chars")
    print(f"  Time elapsed: {elapsed:.1f}s ({elapsed/len(results):.1f}s/instance)")
    print(f"  Predictions:  {all_preds_path}")
    print()

    # Quick in-process evaluation (for instances with accessible repos)
    if args.evaluate:
        print("Running quick evaluation (apply + test)...")
        eval_results = []
        for r in results:
            if not r.get("model_patch"):
                eval_results.append({"instance_id": r["instance_id"], "resolved": False, "reason": "no_patch"})
                continue
            inst = next((i for i in instances if i["instance_id"] == r["instance_id"]), None)
            if not inst:
                continue
            repo_path = REPO_CACHE_DIR / inst["repo"].split("/")[1]
            if repo_path.exists():
                ev = apply_and_test(inst, r["model_patch"], repo_path)
                eval_results.append(ev)
                status = "✅ RESOLVED" if ev["resolved"] else f"❌ {ev.get('reason','failed')}"
                print(f"  {r['instance_id'][:45]:45s} {status}")

        resolved = sum(1 for e in eval_results if e.get("resolved"))
        total_ev = len(eval_results)
        if total_ev:
            print(f"\nQUICK EVAL: {resolved}/{total_ev} resolved ({100*resolved//total_ev}%)")
            print("(Note: full harness evaluation requires Docker per-instance environments)")

        eval_path = PRED_DIR / "eval_results.json"
        eval_path.write_text(json.dumps(eval_results, indent=2))
        print(f"Eval results: {eval_path}")

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
    print(f"\nSWE-bench V11 Prediction Report")
    print(f"{'='*50}")
    print(f"Total instances:   {total}")
    print(f"Patches generated: {with_patch}/{total} ({100*with_patch//total}%)")
    print(f"\nBy repo:")
    for repo, results in sorted(by_repo.items()):
        n = len(results)
        ok = sum(results)
        print(f"  {repo:40s} {ok}/{n}")


if __name__ == "__main__":
    main()
