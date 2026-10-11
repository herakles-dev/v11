#!/usr/bin/env python3
"""S2-T0b-1 (#113): one resolver for "which task does (session, task id) name".

A task id is local to one Claude Code TaskList. A resumed conversation keeps
its hook session id but can get a new TaskList whose ids start again at 1, so
one (session_uuid, task_id) pair names several tasks over time. Session
a059e6ae of v11-leverage-program holds four TaskLists, and ids 1-7 name four
tasks each. Every reader that turns a bare id into a task identity
(subject_norm, create_seq) calls TaskIndex.resolve, so all of them apply the
same rules. Design: sessions/v11-leverage-program/artifacts/
s2-t0-epoch-design.md §3-§4, amended by review #19 (§11: C4, C5, C11-C14).

TaskList epochs
    hooks/sync-tasks opens an epoch at the first TaskCreate of a session
    (`fresh`) and whenever a TaskCreate shows the TaskList changed (`reuse`).
    It stamps `tl_epoch` (an int, never compared, only matched) on every event
    it appends, and `tl_open` on the create that opened the epoch. The current
    epoch is kept in $METRICS_DIR/tasklist-epochs/<session_uuid>, an
    append-only file (review #19 C3) whose LAST complete line is read (the
    writer is hooks/lib/common.sh v11_tl_epoch_on_create, S2-T0b-2):
        v1 <tl_epoch> <fresh|reuse|seed> <pid:starttime|-> <last_create_tool_use_id|->
           <,id:tu8,id:tu8,...,> <max_id|->
    tl_epoch 0 (`seed`) is a session seeded at rollout whose events are not
    stamped yet: no current epoch. A torn or garbled last line reads as none.
    Unstamped history (every ledger before S2) gets epochs derived with the
    id-reuse rule. Derived epochs are for display and the store finder only;
    unstamped rows resolve by inference (R2). An epoch's ordinal is the order
    of its first event. A hook session's TaskList spans projects, so epochs()
    reads the session's rows from every ledger in $METRICS_DIR/ledger (C13);
    claims, and so resolve(), stay per project. v11_replay_ledger's fold
    learns an epoch's open reason from this project's ledger only (it stays
    one incremental read): for an epoch opened `fresh` by a create in another
    project, a stamped subject_norm-less row that R1 binds here by
    inference_cross_epoch stays unresolved in the replay (fails safe).

Claims (what can bind an id)
    - counted: `created` events with a valid identity (non-empty
      subject_norm, int create_seq >= 0);
    - legacy only: identity-bearing status events for a (session, id) that
      has no `created` at all (tasks older than the ledger);
    - excluded: ev review/prescope, identity_unresolved, review rows voided
      per review_corrections.py. pair_* ids never mix with numeric ids:
      claims are keyed by the exact id, and epochs use numeric ids only.
    - aliases: identities go through v11_replay_ledger's rehydrate alias rule.
      The aliases are read from the replay's identity view
      (created_claims[].identity; the view also lists them as `aliases`),
      never re-derived here, so V11_REPLAY_REHYDRATE_ALIAS=off turns them off
      here too.
    - norms(I): I's own norm, its aliases' norms, and normalize_subject() of
      the subject of every `created` and renaming field_update folded into I.
      The replay's sibling-follows-parent link uses the same set (key_norms).
    Position = (UTC instant of ts, seqno), v11_replay_ledger's order.
    A row's own position bounds what can bind it: a ledger row passes
    at=(ts, seqno) and binds claims at or before that position; any other row
    (queue, trace) passes at=(ts, None) and binds claims at or before ts, or,
    only when there is none, up to ts + 2 s (C12). With `subject`, a claim
    within those 2 s whose norms contain it beats claims at or before ts
    that do not: a queue or trace row is written after its task's create, so
    an earlier ts is clock skew. Without `subject`, or when neither matches,
    strict position wins.

Rules (in this order; ambiguous only on a real tie)
    R0  An explicit identity binds (basis "explicit") when the ledger knows it,
        else unresolved.
    R1  Session and epoch: C = the claims made in that epoch, at or before the
        row when `at` is given (C11).
          |C| = 1                         -> bound ("epoch")
          |C| = 0, but the epoch claims the id after the row
                                          -> R2 over every epoch
                                             ("inference_before_epoch_claim"):
                                             the row predates this epoch's
                                             create, so it names an older task
          |C| = 0, epoch opened fresh     -> R2 restricted to positions before
                                             the epoch ("inference_cross_epoch")
          |C| = 0, opened reuse/unknown   -> unresolved: the create was never
                                             ledgered, and it must not bind
                                             into an older epoch
          |C| > 1                         -> ambiguous (a reuse the writer missed)
    R2  Session, no epoch (legacy and unstamped rows): the latest claim at or
        before `at` ("inference"). With `subject`, the latest claim whose norms
        contain it wins over later ones. Several identities at that one
        position -> ambiguous; no claim -> unresolved. at=None -> the latest
        claim overall ("latest").
    R3  No session: R2 in every session that claimed the id. One distinct
        identity binds ("only"); with `subject`, one whose norms contain it
        binds; more -> ambiguous (the caller may break the tie). C12 holds
        across sessions: the 2 s slack only when no session has a claim at
        or before ts, or (with `subject`) none that matches while one within
        the slack does.
    R4  Session, no `at`, no epoch (current-state queries): R1 on
        current_epoch(session) ("current_epoch"); with no epoch anywhere, the
        latest claim ("latest").
    A session that is not a UUID counts as no session (R3), with a note. So
    does, when no epoch is given, a session that never claimed the id. This is
    v11_ledger_resolve_by_task_id's contract (review #61).

Terminal (C5)
    An identity is terminal when its last STATUS event (created, in_progress,
    blocked, completed, cancelled) is completed or cancelled; review,
    prescope and field_update rows never count. last_status(rows, identity)
    is the reference the #111 write-side jq mirrors (parity test in T0b-2).

API
    claim_key(ev) -> (session_uuid, tl_epoch | None, task_id)
        The keying rule v11_replay_ledger shares (both import it from
        scripts/lib/task_key.py, which imports nothing).
    tl_epoch_of(ev) -> int | None
        An int, an integral float or a digit string, normalised to int (C4).
    TaskIndex.from_ledger(project, *, metrics_dir=None, events=None,
                          identities=None, cross_project=True)
        events: ledger rows (dicts) instead of $METRICS_DIR/ledger/<project>.jsonl.
        identities: the replay's identity view if the caller already has it;
        otherwise v11_replay_ledger runs (V11_REPLAY_EMIT_IDENTITIES=on).
        If it cannot run, there are no aliases and .warnings says so.
        cross_project=False limits epochs() to this project's ledger.
    TaskIndex.resolve(session, task_id, *, epoch=None, at=None, subject=None,
                      identity=None) -> Resolution
        at: (datetime or ISO string, seqno | float("inf") | None), or a bare
        timestamp (read as (ts, None)).
    TaskIndex.epochs(session) -> [Epoch]   stamped and derived, by ordinal
    TaskIndex.current_epoch(session, task_id=None) -> int | None
        The record's value, else the newest stamped epoch in any ledger. With
        a task_id, epoch_for_task(rec, task_id): a task carried into the
        record's epoch keeps the epoch it was created in (review #26).
    TaskIndex.last_status(identity) -> str | None   (alias-folded, position order)
    TaskIndex.claims(session, task_id) -> [Claim]    (position order)
    TaskIndex.claim_items() -> [((session, task_id), [Claim])]   every claimed pair
    TaskIndex.find_task_store(session, epoch=None, *, ordinal=None,
                              tasks_root=None, teams_root=None,
                              config_dir=None) -> StoreMatch
        The ~/.claude/tasks/<dir> holding the epoch's tasks (C14):
        1. a team config ~/.claude/teams/<dir>/config.json whose
           leadSessionId is the session, or whose createdAt is within 60 s of
           the startedAt of a ~/.claude/sessions/<pid>.json naming the
           session, created no later than the epoch's first create (+60 s):
           the latest such team's store, verified (basis
           "teams_config:lead_session" or "teams_config:process"), unless its
           store holds none of the epoch's tasks while another store does;
        2. otherwise a content match of the epoch's created (id, subject)
           against <dir>/<id>.json, with .highwatermark == the epoch's max id
           breaking a tie: unverified (basis "content_match:<hits>/<ids>" or
           "content_match+highwatermark:..."). No match or an unbroken tie ->
           None.
    TaskIndex.norms(identity) -> frozenset[str]
    read_epoch_record(session, metrics_dir=None) -> EpochRecord | None
    record_epoch(session, metrics_dir=None) -> int | None
        The last record line's tl_epoch, 0 for a seed line (read_epoch_record
        returns None for one).
    parse_identity_arg("subject_norm:create_seq") -> (str, int)
        Splits on the LAST ':'.
    last_status(rows, identity) -> str | None    (rows in the order given)
    Resolution(identity, status, basis, candidates, note, claim)
        status: "bound" | "unresolved" | "ambiguous".
        identity: (subject_norm, create_seq) after aliasing, or None.
        candidates: the tied identities, or [identity] when bound.
        claim: the Claim that bound it (session_uuid, task_id, tl_epoch,
        seqno, ts, ev), or None.
    Resolution, Epoch, EpochRecord, StoreMatch and Claim are namedtuples, not
    dataclasses. v11_replay_ledger imports claim_key from task_key.py, not
    from this module, so the aggregate rebuild path does not load it.

CLI (the TSV contract of v11_ledger_resolve_by_task_id, no trailing newline)
    task_epoch.py resolve PROJECT TASK_ID [--session S] [--epoch E] [--at TS]
                  [--seqno N] [--subject T] [--identity SN:CS] [--format tsv|json]
        "SN<TAB>CS" [+ "\\nNOTE<TAB>text"] | "MISS" | "AMBIGUOUS<TAB>detail"
        The ambiguous detail keeps the phrases scripts/review-daemon matches:
        " names more than one task " (no session) and " tasks under task_id "
        (one session). --seqno without --at takes the ts of the one ledger row
        carrying that seqno. Always exits 0 on a resolution (MISS on an
        internal error); 2 on a usage error.
    task_epoch.py epochs PROJECT --session S [--format tsv|json]
        TSV: ordinal, tl_epoch|-, first_seqno|-, open_reason, max_id|-,
        stamped|derived, n_created, first_ts|-, first_project|-
    task_epoch.py store PROJECT --session S [--epoch E | --ordinal N]
                  [--tasks-root DIR] [--teams-root DIR] [--config-dir DIR]
                  [--format tsv|json]
        TSV: "<store dir name>|NONE<TAB><basis><TAB>verified|unverified"
    All take --metrics-dir DIR (default $METRICS_DIR, else ~/.agent-metrics).
    The config dir defaults to $CLAUDE_CONFIG_DIR, else ~/.claude; the tasks
    root to $V11_TASKS_ROOT, else <config dir>/tasks; the teams root to
    $V11_TEAMS_ROOT, else <config dir>/teams. Process files are read from
    <config dir>/sessions.
"""

import datetime
import json
import os
import re
import sys
from collections import namedtuple

from normalize_subject import normalize_subject
from review_corrections import correction_outcomes
from task_key import claim_key, tl_epoch_of  # noqa: F401 (re-exported API)

BOUND, UNRESOLVED, AMBIGUOUS = "bound", "unresolved", "ambiguous"
OPEN_REASONS = ("fresh", "reuse")
STATUS_EVENTS = ("created", "in_progress", "blocked", "completed", "cancelled")
TERMINAL_STATUSES = ("completed", "cancelled")

Resolution = namedtuple("Resolution", "identity status basis candidates note claim",
                        defaults=("", None))
Epoch = namedtuple("Epoch", "ordinal tl_epoch first_seqno open_reason max_id stamped "
                            "first_ts n_created start first_project")
EpochRecord = namedtuple("EpochRecord", "tl_epoch open_reason sitting last_create_tool_use_id ids "
                                        "carry_from carried", defaults=(None, ()))
StoreMatch = namedtuple("StoreMatch", "name basis path epoch scores verified")
Claim = namedtuple("Claim", "pos identity tl_epoch session_uuid task_id seqno ts ev")

_UTC = datetime.timezone.utc
_TS_MIN = datetime.datetime.min.replace(tzinfo=_UTC)
SLACK = datetime.timedelta(seconds=2)
TEAM_START_SLACK_S = 60
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_SESSION_FILE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_PROJECT_RE = re.compile(r"[a-zA-Z0-9._-]{1,64}")
_DIGITS_RE = re.compile(r"[0-9]{1,30}")
# The epoch record line; keep in step with _V11_TLR_LINE_ERE in hooks/lib/common.sh.
# Groups 7-9 (sittings, pending, carry; review #26) are absent on older lines.
_RECORD_RE = re.compile(r"v1 (0|[1-9][0-9]{0,15}) (fresh|reuse|seed) ([0-9]{1,10}:[0-9]{1,20}|-) "
                        r"([A-Za-z0-9_-]{1,128}|-) (,(?:[A-Za-z0-9_-]{1,32}:[A-Za-z0-9_-]{1,8},)*) "
                        r"([0-9]{1,12}|-)"
                        r"(?: (,(?:[0-9]{1,10}:[0-9]{1,20},){0,8}) (,(?:[A-Za-z0-9_-]{1,32},)*) "
                        r"(-|(?:0|[1-9][0-9]{0,15}):,(?:[A-Za-z0-9_-]{1,32},)*))?")
_EXCLUDED = ("review", "prescope")
V11_HOME = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Keying and parsing
# ---------------------------------------------------------------------------

def valid_identity(sn, cs):
    return (isinstance(sn, str) and bool(sn) and isinstance(cs, int)
            and not isinstance(cs, bool) and cs >= 0)


def event_identity(ev):
    sn, cs = ev.get("subject_norm"), ev.get("create_seq")
    return (sn, cs) if valid_identity(sn, cs) else None


def last_status(rows, identity):
    """The ev of the last status event (created, in_progress, blocked,
    completed, cancelled) carrying `identity` in `rows`, in the order given,
    or None. review, prescope and field_update rows never count (C5); nor do
    rows without an identity. Aliases are the caller's business."""
    found = None
    for ev in rows:
        if ev.get("ev") in STATUS_EVENTS and event_identity(ev) == tuple(identity):
            found = ev["ev"]
    return found


def parse_identity_arg(s):
    """"subject_norm:create_seq" -> (subject_norm, create_seq). A norm may
    itself hold ':', so the split is on the LAST one. ValueError when either
    side is empty or create_seq is not a non-negative integer."""
    if not isinstance(s, str) or ":" not in s:
        raise ValueError(f"identity must be SUBJECT_NORM:CREATE_SEQ, got {s!r}")
    sn, _, cs = s.rpartition(":")
    if not sn or not _DIGITS_RE.fullmatch(cs):
        raise ValueError(f"identity must be SUBJECT_NORM:CREATE_SEQ, got {s!r}")
    return (sn, int(cs))


def instant(ts):
    """ts (ISO string or datetime) as an aware UTC datetime, or None."""
    if isinstance(ts, datetime.datetime):
        d = ts
    else:
        if not ts:
            return None
        try:
            d = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    return d.replace(tzinfo=_UTC) if d.tzinfo is None else d.astimezone(_UTC)


def position(ev):
    try:
        seq = int(ev.get("seqno") or 0)
    except (TypeError, ValueError):
        seq = 0
    return (instant(ev.get("ts")) or _TS_MIN, seq)


def _at_bounds(at):
    """The inclusive upper positions a claim may sit at for row position
    `at`, in the order to try them (C12): a ledger row's own (ts, seqno); for
    any other row, ts itself and then ts + 2 s of slack. () for at=None."""
    if at is None:
        return ()
    ts, seq = (at[0], at[1] if len(at) > 1 else None) if isinstance(at, (tuple, list)) else (at, None)
    d = instant(ts)
    if d is None:
        raise ValueError(f"not an ISO-8601 timestamp: {ts!r}")
    if seq is None:
        return ((d, float("inf")), (d + SLACK, float("inf")))
    return ((d, seq),)


def _within(claims, bounds, lt=None, match=None):
    """The claims at or before the first bound that admits any (all claims
    for no bounds), strictly before `lt` when given, and whether that took
    the slack bound. With `match` (the row's subject is in a claim's norms)
    and a slack bound: when no claim at or before ts matches but some within
    the slack do, those matching claims instead (C12 refinement: a queue or
    trace row is written after its task's create, so an earlier ts is clock
    skew)."""
    if lt is not None:
        claims = [c for c in claims if c.pos < lt]
    if not bounds:
        return list(claims), False
    if match is not None and len(bounds) > 1 and not any(match(c) for c in claims if c.pos <= bounds[0]):
        skewed = [c for c in claims if bounds[0] < c.pos <= bounds[1] and match(c)]
        if skewed:
            return skewed, True
    for n, b in enumerate(bounds):
        got = [c for c in claims if c.pos <= b]
        if got:
            return got, n > 0
    return [], False


def default_metrics_dir():
    return os.environ.get("METRICS_DIR") or os.path.join(os.path.expanduser("~"), ".agent-metrics")


def default_config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def default_tasks_root(config_dir=None):
    if os.environ.get("V11_TASKS_ROOT"):
        return os.environ["V11_TASKS_ROOT"]
    return os.path.join(config_dir or default_config_dir(), "tasks")


def default_teams_root(config_dir=None):
    if os.environ.get("V11_TEAMS_ROOT"):
        return os.environ["V11_TEAMS_ROOT"]
    return os.path.join(config_dir or default_config_dir(), "teams")


def _record_line(session, metrics_dir=None):
    """The regex match of the last complete line of the session's epoch
    record, or None (no file, unreadable, garbled)."""
    if not isinstance(session, str) or not _SESSION_FILE_RE.fullmatch(session):
        return None
    path = os.path.join(metrics_dir or default_metrics_dir(), "tasklist-epochs", session)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    lines = text.split("\n")[:-1]          # the part after the last newline is torn
    return _RECORD_RE.fullmatch(lines[-1]) if lines else None


def record_epoch(session, metrics_dir=None):
    """The tl_epoch on the last complete line of the session's epoch record,
    0 for a `seed` line, or None when there is no readable line. It is the
    value hooks/lib/common.sh v11_tl_epoch_read leaves in _V11_TLR_EPOCH:
    scripts/handoff stamps it as handoff-tasks.json live_tl_epoch, and the
    self-nudge check (v11_handoff_self_sitting) compares the two, so an id
    reuse after a seeded session's handoff still counts as a new TaskList."""
    m = _record_line(session, metrics_dir)
    return int(m.group(1)) if m else None


def read_epoch_record(session, metrics_dir=None):
    """The last complete line of $METRICS_DIR/tasklist-epochs/<session> (the
    record is append-only, review #19 C3), or None when the file is absent or
    unreadable, that line is garbled, or it is a `seed` line (tl_epoch 0: the
    session's events are not stamped yet). A torn tail (no newline) is not a
    line. ids are the numeric ids of the epoch's creates."""
    m = _record_line(session, metrics_dir)
    if m is None or m.group(1) == "0":
        return None
    ids = tuple(int(x.partition(":")[0]) for x in m.group(5).split(",")
                if _DIGITS_RE.fullmatch(x.partition(":")[0]))
    carry_from, carried = None, ()
    if m.group(9) and m.group(9) != "-":
        frm, _, lst = m.group(9).partition(":")
        carry_from, carried = int(frm) or None, tuple(x for x in lst.split(",") if x)
    return EpochRecord(int(m.group(1)), m.group(2) if m.group(2) in OPEN_REASONS else "unknown",
                       "" if m.group(3) == "-" else m.group(3),
                       "" if m.group(4) == "-" else m.group(4), ids, carry_from, carried)


def epoch_for_task(rec, task_id):
    """The epoch a task of the record's session is stamped with: the record's
    tl_epoch, or for a task carried into it (review #26) the epoch that task
    was created in (None for a seed epoch: unstamped). None without a record.
    hooks/lib/common.sh v11_tl_epoch_read SESSION TASK_ID is the bash side."""
    if rec is None:
        return None
    if rec.carried and str(task_id) in rec.carried:
        return rec.carry_from
    return rec.tl_epoch


def _jsonl_rows(path, project, needle=None):
    """v1 rows of `project` in the file, in file order; with `needle`, only
    lines that contain it are parsed."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return []
    rows = []
    for line in text.split("\n"):
        if not line or (needle is not None and needle not in line):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict) and ev.get("project") == project and ev.get("v") == 1:
            rows.append(ev)
    return rows


def read_ledger(project, metrics_dir=None):
    """The project's v1 ledger rows in file order; malformed lines skipped."""
    return _jsonl_rows(os.path.join(metrics_dir or default_metrics_dir(), "ledger",
                                    f"{project}.jsonl"), project)


def replay_identities(project, *, metrics_dir=None, events=None, timeout=60):
    """v11_replay_ledger's identity view (V11_REPLAY_EMIT_IDENTITIES=on) for
    the project ledger, or for `events` when given; None when the replay
    cannot run. common.sh reads $HERCULES_ROOT/.agent-metrics, so any other
    metrics dir, and `events`, go through a temporary copy. The replay runs
    with V11_TASK_RESOLVER=shared whatever the caller's setting."""
    import subprocess
    import tempfile
    md = os.path.abspath(metrics_dir or default_metrics_dir())
    common_sh = os.path.join(V11_HOME, "hooks", "lib", "common.sh")
    if not os.path.isfile(common_sh):
        return None
    with tempfile.TemporaryDirectory(prefix="task-epoch-") as tmp:
        if events is None and os.path.basename(md) == ".agent-metrics":
            root = os.path.dirname(md)
        else:
            if events is None:
                events = read_ledger(project, md)
            root = tmp
            os.makedirs(os.path.join(tmp, ".agent-metrics", "ledger"))
            with open(os.path.join(tmp, ".agent-metrics", "ledger", f"{project}.jsonl"), "w",
                      encoding="utf-8") as fh:
                for ev in events:
                    fh.write(json.dumps(ev, separators=(",", ":")) + "\n")
        if not os.path.isfile(os.path.join(root, ".agent-metrics", "ledger", f"{project}.jsonl")):
            return []
        # Aliases are data here, not a reader path (review #20): the legacy
        # resolver's view has no created_claims[].identity, so it is forced off.
        env = dict(os.environ, HERCULES_ROOT=root, V11_HOME=V11_HOME, V11_REPLAY_EMIT_IDENTITIES="on",
                   V11_TASK_RESOLVER="shared")
        env.pop("METRICS_DIR", None)
        try:
            proc = subprocess.run(
                ["bash", "-c", 'source "$1" && v11_replay_ledger "$2"', "bash", common_sh, project],
                capture_output=True, text=True, timeout=timeout, env=env)
        except (OSError, subprocess.SubprocessError):
            return None
    if proc.returncode != 0:
        return None
    try:
        agg = json.loads(proc.stdout)
    except ValueError:
        return None
    ids = agg.get("identities") if isinstance(agg, dict) else None
    return [r for r in ids if isinstance(r, dict)] if isinstance(ids, list) else None


def _describe(found):
    """{identity: sessions} -> the v11_ledger_resolve_by_task_id wording."""
    return "; ".join(
        f"session {','.join(sorted(s[:8] for s in sessions if s)) or '?'}: "
        f"\"{sn[:60]}\" (create_seq {cs})"
        for (sn, cs), sessions in found.items())


def _distinct(claims):
    """{identity: [claims]} in the order each identity first appears."""
    out = {}
    for c in claims:
        out.setdefault(c.identity, []).append(c)
    return out


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            v = json.load(fh)
    except (OSError, ValueError):
        return None
    return v if isinstance(v, dict) else None


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


# ---------------------------------------------------------------------------
# The index
# ---------------------------------------------------------------------------

class TaskIndex:
    """Claims, epochs and norms of one project ledger. Build it with
    from_ledger(); it is read-only afterwards."""

    def __init__(self, project, rows, *, identities=None, metrics_dir=None, warnings=None,
                 cross_project=True):
        self.project = project
        self.metrics_dir = metrics_dir or default_metrics_dir()
        self.cross_project = cross_project
        self.warnings = list(warnings or [])
        self.alias_of = {}        # alias identity -> the identity it folds into
        self._alias_norms = {}    # target identity -> its aliases' norms
        self._subjects = {}       # identity -> raw subjects (created / field_update)
        self._status = {}         # identity -> its last status event (C5)
        self._norms = {}
        self._known = set()
        self._claims = {}         # (session, task_id) -> [Claim], position order
        self._by_task = {}        # task_id -> sessions that claimed it
        self._session_rows = {}   # session -> [(pos, project, ev)] feeding epochs()
        self._epochs = {}
        self._epoch_creates = {}  # (session, ordinal) -> [(project, created ev)]
        self._build(rows, identities or [])

    @classmethod
    def from_ledger(cls, project, *, metrics_dir=None, events=None, identities=None,
                    cross_project=True):
        if not isinstance(project, str) or not _PROJECT_RE.fullmatch(project):
            raise ValueError(f"invalid project name {project!r}")
        md = metrics_dir or default_metrics_dir()
        if events is None:
            rows = read_ledger(project, md)
        else:
            rows = [ev for ev in events if isinstance(ev, dict) and ev.get("project") == project]
        warnings = []
        if identities is None and rows:
            identities = replay_identities(project, metrics_dir=md,
                                           events=rows if events is not None else None)
            if identities is None:
                warnings.append("v11_replay_ledger's identity view is unavailable: "
                                "rehydrate aliases are not applied")
        return cls(project, rows, identities=identities, metrics_dir=md, warnings=warnings,
                   cross_project=cross_project)

    # -- construction -------------------------------------------------------

    def _build(self, rows, identities):
        for rec in identities:
            target = (rec.get("subject_norm"), rec.get("create_seq"))
            if not valid_identity(*target):
                continue
            for c in rec.get("created_claims") or []:
                ci = c.get("identity") if isinstance(c, dict) else None
                if not isinstance(ci, dict):
                    continue
                own = (ci.get("subject_norm"), ci.get("create_seq"))
                if valid_identity(*own) and own != target:
                    self.alias_of[own] = target
                    self._alias_norms.setdefault(target, set()).add(own[0])

        corrected = correction_outcomes(rows)
        created, status = {}, {}
        for pos, ev in sorted(((position(ev), ev) for ev in rows), key=lambda p: p[0]):
            et = ev.get("ev")
            sess, tle, tid = claim_key(ev)
            if sess and (tle is not None or (et == "created" and tid.isdigit())):
                self._session_rows.setdefault(sess, []).append((pos, self.project, ev))
            if et in _EXCLUDED or ev.get("identity_unresolved"):
                continue
            if (str(ev.get("outcome") or "").lower() == "void"
                    or corrected.get((ev.get("seqno"), ev.get("ts"))) == "void"):
                continue
            ident = event_identity(ev)
            if ident is None:
                continue
            ident = self.alias(ident)
            self._known.add(ident)
            if et in STATUS_EVENTS:
                self._status[ident] = et
            if et in ("created", "field_update") and isinstance(ev.get("subject"), str) and ev["subject"]:
                self._subjects.setdefault(ident, set()).add(ev["subject"])
            if not sess or tid == "":
                continue
            claim = Claim(pos, ident, tle, sess, tid, ev.get("seqno"), ev.get("ts"), et)
            (created if et == "created" else status).setdefault((sess, tid), []).append(claim)
        self._claims.update(created)
        for key, lst in status.items():
            self._claims.setdefault(key, lst)  # legacy only: no `created` for the pair
        for sess, tid in self._claims:
            self._by_task.setdefault(tid, set()).add(sess)

    def _foreign_rows(self, session):
        """(pos, project, ev) of the session's epoch rows in every other
        project's ledger (C13): a hook session's TaskList spans projects."""
        if not self.cross_project:
            return []
        ledger_dir = os.path.join(self.metrics_dir, "ledger")
        try:
            names = sorted(n for n in os.listdir(ledger_dir) if n.endswith(".jsonl"))
        except OSError:
            return []
        out = []
        for name in names:
            project = name[:-len(".jsonl")]
            if project == self.project or not _PROJECT_RE.fullmatch(project):
                continue
            for ev in _jsonl_rows(os.path.join(ledger_dir, name), project, needle=session):
                sess, tle, tid = claim_key(ev)
                if sess == session and (tle is not None or (ev.get("ev") == "created" and tid.isdigit())):
                    out.append((position(ev), project, ev))
        return out

    # -- identities ---------------------------------------------------------

    def alias(self, ident):
        return self.alias_of.get(ident, ident)

    def norms(self, ident):
        ident = self.alias(ident)
        if ident not in self._norms:
            n = {ident[0]} | self._alias_norms.get(ident, set())
            n |= {normalize_subject(s) for s in self._subjects.get(ident, ())}
            self._norms[ident] = frozenset(n)
        return self._norms[ident]

    def last_status(self, ident):
        """The identity's last status event in position order, aliases
        folded in (C5); None when the ledger never saw one."""
        return self._status.get(self.alias(tuple(ident)))

    def claims(self, session, task_id):
        return list(self._claims.get((str(session or ""), str(task_id)), ()))

    def claim_items(self):
        """[((session, task_id), [Claim])]: every claimed pair, each list in
        position order (copies)."""
        return [(key, list(cl)) for key, cl in self._claims.items()]

    # -- epochs -------------------------------------------------------------

    def epochs(self, session):
        """Every TaskList epoch of the session, by ordinal: stamped ones by
        tl_epoch, unstamped history derived by the id-reuse rule, from every
        ledger that carries the session (C13), plus the epoch record's epoch
        when no event carries it yet."""
        session = str(session or "")
        if session in self._epochs:
            return self._epochs[session]
        rows = sorted(self._session_rows.get(session, []) + self._foreign_rows(session),
                      key=lambda r: r[0])
        builds, stamped, cur = [], {}, None
        for pos, project, ev in rows:
            tle = tl_epoch_of(ev)
            tid = claim_key(ev)[2]
            numeric = ev.get("ev") == "created" and tid.isdigit()
            if tle is not None:
                cur = stamped.get(tle)
                if cur is None:
                    cur = {"stamped": True, "tl_epoch": tle, "reason": None, "start": pos,
                           "ev": ev, "project": project, "ids": set(), "creates": []}
                    stamped[tle] = cur
                    builds.append(cur)
                if ev.get("ev") == "created" and cur["reason"] is None and ev.get("tl_open") in OPEN_REASONS:
                    cur["reason"] = ev["tl_open"]
            elif numeric:
                if cur is None or cur["stamped"] or int(tid) in cur["ids"]:
                    reason = ("fresh" if cur is None
                              else "reuse" if int(tid) in cur["ids"] else "unknown")
                    cur = {"stamped": False, "tl_epoch": None, "reason": reason, "start": pos,
                           "ev": ev, "project": project, "ids": set(), "creates": []}
                    builds.append(cur)
            if ev.get("ev") == "created":
                cur["creates"].append((project, ev))
                if numeric:
                    cur["ids"].add(int(tid))
        rec = read_epoch_record(session, self.metrics_dir)
        if rec is not None:
            if rec.tl_epoch in stamped:
                if stamped[rec.tl_epoch]["reason"] is None:
                    stamped[rec.tl_epoch]["reason"] = rec.open_reason
            else:
                builds.append({"stamped": True, "tl_epoch": rec.tl_epoch, "reason": rec.open_reason,
                               "start": None, "ev": {}, "project": None, "ids": set(rec.ids),
                               "creates": []})
        builds.sort(key=lambda b: (b["start"] is None, b["start"] or (_TS_MIN, 0)))
        out = []
        for n, b in enumerate(builds, 1):
            out.append(Epoch(n, b["tl_epoch"], b["ev"].get("seqno"), b["reason"] or "unknown",
                             max(b["ids"]) if b["ids"] else None, b["stamped"], b["ev"].get("ts"),
                             len(b["creates"]), b["start"], b["project"]))
            self._epoch_creates[(session, n)] = b["creates"]
        self._epochs[session] = out
        return out

    def epoch(self, session, tl_epoch):
        return next((e for e in self.epochs(session) if e.tl_epoch == tl_epoch), None)

    def current_epoch(self, session, task_id=None):
        rec = read_epoch_record(str(session or ""), self.metrics_dir)
        if rec is not None:
            # a task carried into the current epoch keeps its own (review #26)
            return rec.tl_epoch if task_id is None else epoch_for_task(rec, task_id)
        stamped = [e for e in self.epochs(session) if e.stamped and e.start is not None]
        return stamped[-1].tl_epoch if stamped else None

    # -- resolution ---------------------------------------------------------

    def resolve(self, session, task_id, *, epoch=None, at=None, subject=None, identity=None):
        tid = "" if task_id is None else str(task_id)
        want = normalize_subject(subject) if subject else None
        if identity is not None:
            return self._r0(identity)
        sess = str(session) if session else ""
        if sess and not _UUID_RE.fullmatch(sess):
            return self._r3(tid, at, want, no_session=("not_uuid", sess))
        if sess and epoch is None and (sess, tid) not in self._claims:
            return self._r3(tid, at, want, no_session=("no_claim", sess))
        if not sess:
            return self._r3(tid, at, want)
        if epoch is not None:
            return self._r1(sess, tid, int(epoch), at, want, "epoch")
        if at is not None:
            return self._r2(sess, tid, "inference", bounds=_at_bounds(at), want=want)
        cur = self.current_epoch(sess, tid)
        if cur is None:
            return self._r2(sess, tid, "latest", want=want)
        return self._r1(sess, tid, cur, None, want, "current_epoch")

    def _r0(self, identity):
        ident = parse_identity_arg(identity) if isinstance(identity, str) else tuple(identity)
        if len(ident) != 2 or not valid_identity(*ident):
            return Resolution(None, UNRESOLVED, "explicit", [], f"not an identity: {identity!r}")
        target = self.alias(ident)
        if target not in self._known:
            return Resolution(None, UNRESOLVED, "explicit", [],
                              f"identity {ident[0]}:{ident[1]} is not in the {self.project} ledger")
        note = f"{ident[0]}:{ident[1]} is a rehydrate alias of this task" if target != ident else ""
        return Resolution(target, BOUND, "explicit", [target], note)

    def _matcher(self, want):
        return (lambda c: want in self.norms(c.identity)) if want else None

    def _r1(self, sess, tid, tle, at, want, basis):
        bounds = _at_bounds(at)
        in_epoch = [c for c in self._claims.get((sess, tid), ()) if c.tl_epoch == tle]
        mine, slack = _within(in_epoch, bounds, match=self._matcher(want))
        if in_epoch and not mine:
            # C11: this epoch creates the id only after the row, so the row
            # names an older task (a fresh epoch opened mid-store, or a return
            # to an older store): position decides, across epochs.
            res = self._r2(sess, tid, "inference_before_epoch_claim", bounds=bounds, want=want)
            if res.status == BOUND:
                res = res._replace(note=(res.note + "; " if res.note else "") + (
                    f"TaskList epoch {tle} creates task {tid} only after this row "
                    f"(seqno {in_epoch[0].seqno}); bound by position"))
            return res
        found = _distinct(mine)
        if len(found) == 1:
            note = "bound within the 2 s slack after the row" if slack else ""
            return Resolution(mine[-1].identity, BOUND, basis, [mine[-1].identity], note, mine[-1])
        if len(found) > 1:
            return Resolution(None, AMBIGUOUS, basis, list(found),
                              f"session {sess} holds {len(found)} tasks under task_id {tid} in one "
                              f"TaskList epoch ({tle}; a reuse the writer missed) — "
                              f"{_describe({i: {sess} for i in found})}")
        ep = self.epoch(sess, tle)
        reason = ep.open_reason if ep is not None else "unknown"
        if reason != "fresh":
            return Resolution(None, UNRESOLVED, basis, [],
                              f"task {tid} has no create in TaskList epoch {tle} (opened "
                              f"{reason}); it never binds into an older epoch")
        res = self._r2(sess, tid, "inference_cross_epoch", bounds=bounds, lt=ep.start, want=want)
        if res.status == BOUND and not res.note:
            res = res._replace(note=f"task {tid} was not created in fresh TaskList epoch {tle}; "
                                    f"bound to the latest claim before it (seqno {res.claim.seqno})")
        return res

    def _r2(self, sess, tid, basis, *, bounds=(), lt=None, want=None):
        eligible, slack = _within(self._claims.get((sess, tid), ()), bounds, lt,
                                  match=self._matcher(want))
        if not eligible:
            return Resolution(None, UNRESOLVED, basis, [],
                              f"session {sess} has no claim on task {tid} at that position")
        pool, note = eligible, ""
        if want:
            matching = [c for c in eligible if want in self.norms(c.identity)]
            if matching:
                pool = matching
            else:
                note = f"no claim on task {tid} matches the subject; bound to the latest"
        top = pool[-1]
        tied = _distinct(c for c in pool if c.pos == top.pos)
        if len(tied) > 1:
            return Resolution(None, AMBIGUOUS, basis, list(tied),
                              f"session {sess} holds {len(tied)} tasks under task_id {tid} at one "
                              f"ledger position (seqno {top.pos[1]}) — "
                              f"{_describe({i: {sess} for i in tied})}")
        if top.identity != eligible[-1].identity:
            note = (f"the subject names an earlier task (seqno {top.seqno}) than the latest "
                    f"claim (seqno {eligible[-1].seqno})")
        elif basis == "latest" and not note and len(_distinct(eligible)) > 1:
            note = (f"session {sess} created {len(_distinct(eligible))} tasks as task_id {tid}; "
                    f"bound to the latest (seqno {top.seqno})")
        if slack:
            note = (note + "; " if note else "") + "bound within the 2 s slack after the row"
        return Resolution(top.identity, BOUND, basis, [top.identity], note, top)

    def _r3_found(self, tid, bounds, want):
        """{identity: [sessions, latest claim]} of R2 in every session that
        claimed the id."""
        found = {}
        for sess in sorted(self._by_task.get(tid, ())):
            res = self._r2(sess, tid, "only", bounds=bounds, want=want)
            if res.status == UNRESOLVED:
                continue
            for i in res.candidates:
                slot = found.setdefault(i, [set(), None])
                slot[0].add(sess)
                if res.claim is not None and (slot[1] is None or res.claim.pos > slot[1].pos):
                    slot[1] = res.claim
        return found

    def _r3(self, tid, at, want, no_session=None):
        bounds = _at_bounds(at)
        # C12 across sessions (review #20): the claims at or before ts in
        # every session first. The 2 s slack only when no session has one,
        # or, with `subject`, when none of them matches and a claim within
        # the slack does (the refinement _within applies per session).
        found, slack = self._r3_found(tid, bounds[:1], want), False
        if len(bounds) > 1:
            if not found:
                found, slack = self._r3_found(tid, bounds, want), True
            elif want and not any(want in self.norms(i) for i in found):
                skewed = {i: v for i, v in self._r3_found(tid, bounds, want).items()
                          if want in self.norms(i)}
                if skewed:
                    found, slack = skewed, True
        kind, sess = no_session or (None, "")
        if not found:
            why = ("" if not kind else f"'{sess}' is not a session UUID; " if kind == "not_uuid"
                   else f"session {sess} holds no task {tid}; ")
            return Resolution(None, UNRESOLVED, "only", [], f"{why}no task carries id {tid}")
        order = sorted(found, key=lambda i: found[i][1].pos if found[i][1] else (_TS_MIN, 0),
                       reverse=True)
        picked = order
        if len(order) > 1 and want:
            picked = [i for i in order if want in self.norms(i)] or order
        if len(picked) == 1:
            ident = picked[0]
            owners = ",".join(sorted(s[:8] for s in found[ident][0] if s)) or "?"
            note = ""
            if kind:
                why = (f"'{sess}' is not a session UUID" if kind == "not_uuid"
                       else f"session {sess} holds no task {tid}")
                note = f"{why}; bound to the only task carrying that id (session {owners})"
            elif len(order) > 1:
                note = f"the subject picks one of {len(order)} tasks carrying id {tid} (session {owners})"
            if slack:
                note = (note + "; " if note else "") + "bound within the 2 s slack after the row"
            return Resolution(ident, BOUND, "only", [ident], note, found[ident][1])
        why = ""
        if kind:
            why = (f" ('{sess}' is not a session UUID)" if kind == "not_uuid"
                   else f" (session {sess} holds none of them)")
        return Resolution(None, AMBIGUOUS, "only", order,
                          f"task_id {tid} names more than one task in the {self.project} ledger — "
                          f"{_describe({i: found[i][0] for i in order})}. Pass the parent's session "
                          f"UUID as SESSION_UUID{why} (4th argument; `review-queue pending "
                          f"{self.project} --json` lists it)")

    # -- task store ---------------------------------------------------------

    def find_task_store(self, session, epoch=None, *, ordinal=None, tasks_root=None,
                        teams_root=None, config_dir=None):
        """The TaskList store (a directory under tasks_root) that holds the
        epoch's tasks. Default epoch: current_epoch(), else the newest one.
        A team config linking the store to the session wins (verified);
        otherwise the content match decides (unverified). Stores untouched
        since before the epoch began are skipped by the content match."""
        session = str(session or "")
        config = config_dir or default_config_dir()
        root = tasks_root or default_tasks_root(config)
        teams = teams_root or default_teams_root(config)
        eps = self.epochs(session)
        if ordinal is not None:
            ep = next((e for e in eps if e.ordinal == int(ordinal)), None)
        elif epoch is not None:
            ep = self.epoch(session, int(epoch))
        else:
            cur = self.current_epoch(session)
            ep = self.epoch(session, cur) if cur is not None else (eps[-1] if eps else None)
        if ep is None:
            return StoreMatch(None, "no_epoch", None, None, {}, False)
        expected = {}
        for project, ev in self._epoch_creates.get((session, ep.ordinal), ()):
            tid, ident = claim_key(ev)[2], event_identity(ev)
            if not tid.isdigit() or ident is None:
                continue
            if project == self.project:
                norms = self.norms(ident)
            else:  # another project's create: its own norm and subject
                norms = {ident[0]} | ({normalize_subject(ev["subject"])}
                                      if isinstance(ev.get("subject"), str) and ev["subject"] else set())
            expected.setdefault(tid, set()).update(norms)
        scores = self._content_scores(ep, expected, root) if expected else {}
        team = self._team_store(session, ep, teams, os.path.join(config, "sessions"), root)
        conflict = ""
        if team is not None:
            name, how = team
            if not (scores and scores.get(name, 0) == 0):
                return StoreMatch(name, f"teams_config:{how}", os.path.join(root, name), ep, scores, True)
            conflict = f";team_conflict:{name}"  # its store holds none of the epoch's tasks
        if not expected:
            return StoreMatch(None, "no_creates" + conflict, None, ep, {}, False)
        if scores is None:
            return StoreMatch(None, "no_tasks_root" + conflict, None, ep, {}, False)
        if not scores:
            return StoreMatch(None, "no_match" + conflict, None, ep, {}, False)
        best = max(scores.values())
        top = sorted(n for n, v in scores.items() if v == best)
        name, basis = None, f"ambiguous:{','.join(top)}"
        if len(top) == 1:
            name, basis = top[0], f"content_match:{best}/{len(expected)}"
        else:
            by_hwm = [n for n in top if _highwatermark(os.path.join(root, n)) == ep.max_id]
            if len(by_hwm) == 1:
                name, basis = by_hwm[0], f"content_match+highwatermark:{best}/{len(expected)}"
        return StoreMatch(name, basis + conflict, os.path.join(root, name) if name else None,
                          ep, scores, False)

    def _content_scores(self, ep, expected, root):
        """{store: how many of the epoch's (id, subject) it holds}, or None
        when the tasks root cannot be read."""
        since = ep.start[0].timestamp() - 60 if ep.start and ep.start[0] > _TS_MIN else None
        try:
            dirs = [d for d in os.scandir(root) if d.is_dir(follow_symlinks=False)]
        except OSError:
            return None
        scores = {}
        for d in dirs:
            try:
                if since is not None and d.stat(follow_symlinks=False).st_mtime < since:
                    continue
            except OSError:
                continue
            hits = 0
            for tid, norms in expected.items():
                subj = (_read_json(os.path.join(d.path, f"{tid}.json")) or {}).get("subject")
                if isinstance(subj, str) and normalize_subject(subj) in norms:
                    hits += 1
            if hits:
                scores[d.name] = hits
        return scores

    def _team_store(self, session, ep, teams_root, sessions_dir, root):
        """(store, how) of the latest team config that links a store to the
        session and was created no later than the epoch began (C14), or None.
        how: "lead_session" (leadSessionId is the session) or "process" (a
        sessions/<pid>.json naming the session started within 60 s of the
        team's createdAt: a launch that /resumed into the session)."""
        starts = []
        try:
            pid_files = [e.path for e in os.scandir(sessions_dir)
                         if e.name.endswith(".json")]
        except OSError:
            pid_files = []
        for path in pid_files:
            info = _read_json(path) or {}
            if info.get("sessionId") == session and _int(info.get("startedAt")) is not None:
                starts.append(info["startedAt"])
        try:
            teams = list(os.scandir(teams_root))
        except OSError:
            return None
        limit = ep.start[0].timestamp() + TEAM_START_SLACK_S if ep.start and ep.start[0] > _TS_MIN else None
        best = None
        for t in teams:
            cfg = _read_json(os.path.join(t.path, "config.json"))
            created = _int((cfg or {}).get("createdAt"))
            if cfg is None or created is None:
                continue
            name = cfg.get("name") if isinstance(cfg.get("name"), str) else t.name
            if not _SESSION_FILE_RE.fullmatch(name) or not os.path.isdir(os.path.join(root, name)):
                continue
            if cfg.get("leadSessionId") == session:
                how = "lead_session"
            elif any(abs(s - created) <= TEAM_START_SLACK_S * 1000 for s in starts):
                how = "process"
            else:
                continue
            if limit is not None and created / 1000 > limit:
                continue
            if best is None or created > best[0]:
                best = (created, name, how)
        return best[1:] if best else None


def _highwatermark(store):
    try:
        with open(os.path.join(store, ".highwatermark"), encoding="utf-8") as fh:
            v = fh.read().strip()
    except OSError:
        return None
    return int(v) if _DIGITS_RE.fullmatch(v) else None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _ident_json(i):
    return {"subject_norm": i[0], "create_seq": i[1]} if i else None


def _claim_json(c):
    if c is None:
        return None
    return {"session_uuid": c.session_uuid, "task_id": c.task_id, "tl_epoch": c.tl_epoch,
            "seqno": c.seqno, "ts": c.ts, "ev": c.ev}


def resolution_json(res):
    return {"status": res.status, "identity": _ident_json(res.identity), "basis": res.basis,
            "candidates": [_ident_json(i) for i in res.candidates], "note": res.note,
            "claim": _claim_json(res.claim)}


def resolution_tsv(res):
    if res.status == BOUND:
        return f"{res.identity[0]}\t{res.identity[1]}" + (f"\nNOTE\t{res.note}" if res.note else "")
    if res.status == AMBIGUOUS:
        return f"AMBIGUOUS\t{res.note}"
    return "MISS"


def epoch_json(e):
    return {"ordinal": e.ordinal, "tl_epoch": e.tl_epoch, "first_seqno": e.first_seqno,
            "open_reason": e.open_reason, "max_id": e.max_id, "stamped": e.stamped,
            "first_ts": e.first_ts, "n_created": e.n_created, "first_project": e.first_project}


def _dash(v):
    return "-" if v is None else str(v)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="task_epoch.py",
                                 description="Resolve a (session, task id) to a task identity "
                                             "across TaskList epochs (S2-T0b-1, #113).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve", help="resolve a task id to (subject_norm, create_seq)")
    r.add_argument("project")
    r.add_argument("task_id")
    r.add_argument("--session", default="")
    r.add_argument("--epoch", type=int)
    r.add_argument("--at", help="ISO-8601 ts of the row being resolved")
    r.add_argument("--seqno", type=int, help="ledger seqno of the row (inclusive position)")
    r.add_argument("--subject")
    r.add_argument("--identity", help="SUBJECT_NORM:CREATE_SEQ (rule R0)")
    e = sub.add_parser("epochs", help="list a session's TaskList epochs")
    e.add_argument("project")
    e.add_argument("--session", required=True)
    s = sub.add_parser("store", help="find the task store directory of an epoch")
    s.add_argument("project")
    s.add_argument("--session", required=True)
    grp = s.add_mutually_exclusive_group()
    grp.add_argument("--epoch", type=int)
    grp.add_argument("--ordinal", type=int)
    s.add_argument("--tasks-root")
    s.add_argument("--teams-root")
    s.add_argument("--config-dir")
    for p in (r, e, s):
        p.add_argument("--format", choices=("tsv", "json"), default="tsv")
        p.add_argument("--metrics-dir")
    args = ap.parse_args(argv)

    identity = None
    if args.cmd == "resolve" and args.identity is not None:
        try:
            identity = parse_identity_arg(args.identity)
        except ValueError as exc:
            ap.error(str(exc))
    at = None
    if args.cmd == "resolve" and args.at is not None:
        if instant(args.at) is None:
            ap.error(f"--at: not an ISO-8601 timestamp: {args.at!r}")
        at = (args.at, args.seqno)
    if not _PROJECT_RE.fullmatch(args.project):
        if args.cmd == "resolve":
            print("MISS" if args.format == "tsv" else json.dumps(
                {"status": UNRESOLVED, "note": "invalid project name"}), end="")
            return 0
        ap.error(f"invalid project name {args.project!r}")

    try:
        idx = TaskIndex.from_ledger(args.project, metrics_dir=args.metrics_dir)
        for w in idx.warnings:
            print(f"task_epoch: {w}", file=sys.stderr)
        if args.cmd == "resolve":
            if at is None and args.seqno is not None:
                rows = [ev for ev in read_ledger(args.project, idx.metrics_dir)
                        if ev.get("seqno") == args.seqno]
                if len(rows) != 1:
                    ap.error(f"--seqno {args.seqno} matches {len(rows)} ledger rows; pass --at too")
                at = (rows[0].get("ts"), args.seqno)
            res = idx.resolve(args.session or None, args.task_id, epoch=args.epoch, at=at,
                              subject=args.subject, identity=identity)
            if args.format == "json":
                print(json.dumps(resolution_json(res)))
            else:
                if res.status == UNRESOLVED and res.note:
                    print(f"task_epoch: {res.note}", file=sys.stderr)
                print(resolution_tsv(res), end="")
            return 0
        if args.cmd == "epochs":
            eps = idx.epochs(args.session)
            if args.format == "json":
                print(json.dumps([epoch_json(x) for x in eps]))
            else:
                for x in eps:
                    print("\t".join((str(x.ordinal), _dash(x.tl_epoch), _dash(x.first_seqno),
                                     x.open_reason, _dash(x.max_id),
                                     "stamped" if x.stamped else "derived",
                                     str(x.n_created), _dash(x.first_ts), _dash(x.first_project))))
            return 0
        m = idx.find_task_store(args.session, args.epoch, ordinal=args.ordinal,
                                tasks_root=args.tasks_root, teams_root=args.teams_root,
                                config_dir=args.config_dir)
        if args.format == "json":
            print(json.dumps({"task_store": m.name, "task_store_basis": m.basis,
                              "verified": m.verified, "path": m.path,
                              "epoch": epoch_json(m.epoch) if m.epoch else None,
                              "scores": m.scores}))
        else:
            print(f"{m.name or 'NONE'}\t{m.basis}\t{'verified' if m.verified else 'unverified'}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"task_epoch: {exc}", file=sys.stderr)
        if args.cmd == "resolve":
            print("MISS" if args.format == "tsv" else json.dumps(
                {"status": UNRESOLVED, "note": str(exc)}), end="")
            return 0
        return 1


if __name__ == "__main__":
    sys.exit(main())
