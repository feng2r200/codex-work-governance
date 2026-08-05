# L5 Deviation and Rollback

Enter L5 when evidence shows the route, output, scope, dependency, or artifact
state may no longer serve the goal.

An inserted request or between-slice audit is not automatically a deviation.
First apply the L0 goal-alignment classifier: unrelated bounded work uses a
resumable No-Plan interruption, aligned priority changes stay in the current
Plan, and only an aligned material contract change enters Plan adaptation or
revision.

Do not enter L5 merely because an implementation attempt failed, a local fact
is unknown, or more evidence is needed. Those are Agent-owned diagnosis and
exploration unless they prove a material change to goal, scope, behavior,
cost, safety, or delivery shape.

Keep deviation evidence runtime-scoped until it proves a material contract
change. A weak-link suspicion, stale artifact suspicion, review note, or
between-slice audit finding may freeze only the affected downstream targets
while the agent checks the deciding evidence. Do not create a separate
deviation log, Plan revision, or contract churn for every observation.

Immediate actions:

- stop downstream execution;
- mark affected artifacts `suspect`, including artifacts previously marked
  final;
- preserve evidence of the deviation;
- identify the first unsupported assumption or failed gate;
- decide whether the issue is local execution, Plan structure, scope, or bottom
  goal mismatch.

Also enter L5 with reason `INEFFECTIVE_LOOP_DETECTED` after two consecutive
attempts show no material evidence delta or target progress. Preserve the
attempt tuples and stop adding retries or tests until a changed hypothesis can
produce discriminating evidence. Explicit monitoring or wait requests are not
loops merely because the observed state is unchanged.

Enter L5 immediately with reason `QUALITY_DRIFT_DETECTED` when a repeated-work
checkpoint diverges from its confirmed pilot invariant. Freeze dependent
downstream batches, preserve the first divergent and last accepted evidence,
and do not continue amplifying the deviation. Bulk authorization supplies no
override; recovery still requires a discriminating cause, a bounded repair
slice, and the applicable confirmation.

Before proposing a recovery, write a root-cause challenge:

- exact symptom and boundary where it was observed;
- falsifiable cause hypothesis and causal chain;
- evidence supporting and contradicting the hypothesis;
- cheapest safe discriminating probe;
- whether each candidate solution removes the cause, contains impact, or hides
  the symptom;
- materially plausible minimal containment, causal correction, and alternate
  route, compared for truth proximity, reversibility, and risk.

Do not resume because a test passes if the causal boundary has not been
observed. If the root cause remains unknown, label it unknown and select the
next discriminating probe rather than presenting a workaround as a fix.

High-impact recovery choices require confirmation:

- destructive rollback;
- quarantine or deletion of artifacts;
- compensating data changes;
- scope revision;
- resuming from an older queue.

Bind that confirmation as `intervention.kind=deviation_recovery`, name the
exact blocked targets, use the immutable deviation evidence as `basis_ref` and
`basis_sha256`, and present the observed evidence, impact, and materially
distinct recovery options. If the correction stays within the confirmed
contract and is reversible, diagnose and apply it without asking the user.

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
