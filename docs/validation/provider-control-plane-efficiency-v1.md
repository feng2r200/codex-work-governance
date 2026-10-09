# Provider Control-Plane Efficiency Synchronization Evidence

Status: Remote source delivery and installed-plugin adoption complete
Date: 2026-10-07

## Why this policy changed

The prior provider-state efficiency contract already separated logical-project
ownership from state isolation, reused one bounded provider snapshot until a
real invalidation trigger, and accepted a precise mutation receipt plus exact
target readback instead of another broad recovery read.

The installed provider now also exposes a composite read-only health surface
and precise control-plane issue classes. Without a matching generic policy,
an Agent could still repeat equivalent route, binding, activation, capability,
and integrity status reads or misreport every missing capability as a broken
provider.

## Synchronized contract

- Prefer one provider-native aggregate health or readiness snapshot when it
  proves the required control-plane obligations.
- Expand to focused status only for a reported gap, a claim outside the
  aggregate's coverage, or an exact fresh guard required by an authorized
  mutation.
- Treat a cleanly inactive route or missing capability as degraded only for
  the named operation. Preserve the missing authority and continue independent
  work when safe.
- Treat stale, malformed, ambiguous, or integrity-failed control state as
  blocked for the affected provider path. Fail closed on dependent claims and
  writes while safe unrelated work continues.
- Neither class authorizes activation, repair, migration, or another
  control-plane mutation.

The public plugin remains tool-neutral. It adds no provider command, state
engine, hook, fallback ledger, or automatic repair.

## Controlled semantic cases

| Case | Required behavior | Guard retained |
| --- | --- | --- |
| Aggregate health covers route, binding, isolation, capability, and integrity | Reuse the single snapshot | No repeated equivalent status calls |
| Aggregate reports a bounded gap | Open only the affected focused status | Unrelated evidence remains reusable |
| A claim falls outside aggregate coverage | Obtain evidence for that claim only | Healthy is not treated as universal proof |
| An authorized mutation requires an exact fresh guard | Refresh only that guard immediately before mutation | Readiness does not grant mutation authority |
| Route is cleanly inactive or capability is absent | Mark only the named operation degraded | No implicit activation or repair |
| Control state is stale, malformed, ambiguous, or integrity-failed | Block the affected provider path | No unsafe read, write, or completion claim |

## Validation

- All 22 policy-contract tests pass.
- Ruff lint and format checks pass.
- All ten packaged Skills pass the bundled Skill structural validator.
- The formal Codex local marketplace installation accepts the plugin manifest.
- Tool-neutrality checks confirm that the public plugin contains no provider
  command name, state engine, or lifecycle hook.
- Both plugin manifests report version `2.0.0+codex.20261007080310`.
- The source and installed plugin each contain 23 files and have identical
  aggregate tree SHA-256
  `ccfcc90b9be46436b895e11c80ad05f28208f937e6cc736d7fc26df9c7c24f63`.

Manifest alignment remains covered by the policy-contract suite, and the
formal plugin manager accepted, installed, enabled, and read back the
candidate.

## Remote delivery

Source commit `5fae19d18ceb6c776229b3407510f4665b76762a` was delivered
to `origin/main` by ordinary fast-forward Push. Post-Push readback confirmed
that local `HEAD`, the tracking ref, and remote `refs/heads/main` all resolved
to that exact commit.

GitHub Actions [CI run 37600634326](https://github.com/feng2r200/codex-work-governance/actions/runs/37600634326)
completed successfully for the exact source commit. Its `policy-contracts` job
passed lint, format checking, and the policy-contract test suite.

## Installed adoption and rollback boundary

The enabled local installation is
`work-governance@work-governance-local`, version
`2.0.0+codex.20261007080310`, under
`/Users/ld/.codex/plugins/cache/work-governance-local/work-governance/`.
The plugin manager replaced the previous cache version rather than retaining
it. The clean pre-change Git revision
`7903a1b701ef9e4bc41951732056a98d5fbe2a23` remains the rollback source; any
rollback would be a separate explicit operation and must be reinstalled and
verified through the formal marketplace path.

Already-running Codex tasks retain the Skill snapshot loaded when they began.
New tasks load the installed version above.

## Boundaries

This synchronization changes source policy and the local installed plugin. The
source commit was pushed and its exact CI succeeded. It does not create a tag
or release, deploy, modify the provider registry or activation markers, or
weaken provider integrity checks.
