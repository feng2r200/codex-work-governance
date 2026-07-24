# L3 Execution

Execute only the next authorized slice.

Before edits:

- require `plan authority check` to return `GOVERNED_ACTIVE` for
  Plan-controlled work;
- read the current authority files and relevant current code/docs;
- protect user changes and unrelated dirty worktree state;
- identify the exact files to edit and why those are the authority locations;
- define the command or inspection that will prove the slice.

During execution:

- keep changes scoped to the obligation;
- avoid parallel writes to the same data or remote surface;
- use deterministic scripts for repeated fragile work;
- record key evidence in `.logs/` only when a Plan exists and the record has
  handoff value;
- never promote `.logs` content into Plan facts without confirmation.

When recovering suspect artifacts, identify the repair task with
`resolves_artifacts`. This exception permits only the declared recovery work;
it does not clear the suspect state or make adjacent tasks executable. It
never permits progress through a `quarantined` or `rollback-pending` artifact.
Blocking the affected task remains legal after an artifact becomes suspect;
the fail-safe transition must not be prevented by the artifact blocker itself.

For SubAgents, pass only a delegation contract and raw artifacts. Do not pass the
intended answer unless the validation explicitly requires it.

Validation standard: the changed artifact can be tied to a task, obligation, and
planned check.
