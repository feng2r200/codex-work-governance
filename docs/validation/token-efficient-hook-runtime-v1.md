# Token-efficient Hook Runtime v1

Status: Accepted implementation contract
Date: 2026-10-13

## Observed baseline

The motivating live-chat snapshot contained 8,499 response records and
1,347,398,602 reported Tokens. Input accounted for 1,342,715,831
(99.6525%); 1,315,142,656 of those input Tokens were cached (97.9465% of
input). Output accounted for 4,682,771, including 1,842,661 reasoning Tokens;
cached input and reasoning are subsets and are not added again.

Operational classification attributed 948,767,898 Tokens (70.4148%) to
exec-only turns, 172,503,422 (12.8027%) to coordination, 99,874,609
(7.4124%) to poll-only turns across 631 responses, and 81,294,538 (6.0334%)
to UI-only turns. Responses carrying at least 150,000 input Tokens were
55.3595% of responses and 68.7869% of reported total usage. The source chat
was still live at the snapshot, so these values are an observed baseline, not
a terminal total or an acceptance threshold.

## Purpose and quality floor

This optional runtime removes avoidable model turns by carrying a small,
explicit active-context delta across SessionStart or PreCompact boundaries and
by recording deterministic tool-event metrics outside the prompt. It does not
lower model choice, reasoning, test coverage, Reviewer or Validator
independence, raw evidence retention, UI acceptance, or failure visibility.
Token reduction is an observation, never an acceptance gate.

The Plugin remains a governance policy package. The portable Agent Plugins
manifest declares `hooks/hooks.json` inside `extensions.com.openai`, while the
compatibility manifest declares that same path directly. A root-level portable
`hooks` field is deliberately forbidden because current Codex treats it as an
unknown Agent Plugins field. When host enumeration of the Plugin definition is
unavailable, the installer can explicitly and atomically merge that same Hook
definition into the supported user-level `$HOME/.codex/hooks.json` surface. It
preserves unrelated user Hooks and never uses a Plugin cache path. The Hook
runtime is not a semantic state engine and does not replace project authority
or the selected durable work-state provider.

## Stable execution contract

Every shipped Hook command has exactly four authorities: the stable absolute
user-level launcher, `wg-hook-v1`, one immutable package SHA-256, and one named
handler. The user-level configuration file only declares those exact commands;
it never becomes an executable package source. A command contains no Plugin
cache path, `latest`/`current` selector, CWD lookup, PATH lookup, or PYTHONPATH
import.

The package lives at
`$HOME/.local/libexec/work-governance/<manifest-sha256>/`. On every call the
launcher rejects symlinks, foreign ownership, group/other-writable parents,
non-private package members, unexpected tree members, incompatible manifests,
and file-digest mismatch. It executes the already verified runtime bytes rather
than reopening an unverified path.

## Output and state bounds

- Hook input is bounded at 256 KiB; explicit context is bounded at 6,000
  characters and an 8 KiB packet.
- Transcript bodies and tool inputs/outputs are never persisted.
- PostToolUse produces no model output. SessionStart and PreCompact emit only a
  changed explicitly staged packet, once per handler and session digest.
- Private packet and emission state expires after seven days. The observation
  file rotates at a fixed byte bound and records only handler, hashed session,
  small event/tool names, timestamps, and local latency.
- Empty output is the normal success result. Malformed input, integrity faults,
  timeouts, nonzero exits, disabled Hooks, untrusted or changed Hook hashes, and
  unsupported environments remain visible as unknown or degraded; none may be
  reported as successful adoption.

Exact Token contribution is read from Codex telemetry when available. Runtime
byte counts and latency are supporting measurements and are never relabeled as
exact Token counts.

## Upgrade and rollback

Upgrade is two-stage and fail-closed:

1. install and read back the candidate immutable package;
2. replace the minimal stable launcher and probe both the old pinned package
   and the candidate package, naming the old package explicitly as the rollback
   digest;
3. exercise a real event through the old trusted Hook;
4. install the new Plugin definition and atomically update only the managed
   definitions in the user-level Hook configuration;
5. trust only its exact Hook hash in Codex;
6. exercise and read back the new real event.

Any failure stops adoption and retains the old package. Launcher rollback is
part of the installer transaction: it restores the previous launcher and then
internally re-probes the explicitly named old package. A failed candidate probe,
failed byte restoration, and failed rollback probe remain distinct errors.
Plugin/Hook rollback likewise restores the previous definition before a real
old-package event is re-exercised.
An old package may be removed only by exact manifest digest after proving no
Hook reference and no live process uses it. Ambiguity means retention.

## Validation matrix

The focused suite covers no-change and changed-delta behavior, payload
exclusion, package tampering, symlink substitution, permissive modes, partial
packages, and old-plus-new launcher probes. Release validation additionally
checks foreign ownership where the host permits it, concurrent installation,
PATH/PYTHONPATH/CWD injection, malformed and oversized input, runtime timeout,
Hook disabled/untrusted/hash-changed behavior, exact package and plugin
readback, and real SessionStart, PreCompact, and PostToolUse events.

## 2026-10-13 Plugin-only adoption result

Implementation and package adoption are separate. The immutable package
`c809a614107c874e512c2bc828634d6c316d4186364d64620efe88658dba79af`
and stable `$HOME/.local/bin/work-governance-hook` were installed, read back,
and probed successfully. Plugin version 2.5.1 was also installed from the
candidate checkout with byte-identical Hook configuration.

Hook adoption is nevertheless **blocked/degraded**, not successful. Codex CLI
0.161.0 and the desktop-bundled 0.162.0-alpha.17.2 both reported `Installed 0`
for every `/hooks` event. SessionStart probes with trust bypass produced no
runtime observation. An isolated compatibility-manifest-only probe did produce
one SessionStart observation, confirming that the stable runtime and Hook
definition work while the portable-plugin loader path does not. This matches
the open upstream loader defect
[openai/codex#47925](https://github.com/openai/codex/issues/47925).

No Hook hash was marked trusted, no global user Hook file was installed, and no
companion plugin remains installed. This is historical Plugin-only evidence;
it does not authorize a trust bypass or prove user-level adoption.

## 2026-10-13 user-level adoption route

The user explicitly approved the supported user-level configuration route after
the Plugin-only loader observation. Version 2.6.0 adds `user-hook install` and
`user-hook status`, and `user-hook rollback`. Install first verifies the
installed immutable package and stable launcher, then merges the exact three
commands into `$HOME/.codex/hooks.json` under an owner-private lock. It preserves
non-Work-Governance handlers, replaces only prior syntactically exact
Work-Governance commands, writes and reads back canonical bytes atomically, and
restores the prior bytes if the installer’s own readback fails. Its private
rollback receipt stores the candidate and prior managed definitions, prior
package digests, and prior configuration presence; rollback requires that the
candidate managed definition is unchanged, verifies the old immutable package(s),
and retains intervening unrelated user Hook changes. Repeating an already-active
candidate does not replace a matching receipt, so its original rollback target
remains intact. The status result compares the exact managed substructure, including
event, matcher, handler, and multiplicity, and deliberately reports
`requires_codex_review`; only a fresh `/hooks` review, trust, and observed real
SessionStart, PreCompact, and PostToolUse events establish active adoption.
