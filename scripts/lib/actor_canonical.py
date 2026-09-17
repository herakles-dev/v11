"""v11.44 — shared read-side actor canonicalization (Python side).

Single source of truth for the fold rule is hooks/lib/actor-canonical.json — this
module just loads it. The bash counterpart is v11_canonical_actor() in
hooks/lib/common.sh; both consult the same JSON so they cannot drift (a
cross-language identity test asserts agreement — see tests/test_actor_canonical.py).

Contract:
  canonical_actor(raw) -> str
    - folds the orchestrator identity family -> "orchestrator"
    - every other value passes through UNCHANGED (non-lossy)
    - V11_ORCH_QUALITY=off  -> returns raw verbatim (legacy literal-string match)

Used by agent-scorecard / agent-effectiveness inside their python3 heredocs:
    sys.path.insert(0, os.path.join(V11_HOME, "scripts", "lib"))
    from actor_canonical import canonical_actor
The fold table is read once and cached; apply canonical_actor() per-record freely.
"""
import json
import os

_FOLD = None


def _table_path():
    v11_home = os.environ.get("V11_HOME") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    return os.environ.get(
        "V11_ACTOR_CANONICAL_TABLE",
        os.path.join(v11_home, "hooks", "lib", "actor-canonical.json"),
    )


def load_fold(force=False):
    """Load and cache the fold map. Missing/broken table -> empty map (pass-through)."""
    global _FOLD
    if _FOLD is not None and not force:
        return _FOLD
    try:
        with open(_table_path(), "r") as fh:
            data = json.load(fh)
        fold = data.get("fold", {})
        _FOLD = fold if isinstance(fold, dict) else {}
    except Exception:
        # Never let a missing/corrupt table break a scorecard read — degrade to identity.
        _FOLD = {}
    return _FOLD


def canonical_actor(raw):
    """Fold the orchestrator family -> 'orchestrator'; pass everything else through."""
    if os.environ.get("V11_ORCH_QUALITY") == "off":
        return raw
    if raw is None:
        return raw
    return load_fold().get(raw, raw)
