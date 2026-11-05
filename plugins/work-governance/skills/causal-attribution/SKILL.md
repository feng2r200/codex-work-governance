---
name: causal-attribution
description: Use when an observed symptom in an existing system needs a trustworthy cause before changing anything, including cost or performance blowups, a capability that silently never activates, a channel that appears to carry nothing, or a suspicion that some component is to blame. Applies whenever acting on the wrong cause would be expensive or hard to reverse.
---

# Causal Attribution

Establish what actually causes an observed symptom in a system that already
runs, so a fix changes the real driver. This Skill owns how a suspicion becomes
a measured, falsifiable, and confirmed cause, and when a plan built on a fallen
premise must be rebuilt. It does not own forward test design, product intent,
action authority, persistence, or reporting.

Use it with `work-governance:problem-discovery` when the work also needs a
strategy for exposing future defects. Discovery designs challenges for behavior
that has not failed yet; attribution explains a failure already in hand.

## Separate The Symptom From The Suspected Cause

Write the symptom as an observable with a magnitude, and write each candidate
cause as a separate claim. "Cost is too high" is a symptom. "The delegation
feature causes it" is a claim that must survive measurement on its own.

Carry every candidate offered by the requester, by prior records, and by your
own first impression as an equal claim. The person reporting a symptom usually
also reports a suspected cause, and that suspicion is evidence about where to
look rather than a finding. Treat a confident framing exactly like an unproven
one until it is measured.

Keep a claim distinct from the remedy it implies. Removing a capability,
rewriting a module, and tightening a limit are decisions that require a
confirmed cause, not reasonable responses to a plausible one.

## Measure Before Attributing

Attribute only against a total. A component's share is meaningless until the
whole is counted on one aligned definition, so establish the denominator first,
then place each candidate inside it.

State the measurement basis explicitly: the exact field or record consulted, the
population, the time window, and the unit. Two numbers may only be compared or
summed when they share all four. Record the extraction command alongside the
result so the number can be recomputed rather than retold.

Prefer a full population over a sample when the data is already durable. Logs,
session records, and stores usually permit an exact count, and an exact count
removes an entire class of dispute.

Report shares, not only magnitudes. A component responsible for under a few
percent cannot explain a symptom measured in multiples, regardless of how
unattractive that component is on other grounds.

Build every ratio from a denominator that the numerator genuinely belongs to.
Events that fire at different natural frequencies do not share a denominator:
dividing an occasional event by a population dominated by a frequent one
manufactures an anomaly that does not exist. Before reporting a rate as low,
state what a complete count would have been and confirm that the denominator
measures opportunities for exactly that event.

## Expect Suspicions To Fail

Most initial attributions are wrong, including your own. A measurement that
retires a candidate is a successful measurement and should be recorded as a
finding rather than discarded as a dead end.

Retire a candidate explicitly and keep the retirement durable with its
evidence. An unrecorded refutation returns as the same suspicion later, and the
same measurement gets paid for twice.

When every named candidate is retired, the real driver is a factor nobody
proposed. Look at per-unit overheads, repetition counts, fixed prefixes,
retained-but-unused material, and anything that scales with turns or invocations
rather than with features. Decompose the total along a dimension that nobody has
examined yet instead of re-examining the retired candidates more carefully.

## Treat A Structural Zero As Decisive

A counter that should be nonzero and is exactly zero across an entire window is
strong negative evidence, not missing data. A channel with no writes, a field
never populated, a subcommand never invoked, and a generated artifact that is
always empty each indicate an absent path rather than a rare one.

Distinguish three readings of a zero and resolve which one holds:

- nothing ever wrote to it, so there is no producer;
- something wrote and the consumer rejected or ignored it; and
- the observation itself never reached the place where writes occur.

These demand different repairs, and the next section separates them.

## Prove The Apparatus Before Trusting A Negative

A negative result is only informative when the measuring arrangement is known
to work. Before concluding that a path is broken, drive it end to end by hand
with a value that cannot arise by chance, and confirm that value appears at the
destination.

Pair the negative with a positive control that differs in one condition. When a
hook, handler, or integration appears inert, first show that an equivalent one
fires in the same environment. That single comparison separates "implemented
incorrectly" from "never invoked", which no amount of code reading resolves.

Add an independent liveness probe to the subject under test. A side effect that
records invocation, such as an appended file written before any other work,
distinguishes "ran and produced nothing useful" from "never ran". Without it, a
silent no-op and an unregistered component look identical.

Guard against the apparatus supplying the answer. When probing whether a value
reaches a consumer, ensure the consumer cannot obtain that value by another
route; an agent that can read the probe's own definition will appear to confirm
a channel that never delivered anything. Isolate the environment, remove
incidental access, and re-run.

Hold a control at the same scope as the thing it controls for. Validation
strictness is rarely uniform across a system: one section may reject every
unrecognised entry while its neighbour accepts anything, so a control placed in
the neighbouring section reports a false verdict about the probe itself. When a
control says the instrument cannot discriminate, suspect the control's
placement before abandoning the instrument, and re-site it in the exact
section, shape, and value type under test.

## Consult The Authoritative Contract

When behavior depends on an interface, read the contract the implementation
actually enforces rather than its documentation or its usual shape. Embedded
schemas, generated descriptors, type definitions, and validation code state
what is accepted; prose states what someone intended.

A silently discarded input is the common failure. An interface that rejects
unknown fields will often drop a well-formed value for an event that does not
declare it, producing no error anywhere. When something is sent but never
observed downstream, confirm that the receiving side declares the field at all
before investigating the sender further.

Enumerate the full set of variants when one variant disappoints. The capability
missing from one event is frequently present on a neighboring one, and that
neighbor is the repair.

## Separate Provisioning Cost From Use

Advertised and consumed are different quantities. Material can be installed,
injected, catalogued, or announced without ever being invoked, and each side has
its own cost and its own remedy.

Count them separately and name which one a finding refers to. The largest
avoidable cost is frequently something carried on every unit of work and used
on almost none, which neither a usage ranking nor a feature review will surface.

A component that is never used may be failing to activate rather than lacking
value. Check whether its activation condition was ever met in the observed
window before concluding it is unnecessary; a condition that was met and did not
activate indicts the detection, and removal would discard a working capability
and keep the defect.

## Follow The Cost To Where The Work Ran

A mechanism that hands work off carries almost none of that work's cost in its
own return value. Delegation, task submission, background execution, and
scheduling all answer with a short handle, so measuring the handle measures the
gesture rather than the labour. Charge each execution body to the mechanism that
created it, and report the dispatch overhead and the dispatched cost as two
named quantities.

Where the cost lands also determines where evidence lands. Work that runs in its
own transcript, process, or log is absent from the parent record, so a ranking
built only on the parent sees a rounding error and concludes the mechanism is
innocent. Enumerate the children first, then aggregate across them on the
billed or measured unit that the budget is actually spent in.

A detached execution body also loses the constraints that were never written
into its brief. Check what instructions reached it and what survived its own
context handling, because an executor that retains the task but not the limits
produces fluent, expensive, unsupervised output that no participant observes.

## Confirm The Mechanism, Not Only The Correlation

A quantified share locates a driver; it does not explain it. Carry attribution
through to the specific mechanism, then check that the mechanism predicts the
other observations already in hand.

A complete account states the trigger, the path, and why the symptom has the
magnitude observed. When two systems differ, compare the per-unit figure and the
unit count separately, since a large aggregate difference is often a product of
two moderate ones and only the decomposition identifies which to address.

Verify the account against evidence it was not derived from. An explanation that
also accounts for an unrelated anomaly, a timing boundary, or a count that was
previously unexplained is substantially stronger than one fitted to a single
observation.

## Rebuild A Plan Whose Premise Has Fallen

When evidence invalidates a premise, withdraw the dependent decisions rather
than attaching a fallback to them. A remedy built on a refuted mechanism
produces another inert path, and the next investigation pays to discover it.

Say plainly which prior conclusion is withdrawn and why. Carry the correction
into the record with the same prominence as the original claim, including your
own earlier recommendations.

Re-derive the remedy from the confirmed mechanism. When a capability is
unavailable where it was assumed, the replacement is usually a different
division of responsibility across available facilities rather than a
reconstruction of the unavailable one.

A premise that falls in the convenient direction is still a fallen premise.
Evidence that the cost, blast radius, or difficulty is far smaller than the
attribution assumed invalidates that estimate exactly as a larger one would,
and an estimate that decided against a route deserves the same scrutiny as one
that decided for it. Withdraw the superseded figure in the record instead of
quietly proceeding because the news was good. For how a proposed route states
and checks its cost and benefit before execution, follow
`work-governance:work-lifecycle`.

## Change The Evidence Route Early When A Tool Misbehaves

When a tool corrupts, truncates, or misrepresents evidence, switch to a
different route on the second occurrence. Repeated attempts through a channel
that has already failed twice consume effort and contaminate results.

Record the failing route and the working substitute with the investigation, so
the same obstacle is paid for once.

## Record The Attribution So It Survives

A durable attribution carries the symptom with its magnitude, the measurement
measurement basis, each candidate with its measured share and verdict, the confirmed
mechanism, the controls that make the negatives trustworthy, and the commands
that reproduce the numbers.

Record refutations beside confirmations. The retired candidates are what keep a
later reader from reopening settled questions, and they are usually the larger
part of the value.

Mark every remaining unknown as unknown. An investigation that resolves most of
its questions and says so is usable; one that smooths over a gap invites a
decision the evidence does not support.

State that reality outranks the record. A later executor who finds the system
behaving differently should re-derive the cause and amend the record, because
these findings describe a system at a moment rather than a fixed truth.

A compact attribution can be expressed as:

| Symptom and magnitude | Candidate | Measurement basis | Measured share | Verdict | Control | Reproduce |
| --- | --- | --- | --- | --- | --- | --- |

The attribution is complete enough when the confirmed mechanism explains the
symptom's magnitude, every proposed candidate has an explicit verdict, each
decisive negative rests on a positive control, and the remaining unknowns are
visible rather than resolved by assumption.
