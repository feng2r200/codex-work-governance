# L5 Deviation and Rollback

Enter L5 when evidence shows the route, output, scope, dependency, or artifact
state may no longer serve the goal.

Immediate actions:

- stop downstream execution;
- mark affected artifacts `suspect`;
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

Validation standard: no suspect, quarantined, or rollback-pending artifact
remains before final completion.
