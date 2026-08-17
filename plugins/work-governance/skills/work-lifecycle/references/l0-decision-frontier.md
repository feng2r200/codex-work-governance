# L0 Decision Frontier

Use a decision frontier when the user goal is valuable but not yet shaped
enough for a durable Plan.

The model owns discovery. First read the relevant files, logs, docs, or runtime
state that can answer agent-owned unknowns. Do not ask the user to provide facts
the project can reveal safely.

Turn the remaining user-owned uncertainty into the smallest useful frontier:

- state the current goal anchor in one sentence;
- list only choices that can change goal, behavior, cost, safety, delivery
  form, or acceptance evidence;
- include the recommended answer and the reason it is the default;
- ask one blocking question at a time unless several choices share the same
  decision moment;
- record the accepted answer as a Plan confirmation only when it becomes durable
  Plan authority.

Prefer choices over essays. The user should be able to approve, reject, or edit
the recommended answer without reading a speculative design document.

Do not use a frontier for ordinary local facts, reversible implementation
details, progress updates, or decision-free continuation. Those stay in L0
exploration or L3 execution.

Validation standard: every question names the blocked target, the recommended
answer, and the evidence or constraint that made local discovery insufficient.
