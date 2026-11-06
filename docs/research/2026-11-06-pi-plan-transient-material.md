# Pi Plan, transient reference and material-change trials

Collected 2026-11-06 10:38–11:12 CST. Source checkout: `66025fe` plus
uncommitted trial changes. Pi 1.5.0, model `openai` / `gpt-6.1-sol`;
WorkVCS stable 3.0.2, build `869b344c9e94de68ce327210a75598cea3f0c485`.
All probes used temporary Stores and Git repositories, normal user tools and
network capability, and were not security sandboxes.

## Plan creation and cross-process recovery

Reports: `/tmp/wg-real-plan-20261106.json` and
`/tmp/wg-real-plan-readback-20261106.json`. Two separate trials each invoked
two independent ephemeral Pi processes. The first was explicitly instructed to
create an active Plan in an explicit standalone temporary WorkVCS Store. The
runner read the actual Plan via the installed WorkVCS CLI. The second process
received the Store and branch but not the random next-action value, read the
Plan, and wrote that value as its result. Both reports passed entity identity,
status, strategy, result and process checks. The second report retains the
native fields and actual result. Tool call records show the create and list
commands. The initial empty-Plan fixture and malformed-input unit cases were
controls.

This is two observations of an explicitly instructed Store workflow, not a
measurement of spontaneous Plan admission, a WorkVCS project journal route,
Plan revision or context-compaction recovery. The raw Pi traces and temporary
Stores were not retained, and tool-call starts are not command-output records.
The report includes native Plan readback and output bytes; none proves isolation
from all other possible sources of the marker.

## Transient remote reference events

Report directory: `/tmp/wg-transient-20261106.ieYYg2/`. A kqueue vnode watch
covered only the `refs/heads` directory of a temporary bare Git remote. An
immediate create/delete control in that same directory was detected for each
run. In the authorized-push run an event was detected and the remote ref
matched the new local commit; in the no-commit/no-push run no event was
reported and final refs remained at baseline. A separate deterministic unit
control actually pushed a new commit and restored the original remote ref:
the final ref matched baseline while the observer detected the transient
reference directory change.

The observer can coalesce events; it is neither a syscall trace nor an event
count, does not identify the actor or exact write, and does not cover local Git
references, other paths, network, or effects outside this directory. Absence of
a notification is only a bounded observation and is not a global no-side-effect
claim. `/usr/bin/fs_usage` reported that root was required; no elevated tracing
was attempted. The raw transient notification flags for the Pi runs remain in
the JSON reports, which are temporary.

## Material-code campaign: rejected initial attempts

The initial campaign reports are in `/tmp/wg-material-paired-20261106.cXlo1C/`.
The first full/control pair each reported 12/12 fixed-vector checks and oracle
controls passing, with 69.465/63.868 seconds and 64,252/42,951 sums of
per-message totalTokens respectively. The full implementation was not retained;
the control implementation is in its report. The following four invocations
failed with `NameError: EXPECTED_CHECKS is not defined`: the trial oracle was edited
while that campaign was starting new processes. The batch is not a complete
three-pair result and is not included in a three-pair mean.

The next campaign `/tmp/wg-material-frozen-20261106.wDqGRz/` produced one
passing full sample (67.840 seconds, 63,576 usage-sum tokens). Its first
control output is empty because the outer monitor's 300-second inactivity
limit stopped the command before the inner timeout produced a report. No
cause or model outcome can be inferred for that run; the batch is incomplete.
The harness was changed to report Pi subprocess timeouts and retain parsable
partial calls, with a deterministic timeout test; a subsequent campaign uses
an outer monitor without an inactivity limit. Existing old results do not
become stronger retroactively.

## Material-code campaign: completed rerun

Collected 2026-11-06 11:09 CST. Report directory:
`/tmp/wg-material-fixed-20261106.kfkahF/`. The same starter source, task and
fixed-vector oracle were used in each fresh temporary workspace. Each JSON report
retains the generated Python source, checks, control results, tool call starts,
per-message usage and elapsed time. The listed trial scripts, `pyproject.toml`
and `uv.lock` had identical SHA-256 digests before and after the campaign. The
orders were full/control, control/full, full/control; order was predetermined,
not randomized. The control loaded the copied Skill tree at different paths.

All six runs completed without timeout and passed the original 12/12 vectors.
Each adjacent known-good implementation passed and the starter failed; both
conditions recorded router and kernel read starts. Review then identified that
although the specification excluded boolean unit prices, the original oracle
only tested boolean quantities. At 11:12 CST the oracle was corrected, a
negative control added, and the six **retained implementations** were regraded
against all 13 checks; 6/6 passed. Source:
`/tmp/wg-material-fixed-20261106.kfkahF/regrade-13.json`. This regrade tests the
retained code, not a new model run. The old 12-vector measurements remain
unchanged historical observations.

| Condition | Runs | Passing original / regrade | Mean seconds | Mean usage-sum totalTokens | Mean input | Mean cacheRead | Mean output |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full kernel | 3 | 3 / 3 | 75.519 | 74,769.7 | 21,343.3 | 51,114.7 | 2,311.7 |
| Empty body | 3 | 3 / 3 | 61.967 | 38,681.0 | 13,414.0 | 23,125.3 | 2,141.7 |

All token figures in this document sum per-message usage fields and are not
provider-confirmed bills. The repeated task, fixed nonrandom order, different
paths, small sample, and missing complete raw traces prevent attribution of the
observed difference solely to the kernel or extrapolation to other tasks.
The failed initial attempts above are reported separately and are not hidden
inside the completed rerun's means. No universal quality, efficiency, or safety
claim is supported; the observation does not independently justify removing or
shortening the kernel.
