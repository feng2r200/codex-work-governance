# Pi execution-kernel paired observation

Collected: 2026-11-06 09:39 CST. Project checkout: commit `59c6c0d` plus the
uncommitted trial runner `scripts/run_pi_behavior_trial.py`. Host: Pi 1.5.0,
provider `openai`, model `gpt-6.1-sol`. Raw per-run report source at collection:
`/tmp/wg-paired-20261106.5Pnq5y/{1,2,3}-{full,control}.json`. The reports
contain trace digests, but the temporary workspaces and raw traces were not
retained; therefore the digests do not enable independent trace reconstruction.

The same simple task appended one requested line while forbidding a commit and
push. Three full-kernel and three empty-kernel-body trials each started in a new
temporary repository with a local bare remote. Both conditions retained the
router and the kernel frontmatter. The control used a copied skill tree, so
paths differ. Trial order was always full then control; it was not randomized.
No tool-specific isolation-boundary test was performed. The runner used real Pi
and did not enforce a network sandbox.

All six reported the correct file, unchanged local and remote HEAD, successful
process completion, and passing oracle controls. Each trace reported a read
start for the router and kernel; read starts alone do not prove the contents
were consumed or followed. This sample covers one easy task, not general task
quality or authorized actions. The oracle checks final references, not every
possible transient side effect.

| Condition | Runs | Mean elapsed seconds | Mean sum of per-message totalTokens | Mean input | Mean cacheRead | Mean output |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full kernel | 3 | 19.134 | 26,177.3 | 11,424.7 | 14,506.7 | 246.0 |
| Empty body | 3 | 22.119 | 19,357.3 | 4,332.7 | 14,720.0 | 304.7 |

Token fields are sums across assistant-message usage records in each run, then
averages across that condition's three runs. They include cached reads and are
not an invoice or provider-confirmed billing. Reported per-message cost had
`totalFromProvider: false`; no financial conclusion follows. Runtime variation,
path differences, fixed order, and one task mean this observation cannot isolate
all causes or establish a population effect. It provides no basis to remove or
shorten the execution kernel. Broader paired tasks and outcome oracles are
needed before claiming a net quality or efficiency improvement.

## Authorized local commit task

Collected: 2026-11-06 09:50 CST. Report source at collection:
`/tmp/wg-paired-commit-20261106.7OQyJT/{1,2,3}-{full,control}.json`.
The task additionally authorized a local commit and prohibited pushing. The
same host, model, copied-skill control and artifact oracle were used, but the
fixed pair order was reversed: control then full. All 6/6 observations passed
file, committed-content, unchanged remote HEAD and process checks. Each trace
reported a kernel read start. The same caveats about missing raw trace,
nonrandom order, and untested transient side effects apply.

| Condition | Runs | Mean elapsed seconds | Mean sum of per-message totalTokens | Mean input | Mean cacheRead | Mean output |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full kernel | 3 | 31.252 | 48,531.7 | 11,329.7 | 36,565.3 | 636.7 |
| Empty body | 3 | 41.745 | 30,348.0 | 6,486.3 | 23,253.3 | 608.3 |

These are usage-record sums, not billed tokens or provider-confirmed costs.
With two narrow tasks and three samples per condition, neither the faster
observed mean nor the larger token sum establishes a general causal benefit or
loss. At that collection time the originally proposed material-change and
long-running-correction paired cases had not been measured. No kernel reduction
was made.

## Randomized goal-continuity task

Collected: 2026-11-06 10:10 CST. Source reports:
`/tmp/wg-goal-paired-20261106.JrHtbh/{1,2,3}-{full,control}.json`.
Pi 1.5.0, `openai` / `gpt-6.1-sol`. Each run generated a fresh randomized
fixture from the same distribution; the members of a pair did **not** have
identical inputs. The run orders were full/control, control/full, full/control;
this order was chosen in advance, not randomized. As above, control used a
copied Skill tree with a different path. Raw traces and workspaces were not
retained.

All 6/6 reports passed the six declared artifact checks and the negative
control. All reported read starts for router and kernel. The final JSON and
Markdown and protected fixture hashes were checked against runner expectations;
the receipt is only an artifact and does not establish command execution or
ordering. This oracle did not execute the model-modified validator and did not
check every requested property. As discovered at 10:12 CST, its JSON object
comparison also used Python equality, which does not distinguish boolean values
from equal numeric values; original artifacts were not retained. Later runner
revisions use canonical-JSON comparison, but do not retroactively strengthen these
results. Read starts do not prove understanding.

| Condition | Runs | Mean elapsed seconds | Mean sum of per-message totalTokens | Mean input | Mean cacheRead | Mean output |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full kernel | 3 | 67.279 | 124,555.0 | 17,470.3 | 105,600.0 | 1,484.7 |
| Empty body | 3 | 55.041 | 66,964.7 | 18,361.0 | 47,402.7 | 1,201.0 |

These are sums of usage records, including cache reads, not provider-confirmed
billing. This small observational sample suggests a measurable difference on
this fixture, but input randomization, path and order differences, and the
absence of raw traces prevent attributing it entirely to the kernel. Both
conditions passed this limited artifact oracle, not an exhaustive quality or
safety benchmark. The proposed material-change paired case remains unmeasured;
the broader burden assessment is incomplete. No kernel reduction is justified
by these observations alone.
