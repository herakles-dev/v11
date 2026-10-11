# Contract House Rules

Gotchas that bit earlier contracts, stated as instructions; the contract executor reads this before every contract.

1. Run pytest as `env -u V11_AUTO_PAIR_REVIEW …`; the session's ambient lever leaks into tests (bit: SC-A4d finding 5, 18 tests failed).
2. `tests/.last-run-metrics.json` is rewritten by every test run; restore it and never commit it (bit: SC Part A, per the contract text; no report line).
3. Heading checks must skip fenced code blocks (bit: SC-M1, vacuous fenced-code heading verifies).
4. `~/.agent-registry/agents.json` is keyed by name (`.agents["name"]`), not a list (bit: SC-M1, wrong registry schema in a verify; sprint-SC-contract-mode.md Evidence paragraph).
5. `--regression` does not select base-tree equality tests; config or emitted-JSON changes need `--regression-extended` in a background shell (bit: SC-M1, `test_t9_cost_ledger_legacy_equals_base`).
6. cost-ledger emits `pricing.source`; provenance text goes in `notes`, never in `pricing.source` (bit: SC-M1, commit abcfbd2).
7. `metadata.wave` must be numeric and project-unique, set at task creation; later updates are invisible to wave-check (orchestrator rule, listed so reviewers can flag violations) (bit: SC-A4d finding 3).
8. A task whose `metadata.agent` starts with `adversarial-` counts as a review task and needs a verdict; contract-executor avoids this (bit: SC-A4d finding 4).
9. Before changing a file or field, find what else reads it and keep those readers working (bit: SC-M1, the `pricing.source` escape and the off-mode path).
10. Write the report to the outbox file and also return it; notifications truncate long results (bit: SC-A4d finding 7).
