# V11.22 Phased Rollout: Self-Review Postamble (remaining ~100 agents)

V11.21 ships the V11.21 Self-Review Postamble on the top-8 high-usage agents only:

- spec-implementer-v11
- backend-architect
- frontend-specialist
- database-engineer
- security-engineer
- testing-engineer
- performance-optimizer
- ai-integration-specialist

The remaining ~100 agents in `~/.claude/agents/` are an **explicitly documented coverage gap**. When they run a task at V11.21:

- Their `TaskUpdate(completed)` payload will NOT include `metadata.artifacts.self_review`.
- The orchestrator's dispatch-trace logs `self_review_omitted=true` so the gap is visible in `~/.agent-metrics/dispatch-trace.jsonl`.
- They STILL get a paired adversarial-lite-reviewer sibling — only Layer A is missing for them.

## V11.22 plan

1. Sort remaining agents by realized dispatch count (from V11.21 dispatch-trace).
2. Add postamble to the next top-20 by usage in a single V11.22 commit.
3. Add to remaining agents in tranches over subsequent point releases.
4. Bulk insertion is mechanical (the postamble is the same template); the lift is review of each agent's existing format to ensure no conflict.

## Identifying coverage in your project

```bash
# How many tasks under YOUR project were dispatched to agents WITHOUT the postamble?
jq -c 'select(.self_review_omitted == true and .project == "YOUR_PROJECT") | {ts, task_id, spawned_agent}' \
   ~/.agent-metrics/dispatch-trace.jsonl
```

If your project relies heavily on agents not in the top-8, escalate to V11.22 prioritization by surfacing the gap in your handoff.
