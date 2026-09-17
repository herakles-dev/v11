#!/usr/bin/env python3
"""
SWE-bench Claude Code CLI Agent (Phase 10.5).

Uses `claude -p` (Claude Code CLI) as a subprocess with real Bash access to a
per-instance git worktree. Patch extraction uses `git diff {base_commit}` —
ground truth, no parsing fragility.

Architecture (per instance):
  [Setup]    git worktree add --detach /tmp/swe-worktrees/{id} {base_commit}
  [Agent]    claude -p "..." --model opus --dangerously-skip-permissions ...
               ← Claude uses real Bash, Edit, Grep to explore + fix
  [Patch]    git diff {base_commit}  →  model_patch
  [Cleanup]  git worktree remove --force /tmp/swe-worktrees/{id}
  [Output]   all_preds.jsonl + trajs/{instance_id}.jsonl

Advantage over swe_v11.py:
  - Claude has real shell access (grep, cat, git log, python -m pytest)
  - Patch is extracted via git diff — ground truth, no FIND/REPLACE fragility
  - Matches top SWE-bench system methodology (SWE-agent, Agentless+)

Usage:
    python3 swe_claude_code_agent.py --num 1 --instance-ids astropy__astropy-12907
    python3 swe_claude_code_agent.py --num 5
    python3 swe_claude_code_agent.py --num 50 --repo-filter django --workers 3
    python3 swe_claude_code_agent.py --report
    python3 swe_claude_code_agent.py --list

Output:
    swebench-predictions/v11-claude-code/all_preds.jsonl    (harness-ready)
    swebench-predictions/v11-claude-code/trajs/{id}.jsonl   (cost, turns, timing)
    swebench-predictions/v11-claude-code/{id}.json          (per-instance detail)
"""

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

try:
    from datasets import load_dataset
except ImportError:
    sys.exit("Install datasets: pip install datasets")

# ── Config ────────────────────────────────────────────────────────────────────

CLAUDE_BIN      = "/path/to/operator-home/.local/bin/claude"
REPO_CACHE_DIR  = Path("/path/to/v11/swebench-repos")
DEFAULT_PRED_DIR = Path("/path/to/v11/swebench-predictions/v11-claude-code")
WORKTREE_BASE   = Path("/tmp/swe-worktrees")

DEFAULT_MODEL   = "claude-opus-4-6"
DEFAULT_BUDGET  = 0.50
DEFAULT_WORKERS = 1
REQUEST_DELAY   = 2.0   # seconds between sequential instances

# ── Agent Prompt ──────────────────────────────────────────────────────────────

PROMPT_TEMPLATE = """\
You are a software engineer fixing a real GitHub bug. Work in the CURRENT directory (the repository root).

## The Bug

{problem_statement}

## PHASE 0 — INVESTIGATE (spec-architect-v11)

Your first job is to understand the bug thoroughly BEFORE touching any code.

1. Run the failing tests to observe the error:
{fail_to_pass_cmds}

2. Explore the codebase to find the root cause:
   - Use Bash to run `git log --oneline -10`, `grep -rn "keyword" .`, or read relevant files
   - Use Read to inspect specific files, Glob to find files by pattern
   - Use Grep for fast code search across the repo

3. Form a clear hypothesis about root cause. DO NOT EDIT FILES YET.

## PHASE 1 — IMPLEMENT (spec-implementer-v11)

Once you understand the root cause:

4. Edit the source file(s) using the Edit tool
5. Keep changes minimal and targeted — fix only the root cause
6. Do NOT modify test files or add new features

## PHASE 2 — VALIDATE (spec-tester-v11)

After editing:

7. Re-run the failing tests:
{fail_to_pass_cmds}

8. If tests still fail, analyze the error output carefully and fix your implementation
9. Retry up to 3 times total
10. Stop when all listed tests pass (or after 3 attempts)

## Important Rules

- Fix only the root cause. Minimal changes. No new features.
- Do NOT modify test files.
- Work only in the current directory.
- The tests that must pass:
{fail_to_pass_list}
"""


# ── Dataset ───────────────────────────────────────────────────────────────────

def load_lite_dataset() -> list[dict]:
    """Load SWE-bench Lite (300 instances) from HuggingFace."""
    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    return [dict(row) for row in ds]


def clone_or_update_repo(repo: str, base_commit: str) -> Optional[Path]:
    """
    Ensure a shared repo cache exists at REPO_CACHE_DIR/{name} and the
    base_commit is present. Returns the repo path, or None on failure.
    """
    _, name = repo.split("/")
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

    # Verify commit is present
    result = subprocess.run(
        ["git", "-C", str(local), "cat-file", "-t", base_commit],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        # Try deeper fetch first
        subprocess.run(
            ["git", "-C", str(local), "fetch", "--depth=500", "origin"],
            capture_output=True, text=True, timeout=60,
        )
        result2 = subprocess.run(
            ["git", "-C", str(local), "cat-file", "-t", base_commit],
            capture_output=True, text=True,
        )
        if result2.returncode != 0:
            print(f"  Commit {base_commit[:8]} not in depth-500 history, unshallowing...")
            subprocess.run(
                ["git", "-C", str(local), "fetch", "--unshallow", "origin"],
                capture_output=True, text=True, timeout=300,
            )

    return local


# ── Worktree Management ───────────────────────────────────────────────────────

def setup_worktree(repo_path: Path, base_commit: str, worktree_path: Path) -> bool:
    """
    Create an isolated git worktree at worktree_path pointing to base_commit.
    Zero disk copy overhead — hardlinks objects from shared repo cache.
    Returns True on success.
    """
    # Remove stale worktree if it exists
    if worktree_path.exists():
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=str(repo_path), capture_output=True,
        )

    r = subprocess.run(
        ["git", "worktree", "add", "--detach", str(worktree_path), base_commit],
        cwd=str(repo_path), capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        print(f"  Worktree creation failed: {r.stderr[:200]}")
        return False
    return True


def teardown_worktree(repo_path: Path, worktree_path: Path):
    """Remove git worktree and prune stale references."""
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        cwd=str(repo_path), capture_output=True, timeout=30,
    )
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=str(repo_path), capture_output=True, timeout=15,
    )


def extract_patch(worktree_path: Path, base_commit: str) -> str:
    """
    Extract the unified diff of all changes Claude made, relative to base_commit.
    Ground truth — captures exactly what was edited, no output parsing.
    """
    r = subprocess.run(
        ["git", "diff", base_commit],
        cwd=str(worktree_path), capture_output=True, text=True, timeout=30,
    )
    return r.stdout.strip()


# ── Prompt Building ───────────────────────────────────────────────────────────

def build_prompt(instance: dict) -> str:
    """Build the 3-phase V11 agent prompt for the given SWE-bench instance."""
    fail_to_pass = json.loads(instance.get("FAIL_TO_PASS", "[]"))

    if fail_to_pass:
        cmds = []
        for test_id in fail_to_pass[:5]:
            if "::" in test_id or test_id.endswith(".py"):
                cmds.append(f"   python -m pytest {test_id} -x --tb=short -q")
            else:
                cmds.append(f"   python -m pytest -x --tb=short -q -k '{test_id}'")
        fail_to_pass_cmds = "\n".join(cmds)
        fail_to_pass_list = "\n".join(f"   - {t}" for t in fail_to_pass[:8])
    else:
        fail_to_pass_cmds = "   (no specific test IDs — explore the test suite)"
        fail_to_pass_list = "   (no specific test IDs provided)"

    return PROMPT_TEMPLATE.format(
        problem_statement=instance["problem_statement"][:4000],
        fail_to_pass_cmds=fail_to_pass_cmds,
        fail_to_pass_list=fail_to_pass_list,
    )


# ── Claude CLI ────────────────────────────────────────────────────────────────

def run_claude_cli(prompt: str, worktree_path: Path, budget_usd: float,
                   model: str = DEFAULT_MODEL) -> dict:
    """
    Run `claude -p PROMPT` as a subprocess in the worktree with real Bash access.

    Claude Code JSON output format:
      {"type":"result","subtype":"success","cost_usd":0.43,"num_turns":12,...}

    Returns parsed dict, or {"type":"error","error":"..."} on failure.
    """
    env = {**os.environ}
    # Prevent nested Claude detection
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)

    if not env.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set. Run: source ~/.secrets/app.env")

    cmd = [
        CLAUDE_BIN,
        "-p", prompt,
        "--model", model,
        "--dangerously-skip-permissions",
        "--output-format", "json",
        "--no-session-persistence",
        "--allowed-tools", "Bash,Edit,Read,Write,Glob,Grep",
        "--max-budget-usd", str(budget_usd),
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
            env=env,
            timeout=600,    # 10 min max per instance
        )

        stderr_preview = (result.stderr or "")[:300]
        if result.returncode != 0:
            print(f"  claude CLI exit {result.returncode}: {stderr_preview}")

        stdout = (result.stdout or "").strip()
        if not stdout:
            return {"type": "error", "error": f"no stdout (exit {result.returncode})"}

        # Parse JSON — the last JSON object on stdout is the result
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            # stdout may have trailing log lines — find the last valid JSON object
            for line in reversed(stdout.splitlines()):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        pass
            return {"type": "error", "error": "json_parse_failed",
                    "stdout_preview": stdout[-200:]}

    except subprocess.TimeoutExpired:
        print(f"  claude CLI timed out (600s)")
        return {"type": "error", "error": "timeout_600s"}
    except Exception as e:
        print(f"  claude CLI exception: {e}")
        return {"type": "error", "error": str(e)}


# ── Trajectory Logging ────────────────────────────────────────────────────────

def save_traj(traj_path: Path, event: str, data: dict):
    """Append a timestamped event to the instance's JSONL trajectory file."""
    entry = {"ts": round(time.time(), 3), "event": event, **data}
    with open(traj_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ── Per-Instance Pipeline ─────────────────────────────────────────────────────

def run_instance(instance: dict, pred_dir: Path, budget_usd: float,
                 model: str = DEFAULT_MODEL) -> dict:
    """
    Full pipeline for one SWE-bench instance:
      1. Clone/update repo cache
      2. Create isolated git worktree at base_commit
      3. Run claude CLI (real Bash access in worktree)
      4. Extract patch via git diff
      5. Teardown worktree
      6. Write prediction + trajectory files
    """
    iid = instance["instance_id"]
    repo = instance["repo"]
    base_commit = instance.get("base_commit", "HEAD")
    model_slug = f"v11-claude-code/{model}"

    traj_dir = pred_dir / "trajs"
    traj_dir.mkdir(parents=True, exist_ok=True)
    traj_path = traj_dir / f"{iid}.jsonl"

    # Resume if already done
    pred_file = pred_dir / f"{iid}.json"
    if pred_file.exists():
        try:
            data = json.loads(pred_file.read_text())
            if data.get("success") and data.get("model_patch"):
                print(f"  ↩️  Already done: {iid}")
                return data
        except Exception:
            pass

    t0 = time.time()
    worktree_path = WORKTREE_BASE / iid
    repo_path: Optional[Path] = None

    try:
        # Step 1: Ensure repo cache
        print(f"  Ensuring repo cache: {repo}")
        repo_path = clone_or_update_repo(repo, base_commit)
        if repo_path is None:
            result = {
                "instance_id": iid,
                "model_name_or_path": model_slug,
                "model_patch": "",
                "success": False,
                "error": "clone_failed",
                "duration_s": round(time.time() - t0, 1),
            }
            pred_file.write_text(json.dumps(result, indent=2))
            return result

        save_traj(traj_path, "setup_start", {
            "repo": repo, "base_commit": base_commit[:12]
        })

        # Step 2: Create worktree
        WORKTREE_BASE.mkdir(parents=True, exist_ok=True)
        print(f"  Creating worktree at {worktree_path}")
        if not setup_worktree(repo_path, base_commit, worktree_path):
            result = {
                "instance_id": iid,
                "model_name_or_path": model_slug,
                "model_patch": "",
                "success": False,
                "error": "worktree_failed",
                "duration_s": round(time.time() - t0, 1),
            }
            pred_file.write_text(json.dumps(result, indent=2))
            return result

        save_traj(traj_path, "worktree_ready", {"path": str(worktree_path)})

        # Step 3: Build prompt and run claude CLI
        prompt = build_prompt(instance)
        print(f"  Running claude CLI (budget: ${budget_usd:.2f})...")
        t_agent = time.time()
        cli_output = run_claude_cli(prompt, worktree_path, budget_usd, model)
        agent_duration = round(time.time() - t_agent, 1)

        # Field name in claude CLI JSON output is "total_cost_usd"
        cost_usd  = cli_output.get("total_cost_usd", cli_output.get("cost_usd", 0.0))
        num_turns = cli_output.get("num_turns", 0)
        subtype   = cli_output.get("subtype", "unknown")
        cli_error = cli_output.get("error", None)

        print(f"  Agent: subtype={subtype}, turns={num_turns}, "
              f"cost=${cost_usd:.3f}, time={agent_duration}s")

        save_traj(traj_path, "agent_complete", {
            "subtype": subtype, "num_turns": num_turns,
            "cost_usd": cost_usd, "agent_duration_s": agent_duration,
            "error": cli_error,
        })

        # Step 4: Extract patch via git diff
        print(f"  Extracting patch (git diff {base_commit[:8]})...")
        patch = extract_patch(worktree_path, base_commit)

        save_traj(traj_path, "patch_extracted", {"patch_len": len(patch)})
        print(f"  Patch: {len(patch)} chars {'✅' if patch else '❌ (empty)'}")

        # Step 5: Build result
        duration_s = round(time.time() - t0, 1)
        result = {
            "instance_id": iid,
            "model_name_or_path": model_slug,
            "model_patch": patch,
            "success": bool(patch),
            "cost_usd": cost_usd,
            "num_turns": num_turns,
            "duration_s": duration_s,
            "agent_subtype": subtype,
            "cli_error": cli_error,
        }

        pred_file.write_text(json.dumps(result, indent=2))
        save_traj(traj_path, "instance_complete", {
            "success": bool(patch), "patch_len": len(patch),
            "duration_s": duration_s, "cost_usd": cost_usd,
        })

        return result

    finally:
        # Always clean up worktree, even on error
        if repo_path is not None and worktree_path.exists():
            print(f"  Cleaning up worktree...")
            teardown_worktree(repo_path, worktree_path)


# ── Batch Runner ──────────────────────────────────────────────────────────────

def run_batch(instances: list, pred_dir: Path,
              workers: int, budget_usd: float,
              model: str = DEFAULT_MODEL) -> list[dict]:
    """Run instances sequentially or in parallel."""
    results: list[dict] = []
    lock = threading.Lock()
    model_slug = f"v11-claude-code/{model}"

    def process_one(instance: dict) -> dict:
        try:
            r = run_instance(instance, pred_dir, budget_usd, model)
        except Exception as e:
            r = {
                "instance_id": instance["instance_id"],
                "model_name_or_path": model_slug,
                "model_patch": "",
                "success": False,
                "error": str(e),
            }
        with lock:
            results.append(r)
            n = len(results)
            patch_status = f"patch({len(r.get('model_patch',''))}c)" if r.get("model_patch") else "no-patch"
            print(f"  [{n}/{len(instances)}] {instance['instance_id']}: "
                  f"{patch_status} ${r.get('cost_usd',0):.3f}")
        return r

    if workers > 1 and len(instances) > 1:
        print(f"\nParallel mode: {workers} workers, {len(instances)} instances")
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(process_one, inst) for inst in instances]
            concurrent.futures.wait(futures)
    else:
        for i, inst in enumerate(instances, 1):
            print(f"\n{'='*60}")
            print(f"[{i}/{len(instances)}] {inst['instance_id']}")
            process_one(inst)
            if i < len(instances):
                time.sleep(REQUEST_DELAY)

    return results


# ── Report ────────────────────────────────────────────────────────────────────

def show_report(pred_dir: Path):
    """Display statistics from completed prediction files."""
    files = list(pred_dir.glob("*.json"))
    if not files:
        print(f"No predictions found in {pred_dir}")
        return

    total        = len(files)
    with_patch   = 0
    total_cost   = 0.0
    total_turns  = 0
    total_dur    = 0.0
    by_repo: dict[str, dict] = {}
    errors: list[str] = []

    for f in sorted(files):
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue

        iid  = data.get("instance_id", f.stem)
        repo = iid.rsplit("__", 1)[0].replace("__", "/") if "__" in iid else "unknown"

        if data.get("model_patch"):
            with_patch += 1
        if data.get("cli_error") or data.get("error"):
            errors.append(f"{iid}: {data.get('cli_error') or data.get('error')}")

        total_cost  += data.get("cost_usd", 0.0)
        total_turns += data.get("num_turns", 0)
        total_dur   += data.get("duration_s", 0.0)

        if repo not in by_repo:
            by_repo[repo] = {"total": 0, "with_patch": 0}
        by_repo[repo]["total"] += 1
        if data.get("model_patch"):
            by_repo[repo]["with_patch"] += 1

    print(f"\n{'='*60}")
    print(f"V11 CLAUDE CODE AGENT REPORT")
    print(f"{'='*60}")
    print(f"  Dir:         {pred_dir}")
    print(f"  Instances:   {total}")
    print(f"  With patch:  {with_patch}/{total} ({100*with_patch//max(total,1)}%)")
    print(f"  Total cost:  ${total_cost:.2f}")
    print(f"  Avg cost:    ${total_cost/max(total,1):.3f}/instance")
    print(f"  Avg turns:   {total_turns/max(total,1):.1f}")
    print(f"  Avg time:    {total_dur/max(total,1):.1f}s/instance")

    print(f"\nBy repo:")
    for repo, stats in sorted(by_repo.items()):
        pct = 100 * stats["with_patch"] // max(stats["total"], 1)
        print(f"  {repo:45s} {stats['with_patch']:3d}/{stats['total']:3d} ({pct}%)")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors[:10]:
            print(f"  {e}")
        if len(errors) > 10:
            print(f"  ... ({len(errors) - 10} more)")

    all_preds_path = pred_dir / "all_preds.jsonl"
    if all_preds_path.exists():
        print(f"\nHarness eval command:")
        print(f"  python -m swebench.harness.run_evaluation \\")
        print(f"      --predictions_path {all_preds_path} \\")
        print(f"      --swe_bench_tasks princeton-nlp/SWE-bench_Lite \\")
        print(f"      --run_id v11-claude-code \\")
        print(f"      --max_workers 4")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SWE-bench Phase 10.5: Claude Code CLI agent with real Bash access",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Phase A: 1-instance pilot (inspect worktree + patch)
  python3 swe_claude_code_agent.py --instance-ids astropy__astropy-12907

  # Phase C: 5-instance comparison vs swe_v11
  python3 swe_claude_code_agent.py --num 5

  # Phase D: 50-instance pilot, 3 workers
  python3 swe_claude_code_agent.py --num 50 --repo-filter django --workers 3

  # Phase E: full 300-instance run
  python3 swe_claude_code_agent.py --num 300 --workers 5

  # View report on completed runs
  python3 swe_claude_code_agent.py --report
""",
    )
    parser.add_argument("--num", type=int, default=5,
                        help="Number of instances to run (default: 5)")
    parser.add_argument("--instance-ids", nargs="+",
                        help="Specific instance IDs to run")
    parser.add_argument("--repo-filter",
                        help="Filter by repo name (e.g. django, sympy, astropy)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Parallel workers (default: {DEFAULT_WORKERS})")
    parser.add_argument("--budget", type=float, default=DEFAULT_BUDGET,
                        help=f"Per-instance budget cap in USD (default: {DEFAULT_BUDGET})")
    parser.add_argument("--out", type=str, default=None,
                        help=f"Output directory (default: {DEFAULT_PRED_DIR})")
    parser.add_argument("--list", action="store_true",
                        help="List first 30 instances and exit")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        help=f"Claude model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--report", action="store_true",
                        help="Show report on completed predictions and exit")
    args = parser.parse_args()

    pred_dir = Path(args.out) if args.out else DEFAULT_PRED_DIR
    pred_dir.mkdir(parents=True, exist_ok=True)
    (pred_dir / "trajs").mkdir(parents=True, exist_ok=True)
    REPO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    WORKTREE_BASE.mkdir(parents=True, exist_ok=True)

    if args.report:
        show_report(pred_dir)
        return

    # Load dataset
    print("Loading SWE-bench Lite dataset (300 instances)...")
    dataset = load_lite_dataset()
    print(f"Loaded {len(dataset)} instances")

    if args.list:
        print(f"\nFirst 30 instances:")
        for inst in dataset[:30]:
            print(f"  {inst['instance_id']:55s}  {inst['repo']}")
        print(f"  ... ({len(dataset)} total)")
        return

    # Select instances
    if args.instance_ids:
        instances = [i for i in dataset if i["instance_id"] in args.instance_ids]
        if not instances:
            sys.exit(f"No instances matched: {args.instance_ids}")
    elif args.repo_filter:
        instances = [
            i for i in dataset
            if args.repo_filter.lower() in i["repo"].lower()
        ][:args.num]
    else:
        instances = dataset[:args.num]

    if not instances:
        sys.exit("No instances matched the filters")

    # Validate prerequisites
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY not set. Run: source ~/.secrets/app.env")
    if not Path(CLAUDE_BIN).exists():
        sys.exit(f"Claude CLI not found at {CLAUDE_BIN}")

    est_cost = len(instances) * args.budget
    print(f"\nV11 Claude Code Agent (Phase 10.5)")
    print(f"  Model:        {args.model}")
    print(f"  Budget cap:   ${args.budget:.2f}/instance")
    print(f"  Workers:      {args.workers}")
    print(f"  Instances:    {len(instances)}")
    print(f"  Est. max:     ${est_cost:.2f}")
    print(f"  Repo cache:   {REPO_CACHE_DIR}")
    print(f"  Output:       {pred_dir}")
    print(f"  Worktrees:    {WORKTREE_BASE}")

    t0 = time.time()
    results = run_batch(instances, pred_dir, workers=args.workers,
                        budget_usd=args.budget, model=args.model)
    elapsed = time.time() - t0

    # Write harness-ready all_preds.jsonl
    all_preds_path = pred_dir / "all_preds.jsonl"
    with open(all_preds_path, "w") as f:
        for r in results:
            f.write(json.dumps({
                "instance_id": r["instance_id"],
                "model_name_or_path": r.get("model_name_or_path", f"v11-claude-code/{args.model}"),
                "model_patch": r.get("model_patch", ""),
            }) + "\n")

    successful  = sum(1 for r in results if r.get("model_patch"))
    total_cost  = sum(r.get("cost_usd", 0.0) for r in results)
    avg_turns   = sum(r.get("num_turns", 0) for r in results) / max(len(results), 1)
    avg_dur     = elapsed / max(len(results), 1)

    print(f"\n{'='*60}")
    print(f"PHASE 10.5 COMPLETE — V11 Claude Code Agent")
    print(f"  Model:        {args.model} (via claude CLI)")
    print(f"  Instances:    {len(results)}")
    print(f"  With patch:   {successful}/{len(results)} ({100*successful//max(len(results),1)}%)")
    print(f"  Total cost:   ${total_cost:.2f}")
    print(f"  Avg cost:     ${total_cost/max(len(results),1):.3f}/instance")
    print(f"  Avg turns:    {avg_turns:.1f}")
    print(f"  Time elapsed: {elapsed:.1f}s ({avg_dur:.1f}s/instance)")
    print(f"  Predictions:  {all_preds_path}")
    print(f"  Traces:       {pred_dir}/trajs/")
    print()
    print("Next: run official harness evaluation:")
    print(f"  python -m swebench.harness.run_evaluation \\")
    print(f"      --predictions_path {all_preds_path} \\")
    print(f"      --swe_bench_tasks princeton-nlp/SWE-bench_Lite \\")
    print(f"      --run_id v11-claude-code \\")
    print(f"      --max_workers 4")


if __name__ == "__main__":
    main()
