# L3 Execution

Execute only the next authorized slice.

Before edits:

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

For SubAgents, pass only a delegation contract and raw artifacts. Do not pass the
intended answer unless the validation explicitly requires it.

Validation standard: the changed artifact can be tied to a task, obligation, and
planned check.
