"""Argparse command surface for the Work Governance controller."""

from __future__ import annotations

# Controller command handlers and constants are bound by name while the parser
# is built, then stored on argparse actions as callable objects.
# ruff: noqa: F821
import argparse
import json
from collections.abc import Mapping
from typing import Any

from workctl_modules.kernel.bindings import call_with_bound_globals


def workflow_help(
    args: argparse.Namespace,
    *,
    workflows: Mapping[str, Any],
    workflow_aliases: Mapping[str, str],
    error_cls: type[Exception],
) -> None:
    """Print the stable public workflow command surface."""
    workflow = args.workflow or "plan"
    workflow = workflow_aliases.get(workflow, workflow)
    if workflow not in workflows:
        raise error_cls(f"UNKNOWN_WORKFLOW: {workflow}")
    print(json.dumps(workflows[workflow], indent=2, sort_keys=True))


def build_parser(bindings: Mapping[str, Any]) -> argparse.ArgumentParser:
    """Build the CLI parser while binding controller command handlers by name."""
    return call_with_bound_globals(globals(), bindings, _build_parser)


def add_current_intake_args(parser: argparse.ArgumentParser) -> None:
    """Add the shared trusted-turn advancement arguments."""
    parser.add_argument("--turn-receipt-sha256")
    parser.add_argument("--expected-intake-sha256")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workctl")
    parser.add_argument(
        "--receipt-sha256",
        help="Optional SHA256 of a legacy READY bootstrap receipt.",
    )
    sub = parser.add_subparsers(dest="domain", required=True)

    help_command = sub.add_parser("help")
    help_command.add_argument(
        "workflow",
        nargs="?",
        choices=[
            "plan",
            "task",
            "evidence",
            "action",
            "migrate",
            "migration",
            "goal",
            "gate",
            "truth",
            "review",
            "context",
            "risk",
            "worktree",
            "doctor",
        ],
    )
    help_command.set_defaults(func=cmd_workflow_help)

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--older-than-hours", type=int, default=24)
    doctor.add_argument("--clean-stale-transactions", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    goal_command = sub.add_parser("goal")
    goal_sub = goal_command.add_subparsers(dest="goal_action", required=True)
    goal_init = goal_sub.add_parser("init")
    goal_init.add_argument("--plan-id")
    goal_init.add_argument("--title")
    goal_init_source = goal_init.add_mutually_exclusive_group(required=True)
    goal_init_source.add_argument("--stdin", action="store_true")
    goal_init_source.add_argument("--from-file")
    goal_init.add_argument("--mode", choices=["autonomous", "strict"], default="autonomous")
    goal_init.set_defaults(func=cmd_goal_init)
    goal_show = goal_sub.add_parser("show")
    goal_show.set_defaults(func=cmd_goal_show)
    goal_revise = goal_sub.add_parser("revise")
    goal_revise.add_argument("--manifest", required=True)
    goal_revise.set_defaults(func=cmd_plan_contract_revise)
    goal_close = goal_sub.add_parser("close")
    goal_close.add_argument("--expected-revision", type=int)
    goal_close.add_argument("--expected-state-sequence", type=int)
    goal_close.add_argument("--evidence-manifest")
    goal_close.add_argument("--finalize-route", action="store_true")
    goal_close.add_argument("--confirmation")
    add_current_intake_args(goal_close)
    goal_close.set_defaults(func=cmd_plan_complete)

    gate_command = sub.add_parser("gate")
    gate_sub = gate_command.add_subparsers(dest="gate_action", required=True)
    gate_list = gate_sub.add_parser("list")
    gate_list.set_defaults(func=cmd_gate_list)
    gate_check = gate_sub.add_parser("check")
    gate_check.add_argument("--gate-id", required=True)
    gate_check.set_defaults(func=cmd_gate_check)
    gate_open = gate_sub.add_parser("open")
    gate_open.add_argument("--confirmation-id", required=True)
    gate_open.add_argument("--description", required=True)
    gate_open.add_argument("--status", default="pending")
    gate_open.add_argument("--ref")
    gate_open.add_argument("--intervention-kind", choices=sorted(INTERVENTION_KINDS), required=True)
    gate_open.add_argument("--blocks", action="append", required=True)
    gate_open.add_argument("--basis-ref", required=True)
    gate_open.add_argument("--basis-sha256")
    gate_open.add_argument("--action-kind", choices=sorted(HIGH_IMPACT_ACTION_KINDS))
    gate_open.add_argument("--expected-revision", type=int, required=True)
    gate_open.set_defaults(func=cmd_plan_confirmation_add)
    for gate_action, decision in (("satisfy", "accepted"), ("waive", "declined")):
        gate_decide = gate_sub.add_parser(gate_action)
        gate_decide.add_argument("--confirmation-id", required=True)
        gate_decide.add_argument("--ref", required=True)
        gate_decide.add_argument("--evidence-sha256")
        gate_decide.add_argument("--expected-revision", type=int, required=True)
        add_current_intake_args(gate_decide)
        gate_decide.set_defaults(
            func=cmd_gate_satisfy if decision == "accepted" else cmd_gate_waive
        )

    truth_command = sub.add_parser("truth")
    truth_sub = truth_command.add_subparsers(dest="truth_action", required=True)
    truth_list = truth_sub.add_parser("list")
    truth_list.set_defaults(func=cmd_truth_list)
    truth_conflicts = truth_sub.add_parser("conflicts")
    truth_conflicts.set_defaults(func=cmd_truth_conflicts)
    for truth_action in ("add", "resolve"):
        truth_edit = truth_sub.add_parser(truth_action)
        truth_edit.add_argument("--manifest", required=True)
        truth_edit.set_defaults(func=cmd_plan_contract_revise)

    review_command = sub.add_parser("review")
    review_sub = review_command.add_subparsers(dest="review_action", required=True)
    review_request = review_sub.add_parser("request")
    review_request.set_defaults(func=cmd_review_request)
    review_status = review_sub.add_parser("status")
    review_status.set_defaults(func=cmd_review_status)
    review_acquisition = review_sub.add_parser("acquisition")
    review_acquisition_sub = review_acquisition.add_subparsers(
        dest="review_acquisition_action",
        required=True,
    )

    def add_review_acquisition_scope_args(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--target-ref", required=True)
        parser.add_argument("--mechanism", required=True)
        parser.add_argument("--review-input-sha256", required=True)

    review_acquisition_check = review_acquisition_sub.add_parser("check")
    add_review_acquisition_scope_args(review_acquisition_check)
    review_acquisition_check.set_defaults(func=cmd_review_acquisition_check)
    review_acquisition_status = review_acquisition_sub.add_parser("status")
    review_acquisition_status.add_argument("--target-ref")
    review_acquisition_status.add_argument("--mechanism")
    review_acquisition_status.set_defaults(func=cmd_review_acquisition_status)
    review_acquisition_record = review_acquisition_sub.add_parser("record-failure")
    add_review_acquisition_scope_args(review_acquisition_record)
    review_acquisition_record.add_argument("--attempt-ref", required=True)
    review_acquisition_record.add_argument("--exit-code", type=int, required=True)
    review_acquisition_record.add_argument(
        "--failure-class",
        choices=["auto", *sorted(REVIEWER_FAILURE_CLASSES)],
        default="auto",
    )
    review_acquisition_record.add_argument("--summary")
    review_acquisition_record.add_argument("--failure-stdin", action="store_true")
    review_acquisition_record.add_argument("--failure-from-file")
    review_acquisition_record.add_argument("--cooldown-seconds", type=int, default=900)
    review_acquisition_record.add_argument("--idempotency-key")
    review_acquisition_record.add_argument("--dry-run", action="store_true")
    review_acquisition_record.set_defaults(func=cmd_review_acquisition_record_failure)
    review_attach = review_sub.add_parser("attach")
    review_attach.add_argument("--manifest", required=True)
    review_attach.add_argument("--expected-revision", type=int, required=True)
    add_current_intake_args(review_attach)
    review_attach.set_defaults(func=cmd_plan_independent_review_record)

    evidence_command = sub.add_parser("evidence")
    evidence_sub = evidence_command.add_subparsers(dest="evidence_action", required=True)
    evidence_capture = evidence_sub.add_parser("capture")
    evidence_capture.add_argument("--task")
    evidence_capture.add_argument("--kind", required=True)
    evidence_capture.add_argument("--summary", required=True)
    evidence_capture.add_argument("--from-file")
    evidence_capture.add_argument(
        "--stdin",
        action="store_true",
        help="Read evidence bytes from standard input; stdin is also the default source.",
    )
    evidence_capture.add_argument(
        "--redaction-policy",
        default="default-secret-patterns-v1",
    )
    evidence_capture.add_argument("--idempotency-key")
    evidence_capture.add_argument("--expected-state-sequence", type=int)
    evidence_capture.set_defaults(func=cmd_evidence_capture)
    evidence_command_capture = evidence_sub.add_parser("command")
    evidence_command_capture.add_argument("--task", required=True)
    evidence_command_capture.add_argument("--kind", default="command-output")
    evidence_command_capture.add_argument("--summary", required=True)
    evidence_command_capture.add_argument("--cwd")
    evidence_command_capture.add_argument("--timeout-seconds", type=int, default=120)
    evidence_command_capture.add_argument("--max-output-bytes", type=int, default=262144)
    evidence_command_capture.add_argument("--idempotency-key")
    evidence_command_capture.add_argument("--expected-state-sequence", type=int)
    evidence_command_capture.add_argument("command", nargs=argparse.REMAINDER)
    evidence_command_capture.set_defaults(func=cmd_evidence_command)
    evidence_record = evidence_sub.add_parser("record")
    evidence_source = evidence_record.add_mutually_exclusive_group(required=True)
    evidence_source.add_argument("--manifest")
    evidence_source.add_argument("--stdin", action="store_true")
    evidence_record.set_defaults(func=cmd_plan_evidence_record)

    context_command = sub.add_parser("context")
    context_sub = context_command.add_subparsers(dest="context_action", required=True)
    context_build = context_sub.add_parser("build")
    context_build.add_argument("--role", choices=sorted(CONTEXT_ROLES), required=True)
    context_build_source = context_build.add_mutually_exclusive_group(required=True)
    context_build_source.add_argument("--manifest")
    context_build_source.add_argument(
        "--stdin",
        action="store_true",
        help="Read a JSON/YAML context manifest from standard input.",
    )
    context_build.add_argument("--task")
    context_build.add_argument("--summary")
    context_build.add_argument(
        "--max-file-bytes",
        type=int,
        default=DEFAULT_MAX_FILE_BYTES,
    )
    context_build.add_argument(
        "--max-total-bytes",
        type=int,
        default=DEFAULT_MAX_TOTAL_BYTES,
    )
    context_build.set_defaults(func=cmd_context_build)

    risk = sub.add_parser("risk")
    risk_sub = risk.add_subparsers(dest="risk_action", required=True)
    risk_inspect = risk_sub.add_parser("inspect")
    risk_inspect.add_argument(
        "--action-kind",
        choices=sorted(MODEL_RISK_ACTION_KINDS),
        required=True,
    )
    risk_inspect.add_argument("--target-ref", required=True)
    risk_source = risk_inspect.add_mutually_exclusive_group()
    risk_source.add_argument("--action-stdin", action="store_true")
    risk_source.add_argument("--action-from-file")
    risk_inspect.set_defaults(func=cmd_risk_inspect)

    action_command = sub.add_parser("action")
    action_sub = action_command.add_subparsers(
        dest="action_authorization_action",
        required=True,
    )
    action_authorize = action_sub.add_parser("authorize")
    action_authorize.add_argument(
        "--action-kind",
        choices=sorted(HIGH_IMPACT_ACTION_KINDS),
        required=True,
    )
    action_authorize.add_argument("--target-ref", required=True)
    action_authorize.add_argument("--action-sha256", required=True)
    action_authorize.add_argument("--confirmation-id", required=True)
    action_authorize.add_argument("--ref", required=True)
    action_authorize.add_argument("--turn-receipt-sha256", required=True)
    action_authorize.add_argument("--ttl-seconds", type=int, default=300)
    action_authorize.set_defaults(func=cmd_action_authorize)
    action_consume = action_sub.add_parser("consume")
    action_consume.add_argument("--authorization-id", required=True)
    action_consume.add_argument(
        "--action-kind",
        choices=sorted(HIGH_IMPACT_ACTION_KINDS),
        required=True,
    )
    action_consume.add_argument("--target-ref", required=True)
    action_consume.add_argument("--action-sha256", required=True)
    action_consume.add_argument("--turn-receipt-sha256")
    action_consume.add_argument("--consumer-ref", required=True)
    action_consume.set_defaults(func=cmd_action_consume)
    action_status = action_sub.add_parser("status")
    action_status.add_argument("--authorization-id", required=True)
    action_status.set_defaults(func=cmd_action_status)
    action_lease = action_sub.add_parser("lease")
    action_lease_sub = action_lease.add_subparsers(dest="action_lease_action", required=True)

    def add_action_lease_scope_args(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--action-kind",
            choices=sorted(HIGH_IMPACT_ACTION_KINDS),
            required=True,
        )
        parser.add_argument("--target-ref", action="append", default=[])
        parser.add_argument("--target-prefix", action="append", default=[])
        parser.add_argument(
            "--action-digest-policy",
            choices=sorted(ACTION_DIGEST_POLICIES),
            default="exact-list",
        )
        parser.add_argument("--allowed-action-sha256", action="append", default=[])
        parser.add_argument("--blocks", action="append", default=[])
        parser.add_argument("--lease-ttl-seconds", type=int, default=3600)
        parser.add_argument("--authorization-ttl-seconds", type=int, default=300)
        parser.add_argument("--max-authorizations", type=int, default=10)
        parser.add_argument(
            "--freeze-on-review-blocker",
            action=argparse.BooleanOptionalAction,
            default=True,
        )
        parser.add_argument("--pilot-evidence-ref")

    action_lease_prepare = action_lease_sub.add_parser("prepare")
    add_action_lease_scope_args(action_lease_prepare)
    action_lease_prepare.set_defaults(func=cmd_action_lease_prepare)
    action_lease_issue = action_lease_sub.add_parser("issue")
    add_action_lease_scope_args(action_lease_issue)
    action_lease_issue.add_argument("--confirmation-id", required=True)
    action_lease_issue.add_argument("--basis-sha256", required=True)
    action_lease_issue.add_argument("--ref", required=True)
    action_lease_issue.add_argument("--turn-receipt-sha256", required=True)
    action_lease_issue.set_defaults(func=cmd_action_lease_issue)
    action_lease_authorize = action_lease_sub.add_parser("authorize")
    action_lease_authorize.add_argument("--lease-id", required=True)
    action_lease_authorize.add_argument(
        "--action-kind",
        choices=sorted(HIGH_IMPACT_ACTION_KINDS),
        required=True,
    )
    action_lease_authorize.add_argument("--target-ref", required=True)
    action_lease_authorize.add_argument("--action-sha256", required=True)
    action_lease_authorize.add_argument("--idempotency-key")
    action_lease_authorize.add_argument("--ttl-seconds", type=int)
    action_lease_authorize.set_defaults(func=cmd_action_lease_authorize)
    action_lease_status = action_lease_sub.add_parser("status")
    action_lease_status.add_argument("--lease-id", required=True)
    action_lease_status.set_defaults(func=cmd_action_lease_status)
    action_lease_revoke = action_lease_sub.add_parser("revoke")
    action_lease_revoke.add_argument("--lease-id", required=True)
    action_lease_revoke.add_argument("--ref", required=True)
    action_lease_revoke.set_defaults(func=cmd_action_lease_revoke)

    migrate = sub.add_parser(
        "migrate",
        description=(
            "Archive outdated active Plans and rebuild the plugin-declared current "
            "schema without adapting legacy runtime state."
        ),
    )
    migrate_sub = migrate.add_subparsers(dest="migration_action", required=True)
    migrate_inspect = migrate_sub.add_parser(
        "inspect",
        description=(
            "Read-only refresh boundary plus NON_AUTHORITY legacy_summary for an "
            "outdated active Plan."
        ),
    )
    migrate_inspect.set_defaults(func=cmd_migrate_inspect)
    migrate_apply = migrate_sub.add_parser(
        "apply",
        description=(
            "Preview or perform current-schema refresh. Output includes state_reset, "
            "legacy_state_migrated=false, not_migrated, and legacy_summary."
        ),
    )
    migrate_apply.add_argument(
        "--confirmation",
        help="Deprecated compatibility argument; current-schema refresh does not require it.",
    )
    migrate_apply.add_argument(
        "--expected-contract-revision",
        type=int,
        help="Required for durable refresh; guards the archived legacy source revision.",
    )
    migrate_apply.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the archive and rebuild boundary without writing project state.",
    )
    migrate_apply.set_defaults(func=cmd_migrate_apply)
    migrate_recover = migrate_sub.add_parser("recover")
    migrate_recover.add_argument("--migration-id")
    migrate_recover.set_defaults(func=cmd_migrate_recover)
    migrate_rollback = migrate_sub.add_parser("rollback-info")
    migrate_rollback.add_argument("--migration-id")
    migrate_rollback.set_defaults(func=cmd_migrate_rollback_info)

    intake = sub.add_parser("intake")
    intake_sub = intake.add_subparsers(dest="intake_action", required=True)
    intake_status = intake_sub.add_parser("status")
    intake_status.set_defaults(func=cmd_intake_status)
    intake_receipt = intake_sub.add_parser("receipt")
    intake_receipt.add_argument("--turn-receipt-sha256", required=True)
    intake_receipt.add_argument(
        "--classification",
        choices=["no_plan", "plan_controlled"],
        required=True,
    )
    intake_receipt.add_argument(
        "--decision",
        choices=["proceed", "explore", "ask"],
        required=True,
    )
    intake_receipt.add_argument("--rationale", required=True)
    intake_receipt.add_argument("--targets", action="append", required=True)
    intake_receipt.add_argument("--current-unknown-id")
    intake_receipt.add_argument("--candidate-plan")
    intake_receipt.set_defaults(func=cmd_intake_receipt)

    layout = sub.add_parser("layout")
    layout_sub = layout.add_subparsers(dest="action", required=True)
    layout_status = layout_sub.add_parser("status")
    layout_status.set_defaults(func=cmd_layout_status)
    layout_validate = layout_sub.add_parser("validate")
    layout_validate.set_defaults(func=cmd_layout_validate)
    layout_adopt = layout_sub.add_parser("adopt")
    layout_adopt.add_argument("--expected-manifest-sha256", required=True)
    layout_adopt.add_argument("--expected-active-plan-id", required=True)
    layout_adopt.add_argument("--ref", required=True)
    layout_adopt.set_defaults(func=cmd_layout_adopt)
    layout_migrate = layout_sub.add_parser("migrate")
    layout_migrate.set_defaults(func=cmd_layout_migrate)
    layout_recover = layout_sub.add_parser("recover")
    layout_recover.set_defaults(func=cmd_layout_recover)

    plan = sub.add_parser("plan")
    plan_sub = plan.add_subparsers(dest="action", required=True)
    init = plan_sub.add_parser("init")
    init.add_argument("--plan-id", required=True)
    init.add_argument("--title", required=True)
    init.add_argument("--mode", choices=["autonomous", "strict"], default="autonomous")
    init.set_defaults(func=cmd_plan_init)
    create = plan_sub.add_parser("create")
    create.add_argument("--plan-id", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--mode", choices=["autonomous", "strict"], default="autonomous")
    create.set_defaults(func=cmd_plan_init)
    status = plan_sub.add_parser("status")
    status.add_argument("--expected-intake-sha256")
    status.add_argument(
        "--full",
        action="store_true",
        help="Include the complete authority, history, and closeout report.",
    )
    status.set_defaults(func=cmd_plan_status)
    show = plan_sub.add_parser("show")
    show.add_argument("--expected-intake-sha256")
    show.add_argument("--full", action="store_true")
    show.set_defaults(func=cmd_plan_status)
    history = plan_sub.add_parser("history")
    history_sub = history.add_subparsers(dest="history_action", required=True)
    history_list = history_sub.add_parser("list")
    history_list.set_defaults(func=cmd_plan_history)
    history_show = history_sub.add_parser("show")
    history_show.add_argument("--plan-id")
    history_show.add_argument("--path")
    history_show.set_defaults(func=cmd_plan_history)
    for queue_action in ("ready", "next", "blocked"):
        queue = plan_sub.add_parser(queue_action)
        queue.set_defaults(func=cmd_plan_queue, queue_action=queue_action)
    reorder = plan_sub.add_parser("reorder")
    reorder.add_argument("--task-id", required=True)
    reorder.add_argument("--priority", type=int, required=True)
    reorder.add_argument("--expected-state-sequence", type=int, required=True)
    reorder.set_defaults(func=cmd_task_reprioritize)
    plan_intake = plan_sub.add_parser("intake")
    plan_intake_sub = plan_intake.add_subparsers(
        dest="plan_intake_action",
        required=True,
    )
    plan_intake_record = plan_intake_sub.add_parser("record")
    plan_intake_record.add_argument("--manifest", required=True)
    plan_intake_record.add_argument("--expected-revision", type=int, required=True)
    plan_intake_record.set_defaults(func=cmd_plan_intake_record)
    admit = plan_sub.add_parser("admit")
    admit_sub = admit.add_subparsers(dest="admit_action", required=True)
    admit_apply = admit_sub.add_parser("apply")
    admit_apply.add_argument("--manifest", required=True)
    admit_apply.set_defaults(func=cmd_plan_admit_apply)
    admit_recover = admit_sub.add_parser("recover")
    admit_recover.add_argument("--transaction-id")
    admit_recover.set_defaults(func=cmd_plan_admit_recover)
    authority = plan_sub.add_parser("authority")
    authority_sub = authority.add_subparsers(dest="authority_action", required=True)
    authority_inspect = authority_sub.add_parser("inspect")
    authority_inspect.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="Agent semantic input as PATH=CLASSIFICATION.",
    )
    authority_inspect.set_defaults(func=cmd_plan_authority_inspect)
    authority_check = authority_sub.add_parser("check")
    authority_check.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="Agent semantic input as PATH=CLASSIFICATION.",
    )
    authority_check.set_defaults(func=cmd_plan_authority_check)
    schema_validate = plan_sub.add_parser("schema-validate")
    schema_validate.add_argument("--plan")
    schema_validate.set_defaults(func=cmd_plan_schema_validate)
    validate = plan_sub.add_parser("validate")
    validate.add_argument("--evidence-manifest")
    validate.set_defaults(func=cmd_plan_validate)
    adapt = plan_sub.add_parser("adapt")
    adapt_source = adapt.add_mutually_exclusive_group(required=True)
    adapt_source.add_argument("--manifest")
    adapt_source.add_argument("--intent-stdin", action="store_true")
    adapt_source.add_argument("--intent-from-file")
    adapt.add_argument("--summary")
    adapt.add_argument("--idempotency-key")
    adapt.add_argument(
        "--expected-revision",
        type=int,
        help="Required for schema-v4 high-level intent adaptation.",
    )
    add_current_intake_args(adapt)
    adapt.set_defaults(func=cmd_plan_adapt)
    contract = plan_sub.add_parser("contract")
    contract_sub = contract.add_subparsers(dest="contract_action", required=True)
    contract_revise = contract_sub.add_parser("revise")
    contract_revise.add_argument("--manifest", required=True)
    contract_revise.set_defaults(func=cmd_plan_contract_revise)
    contract_upgrade = contract_sub.add_parser(
        "upgrade",
        description=(
            "Historical schema-v3-to-v4 recovery/audit surface. New work uses "
            "`migrate apply` current-schema refresh."
        ),
    )
    contract_upgrade_sub = contract_upgrade.add_subparsers(
        dest="contract_upgrade_action",
        required=True,
    )
    contract_upgrade_status = contract_upgrade_sub.add_parser(
        "status",
        description=(
            "Historical schema-v3-to-v4 upgrade status. Current active Plans "
            "older than the plugin-declared schema use `migrate inspect`."
        ),
    )
    contract_upgrade_status.set_defaults(func=cmd_plan_contract_upgrade_status)
    contract_upgrade_apply = contract_upgrade_sub.add_parser(
        "apply",
        description=(
            "Historical schema-v3-to-v4 upgrade transaction. New work must "
            "archive and rebuild through `migrate apply` instead."
        ),
    )
    contract_upgrade_apply.add_argument("--manifest", required=True)
    contract_upgrade_apply.set_defaults(func=cmd_plan_contract_upgrade_apply)
    contract_upgrade_recover = contract_upgrade_sub.add_parser(
        "recover",
        description=("Recover only an already staged historical schema-v3-to-v4 upgrade journal."),
    )
    contract_upgrade_recover.add_argument("--transaction-id")
    contract_upgrade_recover.set_defaults(func=cmd_plan_contract_upgrade_recover)
    structural_rebase = plan_sub.add_parser("structural-rebase")
    structural_rebase_sub = structural_rebase.add_subparsers(
        dest="structural_rebase_action",
        required=True,
    )
    structural_rebase_apply = structural_rebase_sub.add_parser("apply")
    structural_rebase_apply.add_argument("--manifest", required=True)
    structural_rebase_apply.add_argument("--dry-run", action="store_true")
    structural_rebase_apply.set_defaults(func=cmd_plan_structural_rebase_apply)
    structural_rebase_recover = structural_rebase_sub.add_parser("recover")
    structural_rebase_recover.add_argument("--transaction-id", required=True)
    structural_rebase_recover.set_defaults(func=cmd_plan_structural_rebase_recover)
    unknown = plan_sub.add_parser("unknown")
    unknown_sub = unknown.add_subparsers(dest="unknown_action", required=True)
    unknown_add = unknown_sub.add_parser("add")
    unknown_add.add_argument("--unknown-id", required=True)
    unknown_add.add_argument("--question", required=True)
    unknown_add.add_argument("--owner", choices=sorted(UNKNOWN_OWNERS), required=True)
    unknown_add.add_argument("--impact", choices=sorted(UNKNOWN_IMPACTS), required=True)
    unknown_add.add_argument("--blocks", action="append", default=[])
    unknown_add.add_argument("--expected-evidence", required=True)
    unknown_add.add_argument("--expected-revision", type=int, required=True)
    unknown_add.set_defaults(func=cmd_plan_unknown_add)
    unknown_classify = unknown_sub.add_parser("classify")
    unknown_classify.add_argument("--manifest", required=True)
    unknown_classify.add_argument("--expected-revision", type=int, required=True)
    unknown_classify.set_defaults(func=cmd_plan_unknown_classify)
    unknown_resolve = unknown_sub.add_parser("resolve")
    unknown_resolve.add_argument("--unknown-id", required=True)
    unknown_resolve.add_argument("--resolution", required=True)
    unknown_resolve.add_argument("--evidence-manifest", required=True)
    unknown_resolve.add_argument("--expected-revision", type=int, required=True)
    unknown_resolve.set_defaults(func=cmd_plan_unknown_resolve)
    evidence = plan_sub.add_parser("evidence")
    evidence_sub = evidence.add_subparsers(dest="evidence_action", required=True)
    evidence_record = evidence_sub.add_parser("record")
    evidence_source = evidence_record.add_mutually_exclusive_group(required=True)
    evidence_source.add_argument("--manifest")
    evidence_source.add_argument(
        "--stdin",
        action="store_true",
        help="Read the bounded evidence object from standard input.",
    )
    evidence_record.set_defaults(func=cmd_plan_evidence_record)
    reconcile = plan_sub.add_parser("reconcile")
    reconcile_sub = reconcile.add_subparsers(dest="reconcile_action", required=True)
    reconcile_apply = reconcile_sub.add_parser("apply")
    reconcile_apply.add_argument("--manifest", required=True)
    reconcile_apply.add_argument("--dry-run", action="store_true")
    reconcile_apply.set_defaults(func=cmd_plan_reconcile_apply)
    reconcile_recover = reconcile_sub.add_parser("recover")
    reconcile_recover.add_argument("--migration-id")
    reconcile_recover.set_defaults(func=cmd_plan_reconcile_recover)
    reconcile_upgrade = plan_sub.add_parser(
        "reconcile-upgrade",
        description=(
            "Historical composed schema-v3 reconciliation plus schema-v4 upgrade "
            "surface. New work uses `migrate apply` current-schema refresh."
        ),
    )
    reconcile_upgrade_sub = reconcile_upgrade.add_subparsers(
        dest="reconcile_upgrade_action",
        required=True,
    )
    reconcile_upgrade_apply = reconcile_upgrade_sub.add_parser(
        "apply",
        description=(
            "Historical composed schema-v3/v4 transaction. Current active legacy "
            "Plans are archived and rebuilt through `migrate apply`."
        ),
    )
    reconcile_upgrade_apply.add_argument("--manifest", required=True)
    reconcile_upgrade_apply.set_defaults(func=cmd_plan_reconcile_upgrade_apply)
    reconcile_upgrade_recover = reconcile_upgrade_sub.add_parser(
        "recover",
        description=("Recover only an already staged historical reconcile-upgrade workflow."),
    )
    reconcile_upgrade_recover.add_argument("--workflow-id")
    reconcile_upgrade_recover.set_defaults(func=cmd_plan_reconcile_upgrade_recover)
    rollover = plan_sub.add_parser("rollover")
    rollover_sub = rollover.add_subparsers(dest="rollover_action", required=True)
    rollover_apply = rollover_sub.add_parser("apply")
    rollover_apply.add_argument("--manifest", required=True)
    rollover_apply.add_argument("--dry-run", action="store_true")
    rollover_apply.set_defaults(func=cmd_plan_rollover_apply)
    rollover_recover = rollover_sub.add_parser("recover")
    rollover_recover.add_argument("--rollover-id", required=True)
    rollover_recover.set_defaults(func=cmd_plan_rollover_recover)
    retire = plan_sub.add_parser("retire")
    retire_sub = retire.add_subparsers(dest="retire_action", required=True)
    retire_apply = retire_sub.add_parser("apply")
    retire_apply.add_argument("--manifest", required=True)
    retire_apply.add_argument("--dry-run", action="store_true")
    retire_apply.set_defaults(func=cmd_plan_retire_apply)
    retire_recover = retire_sub.add_parser("recover")
    retire_recover.add_argument("--retirement-id", required=True)
    retire_recover.set_defaults(func=cmd_plan_retire_recover)
    closeout_check = plan_sub.add_parser("closeout-check")
    closeout_check.add_argument("--evidence-manifest")
    closeout_check.set_defaults(func=cmd_plan_closeout_check)
    complete = plan_sub.add_parser("complete")
    complete.add_argument("--expected-revision", type=int)
    complete.add_argument("--expected-state-sequence", type=int)
    complete.add_argument("--evidence-manifest")
    complete.add_argument("--finalize-route", action="store_true")
    complete.add_argument("--confirmation")
    add_current_intake_args(complete)
    complete.set_defaults(func=cmd_plan_complete)
    revise = plan_sub.add_parser("revise")
    revise.add_argument("--expected-revision", type=int, required=True)
    revise.add_argument("--confirmation")
    revise.add_argument("--status")
    revise.add_argument("--mode", choices=["autonomous", "strict"])
    revise.add_argument("--include", action="append", default=[])
    revise.add_argument("--remove-exclude", action="append", default=[])
    revise.add_argument("--patch-file")
    revise.add_argument("--body-file")
    revise.set_defaults(func=cmd_plan_revise)
    edit = plan_sub.add_parser("edit")
    edit.add_argument("--expected-revision", type=int, required=True)
    edit.add_argument("--confirmation")
    edit.add_argument("--status")
    edit.add_argument("--mode", choices=["autonomous", "strict"])
    edit.add_argument("--include", action="append", default=[])
    edit.add_argument("--remove-exclude", action="append", default=[])
    edit.add_argument("--patch-file")
    edit.add_argument("--body-file")
    edit.set_defaults(func=cmd_plan_revise)
    confirm = plan_sub.add_parser("confirm")
    confirm.add_argument("--confirmation-id", required=True)
    confirm.add_argument("--decision", choices=["accepted", "declined"], default="accepted")
    confirm.add_argument("--ref", required=True)
    confirm.add_argument("--evidence-sha256")
    confirm.add_argument("--expected-revision", type=int, required=True)
    add_current_intake_args(confirm)
    confirm.set_defaults(func=cmd_plan_confirm)
    confirmation = plan_sub.add_parser("confirmation")
    confirmation_sub = confirmation.add_subparsers(
        dest="confirmation_action",
        required=True,
    )
    confirmation_add = confirmation_sub.add_parser("add")
    confirmation_add.add_argument("--confirmation-id", required=True)
    confirmation_add.add_argument("--description", required=True)
    confirmation_add.add_argument(
        "--status",
        default="pending",
    )
    confirmation_add.add_argument("--ref")
    confirmation_add.add_argument(
        "--intervention-kind",
        choices=sorted(INTERVENTION_KINDS),
        required=True,
    )
    confirmation_add.add_argument("--blocks", action="append", required=True)
    confirmation_add.add_argument("--basis-ref", required=True)
    confirmation_add.add_argument("--basis-sha256")
    confirmation_add.add_argument(
        "--action-kind",
        choices=sorted(HIGH_IMPACT_ACTION_KINDS),
    )
    confirmation_add.add_argument("--expected-revision", type=int, required=True)
    confirmation_add.set_defaults(func=cmd_plan_confirmation_add)
    confirmation_classify = confirmation_sub.add_parser("classify")
    confirmation_classify.add_argument("--manifest", required=True)
    confirmation_classify.add_argument("--expected-revision", type=int, required=True)
    confirmation_classify.set_defaults(func=cmd_plan_confirmation_classify)
    independent_review = plan_sub.add_parser("independent-review")
    independent_review_sub = independent_review.add_subparsers(
        dest="independent_review_action",
        required=True,
    )
    independent_review_record = independent_review_sub.add_parser("record")
    independent_review_record.add_argument("--manifest", required=True)
    independent_review_record.add_argument("--expected-revision", type=int, required=True)
    add_current_intake_args(independent_review_record)
    independent_review_record.set_defaults(func=cmd_plan_independent_review_record)
    verify_entry = plan_sub.add_parser("verify-entry")
    verify_entry.add_argument("--field", choices=["obligations", "validations"], required=True)
    verify_entry.add_argument("--entry-id", required=True)
    verify_entry.add_argument("--confirmation", required=True)
    verify_entry.add_argument("--evidence-manifest")
    verify_entry.add_argument("--evidence-ref")
    verify_entry.add_argument("--evidence-sha256")
    verify_entry.add_argument("--expected-revision", type=int, required=True)
    add_current_intake_args(verify_entry)
    verify_entry.set_defaults(func=cmd_plan_verify_entry)
    artifact_state = plan_sub.add_parser("artifact-state")
    artifact_state.add_argument("--artifact-id", required=True)
    artifact_state.add_argument(
        "--state",
        choices=["suspect", "quarantined", "rollback-pending"],
        required=True,
    )
    artifact_state.add_argument("--confirmation")
    artifact_state.add_argument("--evidence-manifest")
    artifact_state.add_argument("--evidence-ref")
    artifact_state.add_argument("--evidence-sha256")
    artifact_state.add_argument("--expected-revision", type=int, required=True)
    artifact_state.set_defaults(func=cmd_plan_artifact_state)
    finalize_artifact = plan_sub.add_parser("finalize-artifact")
    finalize_artifact.add_argument("--artifact-id", required=True)
    finalize_artifact.add_argument("--task-id", required=True)
    finalize_artifact.add_argument("--confirmation", required=True)
    finalize_artifact.add_argument("--evidence-manifest")
    finalize_artifact.add_argument("--evidence-ref")
    finalize_artifact.add_argument("--evidence-sha256")
    finalize_artifact.add_argument("--expected-revision", type=int, required=True)
    add_current_intake_args(finalize_artifact)
    finalize_artifact.set_defaults(func=cmd_plan_finalize_artifact)
    delivery_complete = plan_sub.add_parser("delivery-complete")
    delivery_complete.add_argument("--confirmation", required=True)
    delivery_complete.add_argument("--evidence-manifest")
    delivery_complete.add_argument("--evidence-ref")
    delivery_complete.add_argument("--evidence-sha256")
    delivery_complete.add_argument("--expected-revision", type=int, required=True)
    add_current_intake_args(delivery_complete)
    delivery_complete.set_defaults(func=cmd_plan_delivery_complete)
    activation_repair = plan_sub.add_parser("activation-repair")
    activation_repair.add_argument("--task-id", required=True)
    activation_repair.add_argument("--target-ref", required=True)
    activation_repair.add_argument("--confirmation", required=True)
    activation_repair.add_argument("--expected-revision", type=int, required=True)
    add_current_intake_args(activation_repair)
    activation_repair.set_defaults(func=cmd_plan_activation_repair)
    activation_promote = plan_sub.add_parser("activation-promote")
    activation_promote.add_argument(
        "--state",
        choices=["in_progress", "active"],
        required=True,
    )
    activation_promote.add_argument("--target-ref")
    activation_promote.add_argument("--confirmation", required=True)
    activation_promote.add_argument("--evidence-manifest")
    activation_promote.add_argument("--evidence-ref")
    activation_promote.add_argument("--evidence-sha256")
    activation_promote.add_argument("--expected-revision", type=int, required=True)
    add_current_intake_args(activation_promote)
    activation_promote.set_defaults(func=cmd_plan_activation_promote)

    task = sub.add_parser("task")
    task_sub = task.add_subparsers(dest="action", required=True)
    for action, status_value in {
        "start": "in_progress",
        "block": "blocked",
        "unblock": "in_progress",
        "verify": "verified",
        "skip": "skipped",
    }.items():
        item = task_sub.add_parser(action)
        item.add_argument("--task-id", required=True)
        item.add_argument("--expected-revision", type=int)
        item.add_argument("--expected-state-sequence", type=int)
        item.add_argument("--note")
        if action == "verify":
            task_evidence = item.add_mutually_exclusive_group()
            task_evidence.add_argument("--evidence-manifest")
            task_evidence.add_argument(
                "--evidence-stdin",
                action="store_true",
                help="Record bounded evidence from standard input atomically with verification.",
            )
        if action != "block":
            add_current_intake_args(item)
        else:
            item.set_defaults(
                turn_receipt_sha256=None,
                expected_intake_sha256=None,
            )
        item.set_defaults(
            func=lambda args, value=status_value, handler=set_task_status: handler(args, value)
        )
    done = task_sub.add_parser("done")
    done.add_argument("--task-id", required=True)
    done.add_argument("--expected-revision", type=int)
    done.add_argument("--expected-state-sequence", type=int)
    done.add_argument("--note")
    done.add_argument("--kind", default="task-done")
    done.add_argument("--summary")
    done.add_argument("--idempotency-key")
    done_source = done.add_mutually_exclusive_group()
    done_source.add_argument("--evidence-stdin", action="store_true")
    done_source.add_argument("--evidence-from-file", dest="evidence_from_file")
    done_source.add_argument("--from-file", dest="evidence_from_file")
    done_source.add_argument("--evidence-ref")
    done.add_argument("--evidence-sha256")
    add_current_intake_args(done)
    done.set_defaults(func=cmd_task_done)
    reprioritize = task_sub.add_parser("reprioritize")
    reprioritize.add_argument("--task-id", required=True)
    reprioritize.add_argument("--priority", type=int, required=True)
    reprioritize.add_argument("--expected-state-sequence", type=int, required=True)
    reprioritize.set_defaults(func=cmd_task_reprioritize)

    worktree = sub.add_parser("worktree")
    worktree_sub = worktree.add_subparsers(dest="worktree_action", required=True)
    worktree_begin = worktree_sub.add_parser("begin")
    worktree_begin.add_argument("--worktree-id", required=True)
    worktree_begin.add_argument("--path", required=True)
    worktree_begin.add_argument("--branch", required=True)
    worktree_begin.add_argument("--summary", required=True)
    worktree_begin.set_defaults(func=cmd_worktree_begin)
    worktree_record = worktree_sub.add_parser("record")
    worktree_record.add_argument("--worktree-id", required=True)
    worktree_record.add_argument("--event", required=True)
    worktree_record.add_argument("--summary", required=True)
    worktree_record.add_argument("--evidence-ref")
    worktree_record.add_argument("--evidence-sha256")
    worktree_record.set_defaults(func=cmd_worktree_record)
    worktree_close = worktree_sub.add_parser("close")
    worktree_close.add_argument("--worktree-id", required=True)
    worktree_close.add_argument("--summary", required=True)
    worktree_close.add_argument("--evidence-ref")
    worktree_close.add_argument("--evidence-sha256")
    worktree_close.set_defaults(func=cmd_worktree_close)
    worktree_merge = worktree_sub.add_parser("merge")
    worktree_merge_sub = worktree_merge.add_subparsers(
        dest="worktree_merge_action",
        required=True,
    )
    worktree_merge_inspect = worktree_merge_sub.add_parser("inspect")
    worktree_merge_inspect.add_argument("--worktree-id", required=True)
    worktree_merge_inspect.set_defaults(func=cmd_worktree_merge_inspect)

    log = sub.add_parser("log")
    log_sub = log.add_subparsers(dest="action", required=True)
    append = log_sub.add_parser("append")
    append.add_argument("--kind", required=True)
    append.add_argument("--message", required=True)
    append.add_argument("--expected-revision", type=int, required=True)
    append.set_defaults(func=cmd_log_append)
    return parser
