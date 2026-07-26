"""
Core benchmark runner — loads YAML tasks, dispatches to executors, collects results.

Reuses fire_hooks() and scaffold_v11_project() patterns from test_e2e_v11_pipeline.py.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .scoring import CategoryScore, TierScore, compute_category_scores, compute_composite
from .ledger import get_last_tier_scores, append_result
from .regression import Regression, detect_regressions, has_blocking_regressions

V11_ROOT = Path(__file__).parent.parent
HOOKS_DIR = V11_ROOT / "hooks"
SETTINGS_PATH = V11_ROOT / ".claude" / "settings.json"
TASKS_DIR = Path(__file__).parent / "tasks"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── Hook execution (from test_e2e_v11_pipeline.py) ────────────────────────────

def run_hook(hook_path: str, payload: dict, env: dict,
             cwd: str | None = None, timeout: int = 8) -> tuple[int, str, str]:
    """Run a single hook via subprocess."""
    r = subprocess.run(
        [hook_path],
        input=json.dumps(payload),
        capture_output=True, text=True,
        timeout=timeout, env=env, cwd=cwd,
    )
    return r.returncode, r.stdout, r.stderr


def fire_hooks(event_type: str, matcher_tool: str, payload: dict,
               env: dict, cwd: str | None = None) -> list[dict]:
    """Fire ALL hooks matching a tool event, in order, from settings.json."""
    settings = json.loads(SETTINGS_PATH.read_text())
    entries = settings.get("hooks", {}).get(event_type, [])
    results = []
    for entry in entries:
        matcher = entry.get("matcher", "")
        patterns = matcher.split("|") if matcher else []
        matched = any(matcher_tool == p or matcher_tool.startswith(p) for p in patterns)
        if not matched and matcher:
            continue
        for hook_def in entry.get("hooks", []):
            cmd = hook_def.get("command", "")
            if not cmd or not os.path.isfile(cmd):
                continue
            code, out, err = run_hook(cmd, payload, env, cwd=cwd)
            results.append({
                "hook": os.path.basename(cmd),
                "exit_code": code,
                "stdout": out,
                "stderr": err,
            })
    return results


# ── V11 project scaffold (from test_e2e_v11_pipeline.py) ──────────────────────

def scaffold_v11_project(tmp_path: Path, project_name: str = "bench") -> tuple[Path, Path, dict]:
    """Create a realistic V11 project structure. Returns (project_dir, workspace_root, env)."""
    workspace_root = tmp_path / "workspace"
    sessions = workspace_root / "sessions"
    project = sessions / project_name
    src_dir = project / "src"
    tests_dir = project / "tests"
    metrics_dir = workspace_root / ".agent-metrics"
    task_state_dir = metrics_dir / "task-state"

    for d in [src_dir, tests_dir, metrics_dir, task_state_dir]:
        d.mkdir(parents=True, exist_ok=True)

    (project / "spec.md").write_text(
        f"# {project_name}\n\n## Intent\nBenchmark validation.\n"
    )
    (project / ".autonomy-state").write_text(json.dumps({
        "level": 0, "successful": 0, "errors": 0, "rollbacks": 0,
        "approved_categories": [], "grants": [],
        "high_risk_history": [], "recent_errors": [],
        "last_updated": "2026-01-01T00:00:00Z",
    }))

    registry = {
        "formation": "feature-impl",
        "project": project_name,
        "created_at": "2026-03-16T00:00:00Z",
        "heartbeat_interval_minutes": 10,
        "teammates": {
            "backend-impl": {
                "agent": "spec-implementer-v11",
                "agent_id": "backend-impl",
                "ownership": {
                    "directories": [str(src_dir) + "/"],
                    "files": [], "patterns": [],
                },
                "tool_policies": {"profile": "coding"},
            },
            "tester": {
                "agent": "spec-tester-v11",
                "agent_id": "tester",
                "ownership": {
                    "directories": [str(tests_dir) + "/"],
                    "files": [], "patterns": [],
                },
                "tool_policies": {"profile": "testing"},
            },
        },
    }
    (project / ".formation-registry.json").write_text(json.dumps(registry, indent=2))
    (src_dir / "app.py").write_text("def hello():\n    return 'world'\n")
    (tests_dir / "test_app.py").write_text("def test_hello():\n    assert True\n")
    (metrics_dir / "active-project").write_text(project_name)

    env = {
        **os.environ,
        "SESSIONS_ROOT": str(sessions),
        "V11_WORKSPACE_ROOT": str(workspace_root),
        "V11_SESSION_PROJECT": project_name,
        "HOME": str(workspace_root),
        "NO_COLOR": "1",
        "TERM": "dumb",
    }
    return project, workspace_root, env


# ── YAML task loader ──────────────────────────────────────────────────────────

def load_tasks(tier: int) -> list[dict]:
    """Load all YAML task definitions for a given tier (and below)."""
    if not TASKS_DIR.exists():
        return []
    tasks = []
    for yml_file in sorted(TASKS_DIR.glob("BT-*.yml")):
        try:
            task = yaml.safe_load(yml_file.read_text())
            if task and task.get("tier", 0) <= tier:
                task["_file"] = str(yml_file)
                tasks.append(task)
        except yaml.YAMLError:
            continue
    return tasks


# ── Task executors ─────────────────────────────────────────────────────────────

def _exec_hook_chain(task: dict, project: Path, env: dict) -> dict:
    """Execute a hook-chain benchmark task."""
    steps = task.get("steps", [])
    errors = []

    for step in steps:
        event = step.get("event", "PreToolUse")
        tool = step.get("tool", "Write")
        payload = step.get("payload", {})
        if not payload.get("session_id"):
            payload["session_id"] = "bench-session"
        if not payload.get("tool_name"):
            payload["tool_name"] = tool

        step_env = {**env}
        if step.get("agent_id"):
            step_env["V11_AGENT_ID"] = step["agent_id"]

        try:
            results = fire_hooks(event, tool, payload, step_env, cwd=str(project))
        except Exception as e:
            errors.append(f"Step '{step.get('name', '?')}' failed: {e}")
            continue

        # Check assertions
        for assertion in step.get("assertions", []):
            atype = assertion.get("type")
            if atype == "hook_fired":
                hook_names = [r["hook"] for r in results]
                expected = assertion["hook"]
                if expected not in hook_names:
                    errors.append(f"Expected hook '{expected}' to fire, got: {hook_names}")

            elif atype == "exit_code":
                hook_name = assertion.get("hook")
                expected_code = assertion.get("code", 0)
                matching = [r for r in results if r["hook"] == hook_name]
                if matching and matching[0]["exit_code"] != expected_code:
                    errors.append(
                        f"Hook '{hook_name}' exit code: {matching[0]['exit_code']}, expected {expected_code}"
                    )

            elif atype == "hook_order":
                hook_names = [r["hook"] for r in results]
                before = assertion.get("before")
                after = assertion.get("after")
                if before in hook_names and after in hook_names:
                    if hook_names.index(before) >= hook_names.index(after):
                        errors.append(f"Hook '{before}' should fire before '{after}'")

            elif atype == "output_contains":
                hook_name = assertion.get("hook")
                text = assertion.get("text", "").lower()
                matching = [r for r in results if r["hook"] == hook_name]
                if matching:
                    combined = (matching[0]["stdout"] + matching[0]["stderr"]).lower()
                    if text not in combined:
                        errors.append(f"Hook '{hook_name}' output doesn't contain '{text}'")

    return {"passed": len(errors) == 0, "errors": errors}


def _exec_task_lifecycle(task: dict, project: Path, env: dict) -> dict:
    """Execute a task-lifecycle benchmark (create, claim, complete)."""
    errors = []
    task_state_dir = Path(env["V11_WORKSPACE_ROOT"]) / ".agent-metrics" / "task-state"

    # Create
    fire_hooks("PostToolUse", "TaskCreate", {
        "tool_name": "TaskCreate",
        "tool_input": {
            "subject": "Benchmark task",
            "description": "lifecycle test",
            "metadata": {"project": env.get("V11_SESSION_PROJECT", "bench"),
                         "sprint": "sprint-01", "risk": "medium"},
        },
        "tool_output": "Task #1 created successfully: Benchmark task",
        "session_id": "bench-session",
    }, env)

    # Claim
    fire_hooks("PostToolUse", "TaskUpdate", {
        "tool_name": "TaskUpdate",
        "tool_input": {"taskId": "1", "status": "in_progress", "owner": "backend-impl"},
        "tool_output": "Updated task #1 status",
        "session_id": "bench-session",
    }, env)

    project_name = env.get("V11_SESSION_PROJECT", "bench")
    state_file = task_state_dir / f"{project_name}.json"
    if state_file.exists():
        state = json.loads(state_file.read_text())
        if "1" not in state.get("active_task_ids", []):
            errors.append("Task not in active_task_ids after claim")
        if state.get("active_agent_id") != "backend-impl":
            errors.append(f"agent_id: {state.get('active_agent_id')}, expected 'backend-impl'")
    else:
        errors.append("Task state file not created")

    # Complete
    fire_hooks("PostToolUse", "TaskUpdate", {
        "tool_name": "TaskUpdate",
        "tool_input": {"taskId": "1", "status": "completed"},
        "tool_output": "Updated task #1 status",
        "session_id": "bench-session",
    }, env)

    if state_file.exists():
        state = json.loads(state_file.read_text())
        if "1" in state.get("active_task_ids", []):
            errors.append("Task still in active_task_ids after completion")
        if state.get("completed", 0) < 1:
            errors.append("completed count not incremented")

    return {"passed": len(errors) == 0, "errors": errors}


def _exec_schema_validation(task: dict, project: Path, env: dict) -> dict:
    """Validate JSON schemas accept/reject known inputs."""
    errors = []
    schema_dir = V11_ROOT / "schemas"
    cases = task.get("cases", [])

    for case in cases:
        schema_file = schema_dir / case.get("schema", "")
        if not schema_file.exists():
            errors.append(f"Schema not found: {schema_file}")
            continue

        try:
            import jsonschema
            schema = json.loads(schema_file.read_text())
            instance = case.get("input", {})
            should_pass = case.get("valid", True)

            try:
                jsonschema.validate(instance, schema)
                if not should_pass:
                    errors.append(f"Schema {case['schema']} accepted invalid input")
            except jsonschema.ValidationError:
                if should_pass:
                    errors.append(f"Schema {case['schema']} rejected valid input")
        except ImportError:
            errors.append("jsonschema not installed")
            break

    return {"passed": len(errors) == 0, "errors": errors}


def _exec_latency_sla(task: dict, project: Path, env: dict) -> dict:
    """Measure hook latencies against SLA thresholds."""
    errors = []
    slas = task.get("slas", {})

    # Measure each hook using --test mode
    latencies = {}
    for hook_name, max_ms in slas.items():
        hook_path = HOOKS_DIR / hook_name
        if not hook_path.exists():
            errors.append(f"Hook not found: {hook_name}")
            continue

        start = time.monotonic()
        try:
            subprocess.run(
                [str(hook_path), "--test"],
                capture_output=True, text=True, timeout=5,
                env={**os.environ, "NO_COLOR": "1", "TERM": "dumb"},
            )
        except subprocess.TimeoutExpired:
            errors.append(f"Hook '{hook_name}' timed out (SLA: {max_ms}ms)")
            latencies[hook_name] = 5000
            continue
        elapsed_ms = (time.monotonic() - start) * 1000
        latencies[hook_name] = round(elapsed_ms, 1)

        if elapsed_ms > max_ms:
            errors.append(f"Hook '{hook_name}' latency {elapsed_ms:.0f}ms > SLA {max_ms}ms")

    return {"passed": len(errors) == 0, "errors": errors, "latencies": latencies}


def _exec_ownership_check(task: dict, project: Path, env: dict) -> dict:
    """Test file ownership enforcement across agents."""
    errors = []
    src_dir = project / "src"
    tests_dir = project / "tests"

    # Backend agent writing to own dir (should pass)
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(src_dir / "owned.py"), "content": "x = 1\n"},
        "session_id": "bench-session",
    }
    results = fire_hooks("PreToolUse", "Write", payload,
                         {**env, "V11_AGENT_ID": "backend-impl"}, cwd=str(project))
    for r in results:
        if r["hook"] == "guard-write-gates" and r["exit_code"] != 0:
            errors.append("Own directory write was blocked")

    # Backend agent writing to tester's dir (should warn/block)
    cross_payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(tests_dir / "cross.py"), "content": "x = 1\n"},
        "session_id": "bench-session",
    }
    results = fire_hooks("PreToolUse", "Write", cross_payload,
                         {**env, "V11_AGENT_ID": "backend-impl"}, cwd=str(project))
    gwg = [r for r in results if r["hook"] == "guard-write-gates"]
    if gwg:
        combined = (gwg[0]["stdout"] + gwg[0]["stderr"]).lower()
        if "ownership" not in combined and "conflict" not in combined and gwg[0]["exit_code"] == 0:
            errors.append("Cross-agent write not detected")

    return {"passed": len(errors) == 0, "errors": errors}


def _exec_live_cli(task: dict, project: Path, env: dict) -> dict:
    """Execute a live claude -p benchmark task."""
    prompt = task.get("prompt", "")
    model = task.get("model", "haiku")
    timeout = task.get("timeout", 120)
    assertions = task.get("assertions", [])
    errors = []
    cost_usd = 0.0

    # Check if claude CLI is available
    try:
        subprocess.run(["claude", "--version"], capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"passed": False, "errors": ["claude CLI not available"], "cost_usd": 0, "skipped": True}

    # Set up project with V11 settings
    import shutil
    claude_dir = project / ".claude"
    claude_dir.mkdir(exist_ok=True)
    if SETTINGS_PATH.exists():
        shutil.copy2(SETTINGS_PATH, claude_dir / "settings.json")

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", model,
             "--dangerously-skip-permissions", "--output-format", "json"],
            capture_output=True, text=True,
            timeout=timeout, env=env, cwd=str(project),
        )
    except subprocess.TimeoutExpired:
        return {"passed": False, "errors": [f"claude -p timed out after {timeout}s"], "cost_usd": 0}

    # Parse cost from JSON output
    try:
        output = json.loads(result.stdout)
        cost_usd = output.get("cost_usd", 0) or 0
    except (json.JSONDecodeError, TypeError):
        pass

    # Check assertions
    audit_log = Path(env["V11_WORKSPACE_ROOT"]) / ".agent-metrics" / "autonomy-audit.jsonl"
    for assertion in assertions:
        atype = assertion.get("type")
        if atype == "file_exists":
            fpath = project / assertion["path"]
            if not fpath.exists():
                errors.append(f"Expected file not created: {assertion['path']}")
        elif atype == "file_contains":
            fpath = project / assertion["path"]
            if fpath.exists():
                content = fpath.read_text()
                if assertion.get("text") and assertion["text"] not in content:
                    errors.append(f"File {assertion['path']} doesn't contain '{assertion['text']}'")
            else:
                errors.append(f"File not found: {assertion['path']}")
        elif atype == "audit_entry":
            if audit_log.exists():
                entries = audit_log.read_text()
                project_name = env.get("V11_SESSION_PROJECT", "bench")
                if project_name not in entries:
                    errors.append("No audit entries for project")
            else:
                errors.append("No audit log created")
        elif atype == "exit_code":
            if result.returncode != assertion.get("code", 0):
                errors.append(f"Exit code: {result.returncode}, expected {assertion.get('code', 0)}")

    return {"passed": len(errors) == 0, "errors": errors, "cost_usd": cost_usd}


# Executor dispatch
EXECUTORS = {
    "hook-chain": _exec_hook_chain,
    "task-lifecycle": _exec_task_lifecycle,
    "schema-validation": _exec_schema_validation,
    "latency-sla": _exec_latency_sla,
    "ownership": _exec_ownership_check,
    "live-cli": _exec_live_cli,
}


# ── Existing suite integration ─────────────────────────────────────────────────

def _run_existing_pytest(timeout: int = 600) -> dict:
    """Run existing pytest suite and extract pass/fail counts.

    Recursion guard: if already inside pytest (PYTEST_CURRENT_TEST set),
    return a stub result without re-entering pytest. Otherwise three copies
    of TestTier0Integration × full suite would stack exponentially.
    """
    import os as _os
    if _os.environ.get("PYTEST_CURRENT_TEST"):
        # We're inside a pytest invocation; don't recurse.
        return {"passed": 0, "total": 0, "score": 0, "skipped": "pytest-recursion-guard"}
    try:
        # Pass PYTEST_CURRENT_TEST=inner to the child so any nested call short-circuits.
        child_env = dict(_os.environ)
        child_env["PYTEST_CURRENT_TEST"] = "benchmark-runner-child"
        result = subprocess.run(
            ["python3", "-m", "pytest", str(V11_ROOT / "tests"), "--tb=no",
             "--ignore=" + str(V11_ROOT / "tests" / "test_benchmark.py"),
             "-m", "not slow", "-p", "no:benchmark", "-p", "no:xdist"],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(V11_ROOT), env=child_env,
        )
        # Parse "X passed, Y failed" from last lines
        output = result.stdout + result.stderr
        passed = failed = 0
        for line in output.split("\n"):
            if "passed" in line:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == "passed" or p == "passed,":
                        try:
                            passed = int(parts[i - 1])
                        except (ValueError, IndexError):
                            pass
                    if p == "failed" or p == "failed,":
                        try:
                            failed = int(parts[i - 1])
                        except (ValueError, IndexError):
                            pass
        total = passed + failed
        return {"passed": passed, "total": total, "score": (passed / total * 100) if total > 0 else 0}
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {"passed": 0, "total": 0, "score": 0}


def _run_existing_fqb(timeout: int = 120) -> dict:
    """Run Formation Quality Benchmark and extract score."""
    fqb_path = V11_ROOT / "scripts" / "formation-quality-benchmark"
    if not fqb_path.exists():
        return {"passed": 0, "total": 20, "score": 0}
    try:
        result = subprocess.run(
            ["python3", str(fqb_path), "--json"],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(V11_ROOT),
        )
        data = json.loads(result.stdout)
        return {
            "passed": data.get("passed", 0),
            "total": data.get("total", 20),
            "score": data.get("score", 0),
        }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return {"passed": 0, "total": 20, "score": 0}


# ── Main run function ─────────────────────────────────────────────────────────

def run_benchmark(
    tier: int = 0,
    baseline: dict | None = None,
    previous: dict | None = None,
    ledger_path: Path | None = None,
    verbose: bool = False,
) -> dict:
    """
    Run the V11 benchmark at the specified tier.

    Returns a full result dict matching the ledger schema.
    """
    start_time = time.monotonic()
    now = datetime.now(timezone.utc)
    run_id = f"v11-bench-{now.strftime('%Y%m%d-%H%M%S')}"

    # Git SHA
    try:
        git_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=str(V11_ROOT),
        ).stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        git_sha = "unknown"

    all_tests: list[dict] = []
    total_cost = 0.0
    latency_p50: dict[str, float] = {}

    # ── Load and run YAML tasks ────────────────────────────────────────────
    tasks = load_tasks(tier)
    for task in tasks:
        task_id = task.get("id", "?")
        task_type = task.get("type", "hook-chain")
        category = task.get("category", task_type)

        executor = EXECUTORS.get(task_type)
        if not executor:
            all_tests.append({
                "id": task_id, "category": category, "passed": False,
                "error": f"Unknown task type: {task_type}", "duration_ms": 0, "cost_usd": 0,
            })
            continue

        # Create a fresh project for each task
        with tempfile.TemporaryDirectory() as tmp:
            project, workspace_root, env = scaffold_v11_project(Path(tmp), project_name="bench")
            task_start = time.monotonic()
            try:
                result = executor(task, project, env)
            except Exception as e:
                result = {"passed": False, "errors": [str(e)]}
            task_duration = (time.monotonic() - task_start) * 1000

        passed = result.get("passed", False)
        cost = result.get("cost_usd", 0)
        total_cost += cost
        error_msg = "; ".join(result.get("errors", []))[:200] if not passed else ""

        # Collect latencies if present
        if "latencies" in result:
            latency_p50.update(result["latencies"])

        all_tests.append({
            "id": task_id,
            "category": category,
            "passed": passed,
            "duration_ms": round(task_duration, 1),
            "cost_usd": cost,
            "error": error_msg,
        })

    # ── Run existing suites as sub-scores (Tier 0 only) ────────────────────
    if tier >= 0:
        # Pytest suite
        pytest_result = _run_existing_pytest()
        all_tests.append({
            "id": "SUITE-pytest",
            "category": "existing-pytest",
            "passed": pytest_result["score"] >= 95,  # 95%+ = pass
            "duration_ms": 0,
            "cost_usd": 0,
            "detail": f"{pytest_result['passed']}/{pytest_result['total']}",
        })

        # FQB suite
        fqb_result = _run_existing_fqb()
        all_tests.append({
            "id": "SUITE-fqb",
            "category": "existing-fqb",
            "passed": fqb_result["score"] >= 95,
            "duration_ms": 0,
            "cost_usd": 0,
            "detail": f"{fqb_result['passed']}/{fqb_result['total']}",
        })

    # ── Compute scores ─────────────────────────────────────────────────────
    tier_passed = sum(1 for t in all_tests if t.get("passed"))
    tier_total = len(all_tests)
    tier_score = TierScore(tier=tier, passed=tier_passed, total=tier_total, tests=all_tests)

    fallback_scores = get_last_tier_scores(ledger_path)
    tier_scores_dict = {tier: tier_score}
    composite = compute_composite(tier_scores_dict, fallback_scores)

    category_scores = compute_category_scores(all_tests)

    # ── Build tier_scores for output ───────────────────────────────────────
    tier_scores_output: dict[str, float | None] = {}
    for t in [0, 1, 2]:
        if t == tier:
            tier_scores_output[f"tier{t}"] = round(tier_score.score, 1)
        else:
            tier_scores_output[f"tier{t}"] = fallback_scores.get(t)

    # ── Regression detection ───────────────────────────────────────────────
    result_dict: dict[str, Any] = {
        "run_id": run_id,
        "timestamp": now.isoformat(),
        "v11_version": "11.6.0",
        "git_sha": git_sha,
        "tier": tier,
        "duration_s": round(time.monotonic() - start_time, 1),
        "total_cost_usd": round(total_cost, 4),
        "composite_score": composite,
        "tier_scores": tier_scores_output,
        "category_scores": {name: cs.to_dict() for name, cs in category_scores.items()},
        "tests": all_tests,
        "latency_p50": latency_p50,
        "regressions": [],
    }

    regressions = detect_regressions(result_dict, baseline, previous)
    result_dict["regressions"] = [
        {"rule": r.rule, "severity": r.severity, "message": r.message, "detail": r.detail}
        for r in regressions
    ]

    # ── Persist to ledger ──────────────────────────────────────────────────
    append_result(result_dict, ledger_path)

    return result_dict
