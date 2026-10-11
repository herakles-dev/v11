#!/usr/bin/env python3
"""
guard-worktree-isolation's TaskList reconcile (S2-R6): one pass over the
host-global $METRICS_DIR/worktree-expectations.jsonl.

    python3 -I -S worktree_registry.py REGISTRY NEED_GIT REPO_ROOT NOW_COUNT \
        CURRENT_HEAD GRACE_SECONDS TTL_DAYS SCOPE PENDING_TTL_DAYS

Replaces the per-row bash loop (4-6 jq + date per row) with the same rules:
a `pending` row older than GRACE_SECONDS is `resolved` when the worktree
count grew past its count_at_spawn (plus the #27 stale-ref advisory when
HEAD moved) and `alerted` otherwise; every other line is copied through
byte-for-byte. Field reads mirror the old `$(jq -r '.key // default')`
calls, and the alert/advisory text and rewritten rows are byte-for-byte
the old ones; a value json.dumps cannot print as jq 1.6 does (float, huge
int, lone surrogate) is handed to that same jq call.

Also in the pass: terminal rows older than TTL_DAYS (0 = never) are
pruned, pending rows never on that account; with SCOPE=repo a pending row
recorded for another repo is left for that repo's TaskList. NEED_GIT=0
(the hook saw no row that can be pending, so it ran no git) leaves pending
rows alone. Review #11 MED-1: those two rules leave a pending row from a
repo that never calls TaskList again stuck in the host-global registry
forever, so a pending row older than PENDING_TTL_DAYS (0 = never) is
pruned regardless of SCOPE or NEED_GIT — silently, no alert. The file is
rewritten (tmp + rename) only when something changed.

Review #11 LOW-2: the read-compute-replace here races a concurrent
spawn-side append (hooks/guard-worktree-isolation's Task|Agent branch,
same REGISTRY path). Both sides take a non-blocking flock on a sibling
REGISTRY.lock; if this pass can't get it (the spawn side holds it that
instant), it skips entirely — no read, no alerts, no rewrite — rather
than risk clobbering the append. The registry is retried whole on the
next TaskList; a TaskList fire must never block on the lock.

Any error leaves the registry untouched and prints nothing.
"""
import fcntl, json, os, re, sys, time

TS = re.compile(r"\A\s*([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})(?:(?:[Tt]|\s+)([0-9]{1,2}):([0-9]{2})"
                r"(?::([0-9]{2})(?:[.,][0-9]+)?)?\s*([Zz]|[+-](?:[0-9]{1,2}:[0-9]{2}|[0-9]{1,4}))?)?\s*\Z", re.A)
DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def jq(line, flag, prog):
    # The pre-S2-R6 per-row call, for values this script cannot print
    # exactly as jq 1.6 does (floats, huge ints, lone surrogates).
    import subprocess
    out = subprocess.run(["jq", flag, prog], input=line, capture_output=True).stdout
    return out.decode("utf-8", "surrogateescape").rstrip("\n")


def plain(v):
    # Values that json.dumps and `jq -c` / `jq -r` print identically.
    if v is None or isinstance(v, bool):
        return True
    if isinstance(v, int):
        return abs(v) < 10 ** 15
    if isinstance(v, str):
        return "\x7f" not in v and not any("\ud800" <= c <= "\udfff" for c in v)
    if isinstance(v, list):
        return all(plain(x) for x in v)
    if isinstance(v, dict):
        return all(plain(k) and plain(x) for k, x in v.items())
    return False


def surrogates(v):
    # Lone-surrogate escapes (jq 1.6 rejects the line) or invalid UTF-8
    # (jq substitutes): such a row is read through jq alone.
    if isinstance(v, str):
        return any("\ud800" <= c <= "\udfff" for c in v)
    if isinstance(v, list):
        return any(surrogates(x) for x in v)
    if isinstance(v, dict):
        return any(surrogates(k) or surrogates(x) for k, x in v.items())
    return False


def get(o, key, default):
    # `.key // default` on an object or null.
    v = o.get(key) if isinstance(o, dict) else None
    return default if v is None or v is False else v


def raw(o, key, default, line, via_jq=False):
    # "$(jq -r .key // default)": jq text, trailing newlines stripped.
    v = get(o, key, default)
    if via_jq:
        v = None
    elif isinstance(v, bool):
        v = "true"
    elif isinstance(v, int) and plain(v):
        v = str(v)
    if not (isinstance(v, str) and plain(v)):
        v = jq(line, "-r", ".%s // %s" % (key, json.dumps(default)))
    return v.rstrip("\n")


def zsecs(z):
    sign = -1 if z[0] == "-" else 1
    h, _, m = z[1:].partition(":")
    if not m:
        h, m = (h, "0") if len(h) <= 2 else (h[:-2], h[-2:])
    h, m = int(h), int(m)
    return None if h * 60 + m > 1440 else sign * (h * 3600 + m * 60)


def epoch(ts, now):
    # `date -d TS +%s` for the ISO-8601 forms (T or spaces, optional
    # seconds/fraction, Z / +-HH:MM / +-HHMM / none = local time); None where
    # GNU date fails. "" is local midnight today, as `date -d ""`.
    if ts == "":
        return int(time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, -1)))
    m = TS.match(ts)
    if not m:
        return None
    y, mo, d, h, mi, s = (int(x or 0) for x in m.groups()[:6])
    z = m.group(7)
    off = 0 if z is None or z in "Zz" else zsecs(z)
    feb = 29 if (y % 4 == 0 and y % 100 != 0) or y % 400 == 0 else 28
    if off is None or not 1 <= mo <= 12 or not 1 <= d <= (feb if mo == 2 else DAYS[mo - 1]) \
            or h > 23 or mi > 59 or s > 59:
        return None
    if z is None:
        try:
            return int(time.mktime((y, mo, d, h, mi, s, 0, 0, -1)))
        except (OverflowError, ValueError):
            return None
    yy = y - (mo <= 2)
    era, yoe = yy // 400, yy % 400
    doy = (153 * (mo + (-3 if mo > 2 else 9)) + 2) // 5 + d - 1
    days = era * 146097 + yoe * 365 + yoe // 4 - yoe // 100 + doy - 719468
    return days * 86400 + h * 3600 + mi * 60 + s - off


def main():
    reg, need_git, repo_root, now_count, cur_head, grace, ttl, scope, pending_ttl_days = sys.argv[1:10]
    now = int(time.time())
    grace, ttl, nc = int(grace), int(ttl) * 86400, int(now_count)
    pending_ttl = int(pending_ttl_days) * 86400
    # A terminal ts whose date sorts after this is inside the TTL at any
    # UTC offset (<= 24 h): kept without parsing.
    keep_after = time.strftime("%Y-%m-%d", time.gmtime(now - ttl + 86400))
    # Review #11 LOW-2: hold the lock for the whole read-compute-replace: a
    # torn read (or a rewrite computed from a stale snapshot) risks the
    # same clobber as an unlocked one. Non-blocking — a TaskList must never
    # wait on it — so a lock held by a concurrent spawn-side append just
    # skips this pass.
    try:
        lockf = open(reg + ".lock", "a+b")
    except OSError:
        return
    try:
        try:
            fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return
        try:
            _reconcile(reg, need_git, repo_root, now_count, cur_head, grace, ttl,
                       scope, pending_ttl, now, keep_after, nc)
        finally:
            try:
                fcntl.flock(lockf, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        lockf.close()


def _stale_base(repo_root, rh, spawn_epoch):
    # A worktree created for this spawn whose base is behind HEAD-at-spawn
    # (#27 only compares spawn-HEAD with now-HEAD, so it misses a worktree
    # that STARTED stale). Advisory; any git error/timeout skips silently.
    import subprocess
    out = []
    try:
        if spawn_epoch is None or not re.fullmatch(r"[0-9a-fA-F]{4,64}", rh, re.A):
            return out
        p = subprocess.run(["git", "-C", repo_root, "worktree", "list", "--porcelain"],
                           capture_output=True, timeout=5)
        if p.returncode != 0:
            return out
        wts, cur = [], {}
        for ln in p.stdout.decode("utf-8", "replace").split("\n") + [""]:
            if ln == "":
                if cur.get("path"):
                    wts.append(cur)
                cur = {}
            elif ln.startswith("worktree "):
                cur["path"] = ln[9:]
            elif ln.startswith("HEAD "):
                cur["head"] = ln[5:]
        main = os.path.realpath(repo_root)
        kept = []
        for w in wts[1:]:  # first entry is the main worktree
            path, head = w["path"], w.get("head", "")
            if os.path.realpath(path) == main or not re.fullmatch(r"[0-9a-f]{4,64}", head, re.A):
                continue
            try:
                # Creation time = mtime of the admin `gitdir` file (written at
                # `worktree add`, not on normal work); the dir mtime drifts.
                with open(os.path.join(path, ".git"), "r", encoding="utf-8", errors="replace") as gf:
                    first = gf.readline().strip()
                if not first.startswith("gitdir:"):
                    continue
                admin = first[7:].strip()
                if not os.path.isabs(admin):
                    admin = os.path.join(path, admin)
                if os.stat(os.path.join(admin, "gitdir")).st_mtime >= spawn_epoch - 60:
                    kept.append((path, head))
            except (OSError, ValueError):
                continue
        for path, head in kept[:3]:
            r = subprocess.run(["git", "-C", repo_root, "rev-list", "--count", "%s..%s" % (head, rh)],
                               capture_output=True, timeout=5)
            if r.returncode != 0:
                continue
            behind = int(r.stdout.decode().strip())
            if behind >= 1:
                out.append("WORKTREE BASE STALE: %s is %d commits behind HEAD at spawn (%s). "
                           "Agent may be editing old code. Fix: git -C %s reset --keep %s"
                           % (path, behind, rh[:8], path, rh))
    except Exception:
        pass
    return out


def _reconcile(reg, need_git, repo_root, now_count, cur_head, grace, ttl, scope,
               pending_ttl, now, keep_after, nc):
    with open(reg, "rb") as f:
        lines = f.read().split(b"\n")
    rows, msgs, changed = [], [], False
    for b in lines:
        if not b:  # empty lines are dropped, as before
            continue
        line = b.decode("utf-8", "surrogateescape")
        # Not JSON, or not an object: `.status` errored, the line is copied.
        # (Number forms only jq 1.6 accepts, like 01 or .5, land here too.)
        try:
            # -0 stays a float: jq prints it as -0, int() as 0.
            o = json.loads(line, parse_int=lambda n: float(n) if n == "-0" else int(n))
        except (ValueError, RecursionError):
            rows.append(b)
            continue
        if not (o is None or isinstance(o, dict)):
            rows.append(b)
            continue
        sur = surrogates(o)
        st = raw(o, "status", "pending", b, sur)
        ts = raw(o, "ts", "", b, sur)
        if st != "pending":
            e = None
            if ttl > 0 and st in ("alerted", "resolved") and ts[:10] <= keep_after:
                e = epoch(ts, now)
            if e is not None and now - e > ttl:
                changed = True
            else:
                rows.append(b)
            continue
        # Review #11 MED-1: a pending row is otherwise only judged by a
        # TaskList that both sees NEED_GIT and (under SCOPE=repo) matches
        # its repo_root — a repo that never runs TaskList again leaves it
        # here forever. This cap prunes it regardless of scope or
        # need_git, silently (no alert; there is nothing to report on a
        # row no repo is coming back to reconcile).
        if pending_ttl > 0:
            e = epoch(ts, now)
            if e is not None and now - e > pending_ttl:
                changed = True
                continue
        rr = get(o, "repo_root", "")
        if need_git != "1" or (scope != "all" and rr != "" and rr != repo_root):
            rows.append(b)
            continue
        # Rows younger than the grace period haven't had a fair chance to
        # start (or finish creating a worktree) yet: left pending. An
        # unparseable ts reads as age 0, as the old `|| echo "$NOW_EPOCH"`.
        e = epoch(ts, now)
        age = now - (now if e is None else e)
        if age < grace:
            rows.append(b)
            continue
        rc = raw(o, "count_at_spawn", 0, b, sur)
        rc = rc if re.fullmatch(r"[0-9]+", rc, re.A) else "0"
        subj = raw(o, "description", "", b, sur)
        changed = True
        # A new worktree since the row's baseline is a best-effort "not
        # obviously broken" signal (no per-agent correlation key exists);
        # none is the alert. Either way the row turns terminal, so it alerts
        # once (guard-agent-stall's anti-spam convention).
        new = "resolved" if nc > int(rc) else "alerted"
        if plain(o):
            rows.append(json.dumps(dict(o or {}, status=new), ensure_ascii=False,
                                   separators=(",", ":")).encode())
        else:
            rows.append(jq(b, "-c", ".status = \"%s\"" % new).encode("utf-8", "surrogateescape"))
        if new == "resolved":
            # V11.35.6 (#27): HEAD moved since spawn, so the worktree forked
            # from a stale ref. Advisory only.
            rh = raw(o, "head_at_spawn", "unknown", b, sur)
            if rh != "unknown" and cur_head != "unknown" and rh != cur_head:
                msgs.append("STALE-REF ADVISORY (#27): agent (%s) worktree forked from %s, HEAD is now %s. "
                            "Agent may be working against stale code." % (subj, rh[:8], cur_head[:8]))
            if rh != "unknown" and os.environ.get("V11_WORKTREE_BASE_CHECK", "on") != "off":
                msgs.extend(_stale_base(repo_root, rh, e))
        else:
            mins = -(-age // 60) if age < 0 else age // 60
            msgs.append("\nWORKTREE ISOLATION ALERT: background agent \x27%s\x27 (%s), spawned\n"
                        "  %dm ago requesting isolation:\"worktree\", still shows no new worktree\n"
                        "  (count then=%s, now=%s). Possible silent no-op (improvements/12 H1).\n"
                        "  Check: git -C \"%s\" worktree list\n"
                        % (raw(o, "subagent_type", "unknown", b, sur), subj, mins, rc, now_count, repo_root))
    if msgs:
        text = "".join(m + "\n" for m in msgs)
        sys.stderr.buffer.write(text.encode("utf-8", "surrogateescape"))
        sys.stderr.flush()
        # A PostToolUse hook that exits 0 reaches the model only through a JSON
        # object on stdout; plain stderr is transcript-only. Emitting here costs no
        # extra fork on the hook's TaskList path (S2-R6 budget). Rollback:
        # V11_WORKTREE_GUARD_CONTEXT=off.
        if os.environ.get("V11_WORKTREE_GUARD_CONTEXT", "on") != "off":
            sys.stdout.write(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PostToolUse", "additionalContext": text}}) + "\n")
            sys.stdout.flush()
    if changed:
        tmp = "%s.tmp.%d" % (reg, os.getppid())
        with open(tmp, "wb") as f:
            f.write(b"".join(r + b"\n" for r in rows))
        os.replace(tmp, reg)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
