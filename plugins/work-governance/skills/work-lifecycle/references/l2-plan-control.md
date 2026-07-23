# L2 Plan Control

Use Plan control when the work affects future execution, handoff, task queues,
facts, confirmation gates, artifacts, acceptance criteria, or rollback state.

Plan files:

- `_Plan/index.yaml`: active plan index.
- `_Plan/<plan-id>.md`: Markdown with YAML frontmatter as the only machine
  authority.
- `.logs/`: append-only process evidence; add it to `.git/info/exclude` in Git
  projects.

Controller gates:

- expected revision must match before writes;
- active Plan scope must not conflict with the requested Plan;
- task dependencies must be `verified` before dependent task start;
- confirmation references must exist and be accepted before high-impact steps;
- suspect, quarantined, or rollback-pending artifacts block closeout;
- logs are append-only and must not overwrite existing entries.

Allowed structural changes:

- `plan init`: create an active Plan and index.
- `plan revise`: increment revision and change structure after confirmation
  when required.
- `plan confirm`: attach a confirmation ref to a gate.
- `task start|block|verify|skip`: update task state.
- `log append`: preserve process evidence.

Validation standard: `plan validate` passes and the revision/history make the
current authority reproducible.
