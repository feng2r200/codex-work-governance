---
name: subagent-governance
description: Use before delegating work to SubAgents or when reviewing multi-agent ownership, context handoff, model choice, parallelism, timeouts, redundant work, and how discoveries should return to the parent.
---

# SubAgent Governance

Delegate when another agent has a clear consumer and provides net value through
independent parallel work, context isolation, relevant specialization, or an
independent challenge. Direct execution is often better for small reads,
mechanical integration, and work whose coordination cost exceeds its execution.

## Choose The Shape

- Parallelize only independent boundaries. Keep dependent stages sequential.
- Give each writable area one owner. Never start overlapping replacement work
  while an owner may still be active.
- Use the strongest suitable parent for integration and material decisions.
  Select SubAgent models and reasoning effort from the task's difficulty,
  latency, cost, and available capabilities; do not encode a permanent
  role-to-model matrix in governance.
- A SubAgent inherits the parent's goal, authority, and active Plan. It does not
  invent a second parent Plan or widen the action boundary.

## Adaptive Delegation Contract

Every delegation needs enough context to be executable:

- concrete goal and owned scope;
- expected artifact or answer and its consumer;
- stop condition and how completion will be checked;
- ownership boundary, especially for shared files or state.

Add non-goals, allowed or forbidden actions, dependencies, evidence, validation,
and output structure only when the risk or ambiguity requires them. Do not make
a long checklist the price of a tiny delegation.

If the delegated result depends on a predecessor's exact terminal outcome,
provide a stable Task, artifact, evidence, or handoff reference. Do not expect a
generic bounded project summary to contain arbitrary completed history, and do
not ask the receiving Agent to infer completion from adjacent current state.

When a shared persistence capability is available, use its own Skill so agents
can retrieve the same project reasoning, decisions, and active state. Multiple
agents may read; assign one record owner or clearly partition writes to prevent
conflicting narrative state.

## Coordinate By Evidence Change

Keep the continuation packet small: goal and authority references, owned input
revision, current result, open issue, and next condition that needs attention.
Pass exact artifacts on demand rather than replaying the conversation. A new
owner must still receive enough context to act without inventing missing facts.

Prefer event-driven or bounded blocking waits when available. Retain the latest
progress cursor or equivalent evidence identity; after an unchanged result,
back off or do independent work instead of repeatedly reading full history.
Missing or uncertain status is not an unchanged result. A new external fact,
deadline, blocker, or ownership risk can justify a fresh targeted check.

Give each issue one actionable feedback package: affected input, evidence,
impact, requested correction, and acceptance. Update it when evidence or the
decision changes. Do not resend it, commission another review, or launch a
replacement owner merely because the same issue remains open. Retry after a
bounded failure diagnosis or a changed input, with a concrete consumer.

## Discovery Channels

- **Blocking discovery:** direction is wrong, the final result would change,
  authority is missing, or continuing risks irreversible harm. Stop affected
  work and notify the parent with evidence.
- **Non-blocking discovery:** improvement, debt, reusable lesson, or adjacent
  risk that does not invalidate the current route. Continue the assigned work,
  preserve the finding, and return it for the parent's final report or later
  optimization.

## Recovery And Integration

A timeout or quiet agent is not itself failure. Inspect available status,
artifacts, diffs, and validation evidence before retrying or replacing it. Do
not launch a duplicate owner into the same scope.

The parent validates outputs, resolves cross-agent conflicts, owns confirmation
gates, and makes the final claim. SubAgent conclusions are inputs, not inherited
authority.
