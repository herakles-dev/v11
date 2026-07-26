#!/usr/bin/env python3
"""
V11.25 post-commit hook: extract sprint-task patterns from a commit subject.

Usage:
    python3 postcommit_extract_patterns.py "COMMIT_SUBJECT"

Prints one pattern per line (e.g. "S55-T2") for subjects that match the
V11 sprint-task prefix convention.  Prints nothing if no pattern matches.

Supported shapes (prefix-anchored on the subject):
  Single:       S55-T2: feature description
  Prep:         S55-prep-T2: feature description
  Multi-comma:  S55-T2,T3: feature description
  Multi-plus:   S55-T2 + T3: feature description
  Mixed multi:  S55-T2,T3,T4: feature description

False-match guard: pattern must be anchored at START of subject.
Mid-subject tokens (e.g. "follow-up: fixed S46-T2 regression") do NOT match.
"""

import sys
import re

def extract_patterns(subject: str) -> list[str]:
    """Return list of sprint-task pattern strings extracted from subject."""
    # Sprint prefix: S\d+ or S\d+-prep (case-sensitive, V11 convention)
    SPRINT_PREFIX = r'^(S\d+(?:-prep)?)'
    SINGLE_T      = r'-(T[A-Za-z0-9]+)'
    MULTI_COMMA   = r'-(T[A-Za-z0-9]+(?:\s*,\s*T[A-Za-z0-9]+)+)'
    MULTI_PLUS    = r'-(T[A-Za-z0-9]+(?:\s*\+\s*T[A-Za-z0-9]+)+)'

    # Try multi shapes first (greedier), then single
    for t_part in [MULTI_COMMA, MULTI_PLUS, SINGLE_T]:
        full_pat = SPRINT_PREFIX + t_part + r':'
        m = re.match(full_pat, subject)
        if m:
            sprint = m.group(1)     # e.g. "S55" or "S55-prep"
            token_str = m.group(2)  # e.g. "T2,T3" or "T2 + T3" or "T2"
            # Split on comma or plus (with optional surrounding whitespace)
            tokens = re.split(r'\s*[,+]\s*', token_str)
            result = []
            for tok in tokens:
                tok = tok.strip()
                if re.match(r'^T[A-Za-z0-9]+$', tok):
                    result.append(f"{sprint}-{tok}")
            return result

    return []

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(0)
    subject = sys.argv[1]
    for p in extract_patterns(subject):
        print(p)
