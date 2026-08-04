# Work Governance CLI reference

> Generated from `plugins/work-governance/scripts/workctl.py` by `generate_cli_reference.py`; edit the parser, not this file.

## Invocation contract

Use the exact receipt-bound controller emitted by SessionStart. The placeholder below is intentional:

```sh
<receipt-bound-workctl> <domain> <command> [options]
```

Mutable schema-v4 Plan commands and high-impact authorization require the current turn receipt. Ordinary schema-v5 runtime commands use the expected state guard without turn intake. `plan status`, `plan show`, queue views, `help`, and `migrate inspect` are read-only views.

## Stable workflow aliases

### `action`

- `action authorize`
- `action consume`
- `action status`

High-impact authority is current-turn, target, digest, expiry, and single-consumption bound.

### `evidence`

- `evidence capture --task T-001 --kind command-output --summary TEXT`
- `evidence record --stdin`
- `plan evidence record --manifest PATH|--stdin`

Direct capture writes redacted blobs and an append-only ledger; Plan evidence records remain the bounded canonical compatibility path.

### `gate`

- `gate list`
- `gate check --gate-id C-001`
- `gate open`
- `gate satisfy`
- `gate waive`

Gate writes are aliases over strict Plan confirmation transactions.

### `migration`

- `migrate inspect`
- `migrate apply`
- `migrate recover`

Migration is explicit, backed up, and recovery-bound.

### `plan`

- `goal show`
- `plan create`
- `plan show [--full]`
- `plan edit`
- `plan reorder`
- `plan status`
- `plan ready`
- `plan next`
- `plan blocked`
- `plan activation-repair`

Contract edits require their existing confirmation and revision guards.

### `review`

- `review status`
- `review request`
- `review attach --manifest PATH`

Review attachment uses the independent-review recorder and its trust rules.

### `task`

- `task start`
- `task block`
- `task unblock`
- `task verify [--evidence-stdin]`
- `task reprioritize`

Schema-v5 runtime transitions use state_sequence and task gates without current-turn intake; mutable v4 transitions retain their turn binding.

### `truth`

- `truth list`
- `truth conflicts`
- `truth add --manifest PATH`

Truth writes are aliases over the confirmed contract revision path.

## Parser command reference

### `action authorize`

```text
usage: workctl action authorize [-h]
                                --action-kind {destructive_operation,production_change,remote_write,secret_handling,substantive_rollback}
                                --target-ref TARGET_REF
                                --action-sha256 ACTION_SHA256
                                --confirmation-id CONFIRMATION_ID --ref REF
                                --turn-receipt-sha256 TURN_RECEIPT_SHA256
                                [--ttl-seconds TTL_SECONDS]

options:
  -h, --help            show this help message and exit
  --action-kind {destructive_operation,production_change,remote_write,secret_handling,substantive_rollback}
  --target-ref TARGET_REF
  --action-sha256 ACTION_SHA256
  --confirmation-id CONFIRMATION_ID
  --ref REF
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --ttl-seconds TTL_SECONDS
```

### `action consume`

```text
usage: workctl action consume [-h] --authorization-id AUTHORIZATION_ID
                              --action-kind {destructive_operation,production_change,remote_write,secret_handling,substantive_rollback}
                              --target-ref TARGET_REF
                              --action-sha256 ACTION_SHA256
                              --turn-receipt-sha256 TURN_RECEIPT_SHA256
                              --consumer-ref CONSUMER_REF

options:
  -h, --help            show this help message and exit
  --authorization-id AUTHORIZATION_ID
  --action-kind {destructive_operation,production_change,remote_write,secret_handling,substantive_rollback}
  --target-ref TARGET_REF
  --action-sha256 ACTION_SHA256
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --consumer-ref CONSUMER_REF
```

### `action status`

```text
usage: workctl action status [-h] --authorization-id AUTHORIZATION_ID

options:
  -h, --help            show this help message and exit
  --authorization-id AUTHORIZATION_ID
```

### `evidence capture`

```text
usage: workctl evidence capture [-h] [--task TASK] --kind KIND
                                --summary SUMMARY [--from-file FROM_FILE]
                                [--stdin]
                                [--redaction-policy REDACTION_POLICY]
                                [--idempotency-key IDEMPOTENCY_KEY]
                                [--expected-state-sequence EXPECTED_STATE_SEQUENCE]

options:
  -h, --help            show this help message and exit
  --task TASK
  --kind KIND
  --summary SUMMARY
  --from-file FROM_FILE
  --stdin               Read evidence bytes from standard input; stdin is also
                        the default source.
  --redaction-policy REDACTION_POLICY
  --idempotency-key IDEMPOTENCY_KEY
  --expected-state-sequence EXPECTED_STATE_SEQUENCE
```

### `evidence record`

```text
usage: workctl evidence record [-h] (--manifest MANIFEST | --stdin)

options:
  -h, --help           show this help message and exit
  --manifest MANIFEST
  --stdin
```

### `gate check`

```text
usage: workctl gate check [-h] --gate-id GATE_ID

options:
  -h, --help         show this help message and exit
  --gate-id GATE_ID
```

### `gate list`

```text
usage: workctl gate list [-h]

options:
  -h, --help  show this help message and exit
```

### `gate open`

```text
usage: workctl gate open [-h] --confirmation-id CONFIRMATION_ID
                         --description DESCRIPTION
                         [--status {pending,accepted}] [--ref REF]
                         --intervention-kind {deviation_recovery,external_authority,plan_contract}
                         --blocks BLOCKS --basis-ref BASIS_REF
                         [--basis-sha256 BASIS_SHA256]
                         [--action-kind {destructive_operation,production_change,remote_write,secret_handling,substantive_rollback}]
                         --expected-revision EXPECTED_REVISION

options:
  -h, --help            show this help message and exit
  --confirmation-id CONFIRMATION_ID
  --description DESCRIPTION
  --status {pending,accepted}
  --ref REF
  --intervention-kind {deviation_recovery,external_authority,plan_contract}
  --blocks BLOCKS
  --basis-ref BASIS_REF
  --basis-sha256 BASIS_SHA256
  --action-kind {destructive_operation,production_change,remote_write,secret_handling,substantive_rollback}
  --expected-revision EXPECTED_REVISION
```

### `gate satisfy`

```text
usage: workctl gate satisfy [-h] --confirmation-id CONFIRMATION_ID --ref REF
                            [--evidence-sha256 EVIDENCE_SHA256]
                            --expected-revision EXPECTED_REVISION
                            [--turn-receipt-sha256 TURN_RECEIPT_SHA256]
                            [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]

options:
  -h, --help            show this help message and exit
  --confirmation-id CONFIRMATION_ID
  --ref REF
  --evidence-sha256 EVIDENCE_SHA256
  --expected-revision EXPECTED_REVISION
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
```

### `gate waive`

```text
usage: workctl gate waive [-h] --confirmation-id CONFIRMATION_ID --ref REF
                          [--evidence-sha256 EVIDENCE_SHA256]
                          --expected-revision EXPECTED_REVISION
                          [--turn-receipt-sha256 TURN_RECEIPT_SHA256]
                          [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]

options:
  -h, --help            show this help message and exit
  --confirmation-id CONFIRMATION_ID
  --ref REF
  --evidence-sha256 EVIDENCE_SHA256
  --expected-revision EXPECTED_REVISION
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
```

### `goal close`

```text
usage: workctl goal close [-h] --expected-revision EXPECTED_REVISION
                          [--evidence-manifest EVIDENCE_MANIFEST]
                          [--finalize-route] [--confirmation CONFIRMATION]
                          [--turn-receipt-sha256 TURN_RECEIPT_SHA256]
                          [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]

options:
  -h, --help            show this help message and exit
  --expected-revision EXPECTED_REVISION
  --evidence-manifest EVIDENCE_MANIFEST
  --finalize-route
  --confirmation CONFIRMATION
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
```

### `goal init`

```text
usage: workctl goal init [-h] --plan-id PLAN_ID --title TITLE
                         [--mode {autonomous,strict}]

options:
  -h, --help            show this help message and exit
  --plan-id PLAN_ID
  --title TITLE
  --mode {autonomous,strict}
```

### `goal revise`

```text
usage: workctl goal revise [-h] --manifest MANIFEST

options:
  -h, --help           show this help message and exit
  --manifest MANIFEST
```

### `goal show`

```text
usage: workctl goal show [-h]

options:
  -h, --help  show this help message and exit
```

### `help`

```text
usage: workctl help [-h]
                    [{plan,task,evidence,action,migration,goal,gate,truth,review}]

positional arguments:
  {plan,task,evidence,action,migration,goal,gate,truth,review}

options:
  -h, --help            show this help message and exit
```

### `intake receipt`

```text
usage: workctl intake receipt [-h] --turn-receipt-sha256 TURN_RECEIPT_SHA256
                              --classification {no_plan,plan_controlled}
                              --decision {proceed,explore,ask}
                              --rationale RATIONALE --targets TARGETS
                              [--current-unknown-id CURRENT_UNKNOWN_ID]
                              [--candidate-plan CANDIDATE_PLAN]

options:
  -h, --help            show this help message and exit
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --classification {no_plan,plan_controlled}
  --decision {proceed,explore,ask}
  --rationale RATIONALE
  --targets TARGETS
  --current-unknown-id CURRENT_UNKNOWN_ID
  --candidate-plan CANDIDATE_PLAN
```

### `intake status`

```text
usage: workctl intake status [-h]

options:
  -h, --help  show this help message and exit
```

### `layout adopt`

```text
usage: workctl layout adopt [-h]
                            --expected-manifest-sha256 EXPECTED_MANIFEST_SHA256
                            --expected-active-plan-id EXPECTED_ACTIVE_PLAN_ID
                            --ref REF

options:
  -h, --help            show this help message and exit
  --expected-manifest-sha256 EXPECTED_MANIFEST_SHA256
  --expected-active-plan-id EXPECTED_ACTIVE_PLAN_ID
  --ref REF
```

### `layout migrate`

```text
usage: workctl layout migrate [-h]

options:
  -h, --help  show this help message and exit
```

### `layout recover`

```text
usage: workctl layout recover [-h]

options:
  -h, --help  show this help message and exit
```

### `layout status`

```text
usage: workctl layout status [-h]

options:
  -h, --help  show this help message and exit
```

### `layout validate`

```text
usage: workctl layout validate [-h]

options:
  -h, --help  show this help message and exit
```

### `log append`

```text
usage: workctl log append [-h] --kind KIND --message MESSAGE
                          --expected-revision EXPECTED_REVISION

options:
  -h, --help            show this help message and exit
  --kind KIND
  --message MESSAGE
  --expected-revision EXPECTED_REVISION
```

### `migrate apply`

```text
usage: workctl migrate apply [-h] [--confirmation CONFIRMATION]
                             [--expected-contract-revision EXPECTED_CONTRACT_REVISION]
                             [--dry-run]

options:
  -h, --help            show this help message and exit
  --confirmation CONFIRMATION
  --expected-contract-revision EXPECTED_CONTRACT_REVISION
  --dry-run
```

### `migrate inspect`

```text
usage: workctl migrate inspect [-h]

options:
  -h, --help  show this help message and exit
```

### `migrate recover`

```text
usage: workctl migrate recover [-h] [--migration-id MIGRATION_ID]

options:
  -h, --help            show this help message and exit
  --migration-id MIGRATION_ID
```

### `plan activation-promote`

```text
usage: workctl plan activation-promote [-h] --state {in_progress,active}
                                       [--target-ref TARGET_REF]
                                       --confirmation CONFIRMATION
                                       [--evidence-manifest EVIDENCE_MANIFEST]
                                       [--evidence-ref EVIDENCE_REF]
                                       [--evidence-sha256 EVIDENCE_SHA256]
                                       --expected-revision EXPECTED_REVISION
                                       [--turn-receipt-sha256 TURN_RECEIPT_SHA256]
                                       [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]

options:
  -h, --help            show this help message and exit
  --state {in_progress,active}
  --target-ref TARGET_REF
  --confirmation CONFIRMATION
  --evidence-manifest EVIDENCE_MANIFEST
  --evidence-ref EVIDENCE_REF
  --evidence-sha256 EVIDENCE_SHA256
  --expected-revision EXPECTED_REVISION
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
```

### `plan activation-repair`

```text
usage: workctl plan activation-repair [-h] --task-id TASK_ID
                                      --target-ref TARGET_REF
                                      --confirmation CONFIRMATION
                                      --expected-revision EXPECTED_REVISION
                                      [--turn-receipt-sha256 TURN_RECEIPT_SHA256]
                                      [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]

options:
  -h, --help            show this help message and exit
  --task-id TASK_ID
  --target-ref TARGET_REF
  --confirmation CONFIRMATION
  --expected-revision EXPECTED_REVISION
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
```

### `plan adapt`

```text
usage: workctl plan adapt [-h] --manifest MANIFEST
                          [--turn-receipt-sha256 TURN_RECEIPT_SHA256]
                          [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]

options:
  -h, --help            show this help message and exit
  --manifest MANIFEST
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
```

### `plan admit apply`

```text
usage: workctl plan admit apply [-h] --manifest MANIFEST

options:
  -h, --help           show this help message and exit
  --manifest MANIFEST
```

### `plan admit recover`

```text
usage: workctl plan admit recover [-h] [--transaction-id TRANSACTION_ID]

options:
  -h, --help            show this help message and exit
  --transaction-id TRANSACTION_ID
```

### `plan artifact-state`

```text
usage: workctl plan artifact-state [-h] --artifact-id ARTIFACT_ID
                                   --state {suspect,quarantined,rollback-pending}
                                   [--confirmation CONFIRMATION]
                                   [--evidence-manifest EVIDENCE_MANIFEST]
                                   [--evidence-ref EVIDENCE_REF]
                                   [--evidence-sha256 EVIDENCE_SHA256]
                                   --expected-revision EXPECTED_REVISION

options:
  -h, --help            show this help message and exit
  --artifact-id ARTIFACT_ID
  --state {suspect,quarantined,rollback-pending}
  --confirmation CONFIRMATION
  --evidence-manifest EVIDENCE_MANIFEST
  --evidence-ref EVIDENCE_REF
  --evidence-sha256 EVIDENCE_SHA256
  --expected-revision EXPECTED_REVISION
```

### `plan authority check`

```text
usage: workctl plan authority check [-h] [--candidate CANDIDATE]

options:
  -h, --help            show this help message and exit
  --candidate CANDIDATE
                        Agent semantic input as PATH=CLASSIFICATION.
```

### `plan authority inspect`

```text
usage: workctl plan authority inspect [-h] [--candidate CANDIDATE]

options:
  -h, --help            show this help message and exit
  --candidate CANDIDATE
                        Agent semantic input as PATH=CLASSIFICATION.
```

### `plan blocked`

```text
usage: workctl plan blocked [-h]

options:
  -h, --help  show this help message and exit
```

### `plan closeout-check`

```text
usage: workctl plan closeout-check [-h]
                                   [--evidence-manifest EVIDENCE_MANIFEST]

options:
  -h, --help            show this help message and exit
  --evidence-manifest EVIDENCE_MANIFEST
```

### `plan complete`

```text
usage: workctl plan complete [-h] --expected-revision EXPECTED_REVISION
                             [--evidence-manifest EVIDENCE_MANIFEST]
                             [--finalize-route] [--confirmation CONFIRMATION]
                             [--turn-receipt-sha256 TURN_RECEIPT_SHA256]
                             [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]

options:
  -h, --help            show this help message and exit
  --expected-revision EXPECTED_REVISION
  --evidence-manifest EVIDENCE_MANIFEST
  --finalize-route
  --confirmation CONFIRMATION
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
```

### `plan confirm`

```text
usage: workctl plan confirm [-h] --confirmation-id CONFIRMATION_ID
                            [--decision {accepted,declined}] --ref REF
                            [--evidence-sha256 EVIDENCE_SHA256]
                            --expected-revision EXPECTED_REVISION
                            [--turn-receipt-sha256 TURN_RECEIPT_SHA256]
                            [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]

options:
  -h, --help            show this help message and exit
  --confirmation-id CONFIRMATION_ID
  --decision {accepted,declined}
  --ref REF
  --evidence-sha256 EVIDENCE_SHA256
  --expected-revision EXPECTED_REVISION
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
```

### `plan confirmation add`

```text
usage: workctl plan confirmation add [-h] --confirmation-id CONFIRMATION_ID
                                     --description DESCRIPTION
                                     [--status {pending,accepted}] [--ref REF]
                                     --intervention-kind {deviation_recovery,external_authority,plan_contract}
                                     --blocks BLOCKS --basis-ref BASIS_REF
                                     [--basis-sha256 BASIS_SHA256]
                                     [--action-kind {destructive_operation,production_change,remote_write,secret_handling,substantive_rollback}]
                                     --expected-revision EXPECTED_REVISION

options:
  -h, --help            show this help message and exit
  --confirmation-id CONFIRMATION_ID
  --description DESCRIPTION
  --status {pending,accepted}
  --ref REF
  --intervention-kind {deviation_recovery,external_authority,plan_contract}
  --blocks BLOCKS
  --basis-ref BASIS_REF
  --basis-sha256 BASIS_SHA256
  --action-kind {destructive_operation,production_change,remote_write,secret_handling,substantive_rollback}
  --expected-revision EXPECTED_REVISION
```

### `plan confirmation classify`

```text
usage: workctl plan confirmation classify [-h] --manifest MANIFEST
                                          --expected-revision EXPECTED_REVISION

options:
  -h, --help            show this help message and exit
  --manifest MANIFEST
  --expected-revision EXPECTED_REVISION
```

### `plan contract revise`

```text
usage: workctl plan contract revise [-h] --manifest MANIFEST

options:
  -h, --help           show this help message and exit
  --manifest MANIFEST
```

### `plan contract upgrade apply`

```text
usage: workctl plan contract upgrade apply [-h] --manifest MANIFEST

options:
  -h, --help           show this help message and exit
  --manifest MANIFEST
```

### `plan contract upgrade recover`

```text
usage: workctl plan contract upgrade recover [-h]
                                             [--transaction-id TRANSACTION_ID]

options:
  -h, --help            show this help message and exit
  --transaction-id TRANSACTION_ID
```

### `plan contract upgrade status`

```text
usage: workctl plan contract upgrade status [-h]

options:
  -h, --help  show this help message and exit
```

### `plan create`

```text
usage: workctl plan create [-h] --plan-id PLAN_ID --title TITLE
                           [--mode {autonomous,strict}]

options:
  -h, --help            show this help message and exit
  --plan-id PLAN_ID
  --title TITLE
  --mode {autonomous,strict}
```

### `plan delivery-complete`

```text
usage: workctl plan delivery-complete [-h] --confirmation CONFIRMATION
                                      [--evidence-manifest EVIDENCE_MANIFEST]
                                      [--evidence-ref EVIDENCE_REF]
                                      [--evidence-sha256 EVIDENCE_SHA256]
                                      --expected-revision EXPECTED_REVISION
                                      [--turn-receipt-sha256 TURN_RECEIPT_SHA256]
                                      [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]

options:
  -h, --help            show this help message and exit
  --confirmation CONFIRMATION
  --evidence-manifest EVIDENCE_MANIFEST
  --evidence-ref EVIDENCE_REF
  --evidence-sha256 EVIDENCE_SHA256
  --expected-revision EXPECTED_REVISION
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
```

### `plan edit`

```text
usage: workctl plan edit [-h] --expected-revision EXPECTED_REVISION
                         [--confirmation CONFIRMATION] [--status STATUS]
                         [--mode {autonomous,strict}] [--include INCLUDE]
                         [--remove-exclude REMOVE_EXCLUDE]
                         [--patch-file PATCH_FILE] [--body-file BODY_FILE]

options:
  -h, --help            show this help message and exit
  --expected-revision EXPECTED_REVISION
  --confirmation CONFIRMATION
  --status STATUS
  --mode {autonomous,strict}
  --include INCLUDE
  --remove-exclude REMOVE_EXCLUDE
  --patch-file PATCH_FILE
  --body-file BODY_FILE
```

### `plan evidence record`

```text
usage: workctl plan evidence record [-h] (--manifest MANIFEST | --stdin)

options:
  -h, --help           show this help message and exit
  --manifest MANIFEST
  --stdin              Read the bounded evidence object from standard input.
```

### `plan finalize-artifact`

```text
usage: workctl plan finalize-artifact [-h] --artifact-id ARTIFACT_ID
                                      --task-id TASK_ID
                                      --confirmation CONFIRMATION
                                      [--evidence-manifest EVIDENCE_MANIFEST]
                                      [--evidence-ref EVIDENCE_REF]
                                      [--evidence-sha256 EVIDENCE_SHA256]
                                      --expected-revision EXPECTED_REVISION
                                      [--turn-receipt-sha256 TURN_RECEIPT_SHA256]
                                      [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]

options:
  -h, --help            show this help message and exit
  --artifact-id ARTIFACT_ID
  --task-id TASK_ID
  --confirmation CONFIRMATION
  --evidence-manifest EVIDENCE_MANIFEST
  --evidence-ref EVIDENCE_REF
  --evidence-sha256 EVIDENCE_SHA256
  --expected-revision EXPECTED_REVISION
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
```

### `plan independent-review record`

```text
usage: workctl plan independent-review record [-h] --manifest MANIFEST
                                              --expected-revision EXPECTED_REVISION
                                              [--turn-receipt-sha256 TURN_RECEIPT_SHA256]
                                              [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]

options:
  -h, --help            show this help message and exit
  --manifest MANIFEST
  --expected-revision EXPECTED_REVISION
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
```

### `plan init`

```text
usage: workctl plan init [-h] --plan-id PLAN_ID --title TITLE
                         [--mode {autonomous,strict}]

options:
  -h, --help            show this help message and exit
  --plan-id PLAN_ID
  --title TITLE
  --mode {autonomous,strict}
```

### `plan intake record`

```text
usage: workctl plan intake record [-h] --manifest MANIFEST
                                  --expected-revision EXPECTED_REVISION

options:
  -h, --help            show this help message and exit
  --manifest MANIFEST
  --expected-revision EXPECTED_REVISION
```

### `plan next`

```text
usage: workctl plan next [-h]

options:
  -h, --help  show this help message and exit
```

### `plan ready`

```text
usage: workctl plan ready [-h]

options:
  -h, --help  show this help message and exit
```

### `plan reconcile apply`

```text
usage: workctl plan reconcile apply [-h] --manifest MANIFEST [--dry-run]

options:
  -h, --help           show this help message and exit
  --manifest MANIFEST
  --dry-run
```

### `plan reconcile recover`

```text
usage: workctl plan reconcile recover [-h] [--migration-id MIGRATION_ID]

options:
  -h, --help            show this help message and exit
  --migration-id MIGRATION_ID
```

### `plan reconcile-upgrade apply`

```text
usage: workctl plan reconcile-upgrade apply [-h] --manifest MANIFEST

options:
  -h, --help           show this help message and exit
  --manifest MANIFEST
```

### `plan reconcile-upgrade recover`

```text
usage: workctl plan reconcile-upgrade recover [-h] [--workflow-id WORKFLOW_ID]

options:
  -h, --help            show this help message and exit
  --workflow-id WORKFLOW_ID
```

### `plan reorder`

```text
usage: workctl plan reorder [-h] --task-id TASK_ID --priority PRIORITY
                            --expected-state-sequence EXPECTED_STATE_SEQUENCE

options:
  -h, --help            show this help message and exit
  --task-id TASK_ID
  --priority PRIORITY
  --expected-state-sequence EXPECTED_STATE_SEQUENCE
```

### `plan retire apply`

```text
usage: workctl plan retire apply [-h] --manifest MANIFEST [--dry-run]

options:
  -h, --help           show this help message and exit
  --manifest MANIFEST
  --dry-run
```

### `plan retire recover`

```text
usage: workctl plan retire recover [-h] --retirement-id RETIREMENT_ID

options:
  -h, --help            show this help message and exit
  --retirement-id RETIREMENT_ID
```

### `plan revise`

```text
usage: workctl plan revise [-h] --expected-revision EXPECTED_REVISION
                           [--confirmation CONFIRMATION] [--status STATUS]
                           [--mode {autonomous,strict}] [--include INCLUDE]
                           [--remove-exclude REMOVE_EXCLUDE]
                           [--patch-file PATCH_FILE] [--body-file BODY_FILE]

options:
  -h, --help            show this help message and exit
  --expected-revision EXPECTED_REVISION
  --confirmation CONFIRMATION
  --status STATUS
  --mode {autonomous,strict}
  --include INCLUDE
  --remove-exclude REMOVE_EXCLUDE
  --patch-file PATCH_FILE
  --body-file BODY_FILE
```

### `plan rollover apply`

```text
usage: workctl plan rollover apply [-h] --manifest MANIFEST [--dry-run]

options:
  -h, --help           show this help message and exit
  --manifest MANIFEST
  --dry-run
```

### `plan rollover recover`

```text
usage: workctl plan rollover recover [-h] --rollover-id ROLLOVER_ID

options:
  -h, --help            show this help message and exit
  --rollover-id ROLLOVER_ID
```

### `plan schema-validate`

```text
usage: workctl plan schema-validate [-h] [--plan PLAN]

options:
  -h, --help   show this help message and exit
  --plan PLAN
```

### `plan show`

```text
usage: workctl plan show [-h]
                         [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]
                         [--full]

options:
  -h, --help            show this help message and exit
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
  --full
```

### `plan status`

```text
usage: workctl plan status [-h]
                           [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]
                           [--full]

options:
  -h, --help            show this help message and exit
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
  --full                Include the complete authority, history, and closeout
                        report.
```

### `plan structural-rebase apply`

```text
usage: workctl plan structural-rebase apply [-h] --manifest MANIFEST
                                            [--dry-run]

options:
  -h, --help           show this help message and exit
  --manifest MANIFEST
  --dry-run
```

### `plan structural-rebase recover`

```text
usage: workctl plan structural-rebase recover [-h]
                                              --transaction-id TRANSACTION_ID

options:
  -h, --help            show this help message and exit
  --transaction-id TRANSACTION_ID
```

### `plan unknown add`

```text
usage: workctl plan unknown add [-h] --unknown-id UNKNOWN_ID
                                --question QUESTION --owner {agent,user}
                                --impact {blocking,non_blocking}
                                [--blocks BLOCKS]
                                --expected-evidence EXPECTED_EVIDENCE
                                --expected-revision EXPECTED_REVISION

options:
  -h, --help            show this help message and exit
  --unknown-id UNKNOWN_ID
  --question QUESTION
  --owner {agent,user}
  --impact {blocking,non_blocking}
  --blocks BLOCKS
  --expected-evidence EXPECTED_EVIDENCE
  --expected-revision EXPECTED_REVISION
```

### `plan unknown classify`

```text
usage: workctl plan unknown classify [-h] --manifest MANIFEST
                                     --expected-revision EXPECTED_REVISION

options:
  -h, --help            show this help message and exit
  --manifest MANIFEST
  --expected-revision EXPECTED_REVISION
```

### `plan unknown resolve`

```text
usage: workctl plan unknown resolve [-h] --unknown-id UNKNOWN_ID
                                    --resolution RESOLUTION
                                    --evidence-manifest EVIDENCE_MANIFEST
                                    --expected-revision EXPECTED_REVISION

options:
  -h, --help            show this help message and exit
  --unknown-id UNKNOWN_ID
  --resolution RESOLUTION
  --evidence-manifest EVIDENCE_MANIFEST
  --expected-revision EXPECTED_REVISION
```

### `plan validate`

```text
usage: workctl plan validate [-h] [--evidence-manifest EVIDENCE_MANIFEST]

options:
  -h, --help            show this help message and exit
  --evidence-manifest EVIDENCE_MANIFEST
```

### `plan verify-entry`

```text
usage: workctl plan verify-entry [-h] --field {obligations,validations}
                                 --entry-id ENTRY_ID
                                 --confirmation CONFIRMATION
                                 [--evidence-manifest EVIDENCE_MANIFEST]
                                 [--evidence-ref EVIDENCE_REF]
                                 [--evidence-sha256 EVIDENCE_SHA256]
                                 --expected-revision EXPECTED_REVISION
                                 [--turn-receipt-sha256 TURN_RECEIPT_SHA256]
                                 [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]

options:
  -h, --help            show this help message and exit
  --field {obligations,validations}
  --entry-id ENTRY_ID
  --confirmation CONFIRMATION
  --evidence-manifest EVIDENCE_MANIFEST
  --evidence-ref EVIDENCE_REF
  --evidence-sha256 EVIDENCE_SHA256
  --expected-revision EXPECTED_REVISION
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
```

### `review attach`

```text
usage: workctl review attach [-h] --manifest MANIFEST
                             --expected-revision EXPECTED_REVISION
                             [--turn-receipt-sha256 TURN_RECEIPT_SHA256]
                             [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]

options:
  -h, --help            show this help message and exit
  --manifest MANIFEST
  --expected-revision EXPECTED_REVISION
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
```

### `review request`

```text
usage: workctl review request [-h]

options:
  -h, --help  show this help message and exit
```

### `review status`

```text
usage: workctl review status [-h]

options:
  -h, --help  show this help message and exit
```

### `task block`

```text
usage: workctl task block [-h] --task-id TASK_ID
                          [--expected-revision EXPECTED_REVISION]
                          [--expected-state-sequence EXPECTED_STATE_SEQUENCE]
                          [--note NOTE]

options:
  -h, --help            show this help message and exit
  --task-id TASK_ID
  --expected-revision EXPECTED_REVISION
  --expected-state-sequence EXPECTED_STATE_SEQUENCE
  --note NOTE
```

### `task reprioritize`

```text
usage: workctl task reprioritize [-h] --task-id TASK_ID --priority PRIORITY
                                 --expected-state-sequence EXPECTED_STATE_SEQUENCE

options:
  -h, --help            show this help message and exit
  --task-id TASK_ID
  --priority PRIORITY
  --expected-state-sequence EXPECTED_STATE_SEQUENCE
```

### `task skip`

```text
usage: workctl task skip [-h] --task-id TASK_ID
                         [--expected-revision EXPECTED_REVISION]
                         [--expected-state-sequence EXPECTED_STATE_SEQUENCE]
                         [--note NOTE]
                         [--turn-receipt-sha256 TURN_RECEIPT_SHA256]
                         [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]

options:
  -h, --help            show this help message and exit
  --task-id TASK_ID
  --expected-revision EXPECTED_REVISION
  --expected-state-sequence EXPECTED_STATE_SEQUENCE
  --note NOTE
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
```

### `task start`

```text
usage: workctl task start [-h] --task-id TASK_ID
                          [--expected-revision EXPECTED_REVISION]
                          [--expected-state-sequence EXPECTED_STATE_SEQUENCE]
                          [--note NOTE]
                          [--turn-receipt-sha256 TURN_RECEIPT_SHA256]
                          [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]

options:
  -h, --help            show this help message and exit
  --task-id TASK_ID
  --expected-revision EXPECTED_REVISION
  --expected-state-sequence EXPECTED_STATE_SEQUENCE
  --note NOTE
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
```

### `task unblock`

```text
usage: workctl task unblock [-h] --task-id TASK_ID
                            [--expected-revision EXPECTED_REVISION]
                            [--expected-state-sequence EXPECTED_STATE_SEQUENCE]
                            [--note NOTE]
                            [--turn-receipt-sha256 TURN_RECEIPT_SHA256]
                            [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]

options:
  -h, --help            show this help message and exit
  --task-id TASK_ID
  --expected-revision EXPECTED_REVISION
  --expected-state-sequence EXPECTED_STATE_SEQUENCE
  --note NOTE
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
```

### `task verify`

```text
usage: workctl task verify [-h] --task-id TASK_ID
                           [--expected-revision EXPECTED_REVISION]
                           [--expected-state-sequence EXPECTED_STATE_SEQUENCE]
                           [--note NOTE]
                           [--evidence-manifest EVIDENCE_MANIFEST |
                           --evidence-stdin]
                           [--turn-receipt-sha256 TURN_RECEIPT_SHA256]
                           [--expected-intake-sha256 EXPECTED_INTAKE_SHA256]

options:
  -h, --help            show this help message and exit
  --task-id TASK_ID
  --expected-revision EXPECTED_REVISION
  --expected-state-sequence EXPECTED_STATE_SEQUENCE
  --note NOTE
  --evidence-manifest EVIDENCE_MANIFEST
  --evidence-stdin      Record bounded evidence from standard input atomically
                        with verification.
  --turn-receipt-sha256 TURN_RECEIPT_SHA256
  --expected-intake-sha256 EXPECTED_INTAKE_SHA256
```

### `truth add`

```text
usage: workctl truth add [-h] --manifest MANIFEST

options:
  -h, --help           show this help message and exit
  --manifest MANIFEST
```

### `truth conflicts`

```text
usage: workctl truth conflicts [-h]

options:
  -h, --help  show this help message and exit
```

### `truth list`

```text
usage: workctl truth list [-h]

options:
  -h, --help  show this help message and exit
```

### `truth resolve`

```text
usage: workctl truth resolve [-h] --manifest MANIFEST

options:
  -h, --help           show this help message and exit
  --manifest MANIFEST
```
