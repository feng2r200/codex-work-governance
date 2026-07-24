# L5 Deviation and Rollback

Enter L5 when evidence shows the route, output, scope, dependency, or artifact
state may no longer serve the goal.

Immediate actions:

- stop downstream execution;
- mark affected artifacts `suspect`, including artifacts previously marked
  final;
- preserve evidence of the deviation;
- identify the first unsupported assumption or failed gate;
- decide whether the issue is local execution, Plan structure, scope, or bottom
  goal mismatch.

High-impact recovery choices require confirmation:

- destructive rollback;
- quarantine or deletion of artifacts;
- compensating data changes;
- scope revision;
- resuming from an older queue.

After recovery:

- do not auto-run the old downstream queue;
- revise the Plan or create a fresh next slice;
- clear suspect state only after validation evidence exists.

Avoid recovery deadlocks: a task may work on a suspect artifact only when the
Plan explicitly names that artifact in the task's `resolves_artifacts`. The
artifact remains suspect until the planned validation proves the correction.
This recovery exception does not apply when any blocking artifact is
`quarantined` or `rollback-pending`.

Use the dedicated artifact state command. `pending` or `final` may move
immediately to `suspect` to fail safe. Quarantine and rollback-pending require
an accepted recovery confirmation, retain that confirmation ID, and must
return through `suspect` before an owning recovery task can finalize them.

Validation standard: no suspect, quarantined, or rollback-pending artifact
remains before final completion.
