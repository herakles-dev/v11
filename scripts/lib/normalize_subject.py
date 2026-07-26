#!/usr/bin/env python3
"""
Canonical v11_normalize_subject implementation (ADR-LEDGER §2.1).

This is the SINGLE canonical implementation. The bash function
v11_normalize_subject in common.sh CALLS this script — it never
re-implements the algorithm. bash≡Python parity is guaranteed by
construction: there is only one code path.

Usage (standalone):
    python3 normalize_subject.py "Subject string here"

Usage (from Python):
    from normalize_subject import normalize_subject
    norm = normalize_subject("My Task: Fix the parser")

Algorithm (applied in exact order per ADR §2.1):
    1. Unicode normalize to NFC.
    2. Lowercase via str.casefold() (Unicode-aware; never tr/awk).
    3. Strip leading task-id prefix.
    4. Replace Unicode whitespace runs with single ASCII space.
    5. Strip leading/trailing ASCII punctuation and whitespace.
    6. Collapse internal punctuation runs (single space per run).
    7. Truncate to 200 Unicode codepoints.
    8. If empty → "__empty__".
"""

import re
import sys
import unicodedata


# ---------------------------------------------------------------------------
# Step 3 — task-id prefix regex (compiled once)
# Matches: "#7. ", "T12 - ", "Task #3 - ", "7. ", "7) ", "7: ", etc.
# Applied case-insensitively, stripped once (not globally).
# The ADR pattern:
#   ^\s*(#?\d+[.):\-]?\s+|t-?\d+[.):\-]?\s+|task\s+#?\d+[.):\-]?\s+)
# ---------------------------------------------------------------------------
_TASK_ID_PREFIX = re.compile(
    r"""^\s*(?:
        \#?\d+[.):\-]?\s+          # #7.  /  7:  /  7)  /  7-  /  7  (with trailing space)
        |t-?\d+[.):\-]?\s+         # T12   T-12  T12:  T12-
        |task\s+\#?\d+[.):\-]?\s+  # Task #3 -  /  Task 3:
    )""",
    re.IGNORECASE | re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Step 5 — leading/trailing strip chars (ASCII punctuation + whitespace)
# ADR §2.1 step 5: strip chars in [ \t\r\n.,:;!?\-_/\\|"'`()[]{}]
# We build a translation-free strip by using str.strip with the explicit set.
# Note: inside a Python character class, ] must be first or escaped,
# and - must be first/last/escaped to be literal.
# ---------------------------------------------------------------------------
_STRIP_CHARS = ' \t\r\n.,:;!?\\-_/\\|"\'`()[]{}'

# ---------------------------------------------------------------------------
# Step 6 — internal punctuation-run collapse
# "Any run of one-or-more of [.,:;!?_/\\|\-] (NOT spaces, NOT alphanumerics)"
#
# Per ADR §2.1 step 6 the parenthetical "(NOT spaces, NOT alphanumerics)"
# describes the CATEGORY — ASCII punctuation that is neither whitespace nor
# alphanumeric — rather than an exclusion list beyond the named chars.
# Row 19 of the pinned corpus confirms: "Fix the parser (round 2)" normalises
# to "fix the parser round 2", so parens collapse to a space.
# The explicit charset therefore also includes the brackets/quotes/parens from
# the step-5 strip set (ADR §2.1 step 5): .,:;!?-_/\|"'`()[]{}.
# Emoji and non-ASCII letters are excluded (non-ASCII, not in the ASCII set).
# ---------------------------------------------------------------------------
_PUNCT_RUN = re.compile(r'[.,:;!?_/\\|\-"\'`()\[\]{}]+')

# ---------------------------------------------------------------------------
# Step 4 / repeated step — Unicode whitespace runs → single ASCII space
# \s in Python re is Unicode-aware when used on str objects.
# ---------------------------------------------------------------------------
_WS_RUN = re.compile(r'\s+')


def normalize_subject(subject: str) -> str:
    """
    Normalize a task subject string to its canonical form per ADR §2.1.

    Parameters
    ----------
    subject : str
        Raw task subject. May contain any Unicode codepoints.

    Returns
    -------
    str
        Normalized subject (lowercase, no task-id prefix, whitespace collapsed,
        internal punctuation runs collapsed, truncated at 200 codepoints).
        "__empty__" when the result would be empty.
    """
    if not isinstance(subject, str):
        # Non-string input (e.g. bytes, None) → empty bucket
        return "__empty__"

    # Step 1: Unicode NFC normalization.
    # Ensures NFD sequences (e + combining acute) collapse to precomposed forms
    # (é U+00E9) so the same visual string always maps to the same bytes.
    s = unicodedata.normalize("NFC", subject)

    # Step 2: Lowercase via Unicode simple case fold.
    # str.casefold() handles ß→ss, İ→i̇, etc. — correct for multilingual subjects.
    s = s.casefold()

    # Step 2b (pre-step-4 control-char sanitisation):
    # ASCII C0 and C1 control characters (U+0000–U+001F, U+007F, U+0080–U+009F)
    # are not matched by Python's \s (which only covers whitespace categories).
    # ADR §2.1 step-4 note: "NUL must not truncate the string mid-process";
    # row 15 corpus entry confirms BEL (\x07) + NUL (\x00) are stripped.
    # Replace them with a space so the subsequent whitespace-collapse (step 4)
    # absorbs them cleanly without any chance of NUL truncation.
    s = re.sub(r'[\x00-\x1f\x7f\x80-\x9f]', ' ', s)

    # Step 3: Strip a leading task-id prefix (once, case-insensitively).
    # Examples: "#7. ", "T12: ", "Task #3 - " are cosmetic and must not split identity.
    s = _TASK_ID_PREFIX.sub("", s, count=1)

    # Step 4: Replace every maximal run of Unicode whitespace with a single ASCII space.
    s = _WS_RUN.sub(" ", s)

    # Step 5: Strip leading/trailing ASCII punctuation and whitespace.
    s = s.strip(_STRIP_CHARS)

    # Step 6: Collapse internal punctuation runs to a single space,
    # then re-collapse any resulting whitespace runs (fixed point in one pass).
    s = _PUNCT_RUN.sub(" ", s)
    s = _WS_RUN.sub(" ", s)

    # Step 7: Truncate to 200 Unicode codepoints.
    # len() on a Python str counts codepoints (not bytes, not grapheme clusters).
    # The ADR mandates codepoint-counted truncation.
    if len(s) > 200:
        s = s[:200]

    # Step 8: Fall back to __empty__ if the result is empty.
    s = s.strip()  # final whitespace trim after truncation
    if not s:
        return "__empty__"

    return s


# ---------------------------------------------------------------------------
# CLI entrypoint — called by v11_normalize_subject in common.sh
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        # No argument: read from stdin (allows piping)
        subject = sys.stdin.read().rstrip("\n")
    else:
        subject = sys.argv[1]
    print(normalize_subject(subject), end="")
