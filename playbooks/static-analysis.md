# Playbook: Static-Analysis Superpowers (`sg` / ast-grep) — EO-S7

> Closes the gap in spec §4.2 (`docs/eigen-opus/11-sa-superpowers-spec.md`, herakles-linux-opus, APPROVED 2026-07-15): a "locate every X" question defaults to a Haiku Explore swarm — 25-100k tokens, minutes, approximate recall — when the question is actually structural (an exact AST shape: a call, an `except` clause, an argument pattern). `sg` (ast-grep) answers those in milliseconds for ~0 tokens with exact recall. This playbook is the deterministic half of the S7 trio (`scc` census, `jscpd` clones, `ast-grep` structural search); the other two have their own extractors and aren't in scope here.
>
> Tool: **`sg`** = `@ast-grep/cli` 0.44.1 (`~/.local/bin/sg`, install pinned + checksummed per spec §1/T10). **Install the scoped npm name only** — bare `ast-grep` on npm is a live typosquat (a different, unrelated 0.1.0 package by another author; `@ast-grep/cli` is the real tool, 175 published versions). `npm view ast-grep` vs `npm view @ast-grep/cli` makes the gap obvious if you need to re-verify.

## Load trigger

Phase 2 PLAN (before `TaskCreate`, orchestrator calls `code_census` on the target — separate playbook) and Phase 3 EXPLORE — specifically the moment a question is about to become a multi-file Haiku swarm spawn. Also Phase 4r/adversarial review (spec §4.3): the reviewer prompt runs the project's rule pack and folds hits into findings.

---

## 1. `sg` vs. a Haiku Explore swarm

| Question shape | Route | Cost |
|---|---|---|
| "Every place that does `<exact structural pattern>`" — a specific call shape, an `except` clause, an argument with a literal default, etc. | `sg` | milliseconds, ~0 tokens, exact recall |
| "Why does X work this way", "what does this subsystem do", fuzzy/semantic/cross-cutting questions, or the shape can't be written as an AST pattern | Haiku Explore swarm | tokens + minutes, approximate |

The rule of thumb from spec §4.2: *if the question is structural ("where is every X"), run `ast_search`/`sg` first.* Pinpoint-report JSON schema is unchanged either way — `sg` output is mechanically reshaped into the same shape a swarm would return, so downstream spawn contracts don't change; only the method that fills them in does.

**Success criterion (spec §7, measured via dispatch traces over 2 sprints):** ≥50% of "locate every X" Explore spawns replaced by `sg`/`ast_search`. If you're about to spawn an Explore agent to "find every place that calls `.exists()` on a marker path" or similar, check §3 below for an existing rule first — writing a 5-line pattern is usually faster than the spawn.

---

## 2. Running a rule

Two entry points, both `--json`:

```bash
# Named rule file (the allowlisted, curated form — see §3/§5)
sg scan -r /path/to/v11/rules/ast-grep/<rule>.yml <path> --json

# Inline pattern (ad hoc, not persisted, not allowlisted)
sg run -p '<pattern>' -l python --json <path>
```

Real invocation, run against this rule pack's own fixture:

```bash
$ cd /path/to/v11/rules/ast-grep
$ sg scan -r marker-exists-not-isfile.yml fixtures/marker-exists-not-isfile/ --json
```

Trimmed output (2 hits, one per `.exists()` call in `fixtures/marker-exists-not-isfile/bad.py`):

```json
[
  {
    "text": "candidate.exists()",
    "range": { "start": { "line": 7, "column": 11 }, "end": { "line": 7, "column": 29 } },
    "file": "fixtures/marker-exists-not-isfile/bad.py",
    "lines": "        if candidate.exists():",
    "language": "Python",
    "metaVariables": { "single": { "PATH": { "text": "candidate" } } },
    "ruleId": "marker-exists-not-isfile",
    "severity": "warning",
    "message": ".exists() is True for directories too. If this is checking for a marker/ sentinel FILE ..., use .is_file() instead ...",
    "note": "Historical bug (EO #28, herakles-linux-opus commit 857dc94, 2026-07-15): ..."
  },
  { "...": "second hit at line 14 (telemetry_file.exists()), same shape" }
]
```

Every hit carries the rule's `message` and `note` inline — that's why the note text (§3) matters: it's what a reviewer or agent actually reads at the point of the finding, not just documentation. An empty `[]` (run it against `fixtures/marker-exists-not-isfile/good.py`) means no hits — that's the expected result on the post-fix shape.

---

## 3. The 4 seed rules

All 4 live in `/path/to/v11/rules/ast-grep/*.yml` with fixtures at `fixtures/<rule-id>/{bad,good}.py`. Each `note:` field is the authoritative wording — this table summarizes it.

| Rule id | Catches | Historical bug / commit | Breadth | Limits |
|---|---|---|---|---|
| `marker-exists-not-isfile` | `$PATH.exists()` — true for directories too, wrong for a marker/sentinel-FILE check | EO #28, herakles-linux-opus `857dc94` (2026-07-15): a directory literally named `CLAUDE.md` satisfied `.exists()` and corrupted Project Atlas discovery | **Broad, by design** — fires on every `.exists()` call, not just marker-shaped ones | `.exists()` is a legitimate "does this path exist at all" check in many places; every hit needs human/reviewer triage, not auto-fix or auto-block |
| `fallback-secret` | `os.getenv($KEY, $DEFAULT)` / `os.environ.get($KEY, $DEFAULT)` where `$KEY` looks secret-shaped (`constraints:` regex on `SECRET\|PASSWORD\|TOKEN\|API_KEY\|...`) and `$DEFAULT` isn't an empty/`None` placeholder | task #16 / platform-hardening C2-R2 (2026-07-14): a name-only pre-commit scan was falsely closed by this exact evasion — a literal default instead of a bare assignment; truth set = `~/scripts/.githooks/pre-commit` R3/R4 (17/22 cases in `test-pre-commit`) | Gated on key-name shape to keep false positives low (`getenv("LOG_LEVEL", "info")` does not fire) | Can't tell a real secret literal from a placeholder/test fixture (advisory/human judgment, same as the value-scan hook it complements). **Python-only**: ast-grep 0.44.1's bash grammar can't parse `${VAR:-literal}` ("Pattern contains an ERROR node") — the shell form still needs the pre-commit value-scan |
| `harvest-survivor-purge` | `$PURGE_FN([$ITEM[$KEY] for $ITEM in $SRC])` — a purge/delete call fed from a post-harvest *survivor* set instead of the raw discovery set | blocker #15, herakles-linux-opus `93e7397` (2026-07-15, CRITICAL from adversarial review of `bef9108`): `_run_purge([r["project_id"] for r in records])` where `records` was harvest survivors — a harvest failure silently dropped a valid project from the purge-safe set, causing a false `DELETE` with FK cascade | **Narrow, by design** — matches only the literal historical listcomp-over-records-like-name shape | The real bug class is a data-flow property (was `$SRC` itself derived from a prior filter of the true discovery set?) that ast-grep can't trace structurally; a purge over a plain identifier (`_run_purge(discovered_ids)`) won't match by design (that's the fixed shape), and other derived-subset bugs using a different shape won't either |
| `swallowed-oserror` | `except OSError: pass`, `except (OSError, IOError): pass`, or bare `except: pass` around filesystem ops | Generalized from `docs/eigen-opus/11-sa-superpowers-spec.md` §4.3 (today's MEDIUM finding); mirrors the fix direction of blocker #15 (`93e7397`) — the corrected `_is_project_root` distinguishes benign-absence errnos from `PermissionError`/other `OSError` and logs a warning instead of blanket-swallowing | Flags the `pass`-only shape specifically | `except OSError as exc: logger.warning(...)` does not match — that's the fix shape, not the bug |

---

## 4. Adding a rule

**File naming:** `/path/to/v11/rules/ast-grep/<rule-id>.yml`, `<rule-id>` kebab-case, matching the `id:` key inside.

**Required keys:**

```yaml
id: <rule-id>            # matches the filename
language: python
rule:                    # a pattern, or `any:`/`all:` of patterns, + optional `constraints:`
  pattern: ...
message: >-              # what the finder should DO about a hit — shown inline on every match
  ...
severity: warning         # advisory-first (spec §1 hard guardrail) — no CI-blocking gates yet
note: >-                  # the historical/authoritative record: bug, commit, breadth decision, known limits
  ...
```

**Fixtures:** `fixtures/<rule-id>/bad.py` (triggers the rule — the pre-fix shape) and `fixtures/<rule-id>/good.py` (the fixed shape — must NOT trigger).

**Verify command:**

```bash
cd /path/to/v11/rules/ast-grep
sg scan -r <rule-id>.yml fixtures/<rule-id>/bad.py --json | python3 -c "import json,sys; print(len(json.load(sys.stdin)), 'hits')"
sg scan -r <rule-id>.yml fixtures/<rule-id>/good.py --json | python3 -c "import json,sys; print(len(json.load(sys.stdin)), 'hits')"
```
`bad.py` must report ≥1 hit, `good.py` must report `0 hits`. (Confirmed for all 4 seed rules: `fallback-secret` 2/0, `harvest-survivor-purge` 1/0, `swallowed-oserror` 3/0, `marker-exists-not-isfile` 2/0.)

**The regression-proof gate (spec §7, success criterion 2):** a rule ships only when it catches its original bug **on the pre-fix commit**. Where the historical bug has a real fix commit in this repo, pull the exact pre-fix source as the `bad.py` fixture:

```bash
git -C /path/to/operator-home/herakles-linux-opus show <fix-commit>^:<path> > fixtures/<rule-id>/bad.py
```

Verified for the two seed rules with an in-repo fix commit:
```bash
$ git -C /path/to/operator-home/herakles-linux-opus show 857dc94^:src/domains/atlas/ingest.py | grep -n '\.exists()'
180:                if candidate.exists():
...                                                    # marker-exists-not-isfile's bad.py shape, confirmed
$ git -C /path/to/operator-home/herakles-linux-opus show 93e7397^:src/cli.py | grep -n '_run_purge\|records\['
199:        purged = _run_purge([r["project_id"] for r in records])
...                                                    # harvest-survivor-purge's bad.py shape, confirmed
```

`fallback-secret` (external truth set: `~/scripts/.githooks/test-pre-commit`, not a single herakles-linux-opus commit) and `swallowed-oserror` (generalized from a spec finding, not a shipped-then-fixed commit) don't have a single `git show <fix>^` source — their `bad.py` fixtures instead hand-encode the documented bug shape from the cited source. Either way, the gate is the same: run `sg scan` against the fixture and confirm it reproduces the finding before the rule is considered shipped.

---

## 5. Allowlist contract for Opus

**Status as of 2026-09-18: live on `main`** — `src/domains/atlas/ast_search.py` (task #23), MCP registration (`ast_search`, task #25), the REST routes (task #26), and the CLI sweep `opus atlas extract-pattern-flags` (task #27) all shipped and are reachable at `:9001`. Gate PASSED: `tests/test_atlas_ast_search.py` (15 tests, S7-W3 acceptance), seed rules verified on pre-fix source `857dc94^` and `93e7397^`. The endpoints below are exactly what's live — this section is no longer forward-looking.

The contract itself (fixed points, from the task descriptions):

- **Allowlist = files present in `RULES_DIR`** (`/path/to/v11/rules/ast-grep`, overridable via `OPUS_ASTGREP_RULES_DIR`). `list_rules()` enumerates `*.yml` basenames in that directory — that list **is** the allowlist.
- **Callers pass a rule id, never a path or YAML body.** `run_ast_search(*, rule, pattern, scope, lang="python", cap=200)` requires exactly one of `rule`/`pattern`; an unknown `rule` raises `ValueError("rule not allowlisted")`, which the router maps to `400` with `{"error": ..., "allowed_rules": list_rules()}`.
- **Inline `pattern` is allowed and bounded** — it bypasses the allowlist (it's not a stored rule) but is still scoped and capped: `scope` must resolve to a known Atlas `project_id` (or `None` = every ingested project root; never an arbitrary filesystem path), results are capped (`cap`, default 200) with a `truncated` flag, and the underlying `subprocess.run` is invoked with an argv list (`shell=False`) under a 60s timeout — never interpolated into a shell string.
- **Surfaces:**
  - MCP tool `ast_search` (alongside `find_clones`, MCP tool count 20→22, task #25).
  - `POST /api/atlas/ast-search` — body `{rule?, pattern?, scope?, lang?, cap?}` (task #26).
  - `GET /api/atlas/ast-search/rules` — returns `list_rules()` so clients can discover the allowlist without guessing (task #26).
  - `opus atlas extract-pattern-flags [--force] [--project NAME]` — **HOST-ONLY**, and also requires `OPUS_DATABASE_URL` exported (container has no project mounts, same discipline as `extract-facts`/`extract-census`; see `reference_atlas_extract_facts_host_only` — in-container `--force` has silently wiped rows before). Sweeps every allowlisted rule over every ingested project and writes `atlas_facts.pattern_flags` + `pattern_flags_generated_at` (task #27, mirrors `extract-census`'s CLI shape and per-project commit/rollback discipline).

#23/#25/#26/#27 have landed; the verify-on-host command from task #27 is the smoke test:
```bash
opus atlas extract-pattern-flags --project-name herakles-linux-opus
# then: psql ... SELECT pattern_flags_generated_at FROM atlas_facts WHERE project_id='herakles-linux-opus';
```
