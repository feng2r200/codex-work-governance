"""Closeout readiness and terminal completion commands."""

from __future__ import annotations

# Controller infrastructure is bound by name for each command execution.
# ruff: noqa: F821
import argparse
import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

from workctl_modules.kernel.bindings import call_with_bound_globals


def call(bindings: Mapping[str, Any], function: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a closeout helper with controller infrastructure bound."""
    return call_with_bound_globals(globals(), bindings, function, *args, **kwargs)


def incomplete_entries(frontmatter: dict[str, Any], field: str) -> list[str]:
    """Return IDs for work entries that are not verified or skipped."""
    return module_incomplete_entries(frontmatter, field, VERIFIED_TASK_STATES)


def unresolved_exclusions(frontmatter: dict[str, Any]) -> list[str]:
    """Return schema-v3 exclusions that still require route disposition."""
    return module_unresolved_exclusions(frontmatter, BLOCKING_EXCLUSION_DISPOSITIONS)


def completion_claims(
    frontmatter: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    """Describe which completion claims current evidence permits."""
    if module_completion_claims is None:
        raise WorkctlError("STATUS_MODULE_UNAVAILABLE: completion_claims")

    def incomplete_ids(document: Mapping[str, object], field: str) -> Sequence[str]:
        return incomplete_entries(cast(dict[str, Any], document), field)

    def confirmation_lookup(
        document: Mapping[str, object],
    ) -> Mapping[str, Mapping[str, object]]:
        return cast(
            Mapping[str, Mapping[str, object]],
            confirmations(cast(dict[str, Any], document)),
        )

    return cast(
        dict[str, Any],
        module_completion_claims(
            frontmatter,
            readiness,
            incomplete_entry_ids=incomplete_ids,
            confirmations_by_id=confirmation_lookup,
            verified_task_states=VERIFIED_TASK_STATES,
        ),
    )


def closeout_readiness(
    frontmatter: dict[str, Any],
    report: AuthorityReport,
    validation_errors: list[str] | None = None,
) -> dict[str, Any]:
    """Compute complete-route readiness without mutating the Plan."""
    blockers: list[str] = []
    blockers.extend(f"plan validation: {error}" for error in (validation_errors or []))
    if report.state != "GOVERNED_ACTIVE":
        blockers.append(f"authority state is {report.state}")
    for field in ("obligations", "tasks", "validations"):
        for entry_id in incomplete_entries(frontmatter, field):
            blockers.append(f"{field} not complete: {entry_id}")
    raw_unknowns = frontmatter.get("unknowns", [])
    if not isinstance(raw_unknowns, list):
        blockers.append("unknowns is invalid")
    else:
        for unknown in raw_unknowns:
            if isinstance(unknown, dict) and unknown.get("status") == "open":
                blockers.append(f"unknown remains open: {unknown.get('id', 'unknown')}")
    artifacts = frontmatter.get("artifacts", [])
    if not isinstance(artifacts, list):
        blockers.append("artifacts is invalid")
    else:
        for artifact in artifacts:
            if not isinstance(artifact, dict) or artifact.get("status") != "final":
                artifact_id = (
                    artifact.get("id", "unknown") if isinstance(artifact, dict) else "invalid"
                )
                blockers.append(f"artifact not final: {artifact_id}")
    if frontmatter.get("schema_version") in {3, 4}:
        delivery = frontmatter.get("delivery", {})
        if not isinstance(delivery, dict) or delivery.get("status") != "complete":
            blockers.append("delivery is not complete")
        activation = frontmatter.get("activation", {})
        if isinstance(activation, dict) and activation.get("status") in BLOCKING_ACTIVATION_STATES:
            blockers.append(f"activation is {activation.get('status')}")
        for description in unresolved_exclusions(frontmatter):
            blockers.append(f"scope exclusion is unresolved: {description}")
    if frontmatter.get("schema_version") == 4:
        if STRICT_INITIAL_INTAKE_REQUIRED:
            current_intake_state = intake_state(frontmatter)
            if current_intake_state != "CURRENT_BASIS":
                blockers.append(f"intake is {current_intake_state}")
        for unknown_id in legacy_unknown_ids(frontmatter):
            blockers.append(f"legacy unknown contract: {unknown_id}")
        intervention_state = intervention_contract_state(frontmatter)
        if intervention_state != "STRICT_READY":
            blockers.append(f"intervention contract is {intervention_state}")
    for mode in independent_review_blockers(project_root(), frontmatter, "route"):
        blockers.append(f"independent review blocks route: {mode}")
    raw_confirmations = frontmatter.get("confirmations", {})
    if not isinstance(raw_confirmations, dict):
        blockers.append("confirmations is invalid")
    else:
        for item in raw_confirmations.get("required", []):
            if not isinstance(item, dict) or not confirmation_resolved_for_closeout(
                frontmatter, item
            ):
                confirmation_id = item.get("id", "unknown") if isinstance(item, dict) else "invalid"
                blockers.append(f"confirmation unresolved: {confirmation_id}")
    route = frontmatter.get("route", {})
    if not isinstance(route, dict):
        blockers.append("route is invalid")
    else:
        if route.get("route_status") != "terminal":
            blockers.append("route_status is not terminal")
        if route.get("next_phase") not in {"", "none"}:
            blockers.append("next_phase remains")
        if route.get("confirmation_gate") not in {"", "none"}:
            blockers.append("confirmation_gate remains")
    handoff = frontmatter.get("handoff", {})
    if not isinstance(handoff, dict):
        blockers.append("handoff is invalid")
    else:
        if handoff.get("route_status") != "terminal":
            blockers.append("handoff route_status is not terminal")
        if handoff.get("next_step") not in {"", "none"}:
            blockers.append("handoff next_step remains")
    return {"ready": not blockers, "blockers": blockers}


def cmd_plan_closeout_check(args: argparse.Namespace) -> None:
    """Print closeout readiness and fail when obligations remain."""
    root = project_root()
    report = inspect_authority(root)
    doc = load_plan(active_plan_path(root))
    validation_errors = validate_plan(root)
    if doc.frontmatter.get("schema_version") == 5:
        v5_recover_pending_event(root, doc.frontmatter)
        readiness = v5_runtime_closeout_readiness(
            root,
            doc.frontmatter,
            report,
            validation_errors,
        )
    else:
        readiness = closeout_readiness(doc.frontmatter, report, validation_errors)
    if doc.frontmatter.get("schema_version") == 4:
        if not args.evidence_manifest:
            readiness["ready"] = False
            readiness["blockers"].append("closeout evidence manifest required")
        else:
            try:
                verify_evidence_manifest(
                    root,
                    args.evidence_manifest,
                    plan_id=str(doc.frontmatter["plan_id"]),
                    subject="closeout",
                )
            except WorkctlError as exc:
                readiness["ready"] = False
                readiness["blockers"].append(str(exc))
    print(json.dumps(readiness, indent=2, sort_keys=True))
    if not readiness["ready"]:
        raise SystemExit(1)


def v5_closeout_evidence(
    root: Any,
    frontmatter: dict[str, Any],
    state: dict[str, Any],
    evidence_manifest: str | None,
) -> tuple[str, str]:
    """Return or create the canonical v5 closeout evidence record."""
    plan_id = str(frontmatter["plan_id"])
    if evidence_manifest:
        return verify_evidence_manifest(
            root,
            evidence_manifest,
            plan_id=plan_id,
            subject="closeout",
        )
    items: list[dict[str, str]] = []
    state_tasks = state.get("tasks", {})
    for task in frontmatter.get("tasks", []):
        if not isinstance(task, dict) or not isinstance(task.get("id"), str):
            continue
        state_task = state_tasks.get(task["id"]) if isinstance(state_tasks, dict) else None
        if not isinstance(state_task, dict):
            continue
        evidence_ref = state_task.get("evidence_ref")
        evidence_sha256 = state_task.get("evidence_sha256")
        if isinstance(evidence_ref, str) and isinstance(evidence_sha256, str):
            items.append({"ref": evidence_ref, "sha256": evidence_sha256})
    if not items:
        raise WorkctlError("CLOSEOUT_EVIDENCE_ITEMS_REQUIRED")
    return record_evidence_payload(
        root,
        plan_id=plan_id,
        payload={
            "schema_version": 1,
            "kind": "work-governance-evidence",
            "plan_id": plan_id,
            "subject": "closeout",
            "created_at": utc_now(),
            "producer_ref": "runtime:workctl/plan-complete",
            "items": items,
        },
        expected_subject="closeout",
    )


def cmd_plan_complete(args: argparse.Namespace) -> None:
    """Mark a Plan complete, optionally finalizing a ready route atomically."""
    root = project_root()
    with lock(root):
        report = require_governed_authority(root)
        doc = load_plan(active_plan_path(root))
        if doc.frontmatter.get("schema_version") == 5:
            v5_recover_pending_event(root, doc.frontmatter)
            state = load_v5_state(root, doc.frontmatter)
            require_v5_expected_state_sequence(state, args.expected_state_sequence)
            require_independent_target(root, doc.frontmatter, "route")
            validation_errors = validate_plan(root)
            readiness = v5_runtime_closeout_readiness(
                root,
                doc.frontmatter,
                report,
                validation_errors,
                state,
            )
            if not readiness["ready"]:
                raise WorkctlError(
                    "CLOSEOUT_BLOCKED: " + "; ".join(str(item) for item in readiness["blockers"])
                )
            evidence_ref, evidence_sha256 = v5_closeout_evidence(
                root,
                doc.frontmatter,
                state,
                args.evidence_manifest,
            )
            doc.frontmatter["status"] = "complete"
            doc.frontmatter["updated_at"] = utc_now()
            doc.frontmatter["completion"] = {
                "state_sequence": state["state_sequence"],
                "completed_at": doc.frontmatter["updated_at"],
                "evidence_ref": evidence_ref,
                "evidence_sha256": evidence_sha256,
            }
            require_valid_candidate(doc)
            v5_persist_contract_transition(
                root,
                doc,
                event="plan.completed",
                subject=f"plan:{doc.frontmatter['plan_id']}",
                payload={
                    "state_sequence": state["state_sequence"],
                    "status": "complete",
                    "evidence_ref": evidence_ref,
                    "evidence_sha256": evidence_sha256,
                    "evidence_manifest": args.evidence_manifest,
                },
            )
            release_v5_active_index(root, str(doc.frontmatter["plan_id"]))
            print(f"PLAN_COMPLETED state_sequence={state['state_sequence']} active_released=true")
            return
        require_expected_revision(doc.frontmatter, args.expected_revision)
        require_current_intake(
            root,
            doc.frontmatter,
            turn_receipt_sha256=args.turn_receipt_sha256,
            expected_intake_sha256=args.expected_intake_sha256,
            targets=["route"],
        )
        evidence_ref: str | None = None
        evidence_sha256: str | None = None
        if doc.frontmatter.get("schema_version") == 4:
            if not args.evidence_manifest:
                raise WorkctlError("EVIDENCE_MANIFEST_REQUIRED")
            evidence_ref, evidence_sha256 = verify_evidence_manifest(
                root,
                args.evidence_manifest,
                plan_id=str(doc.frontmatter["plan_id"]),
                subject="closeout",
            )
        require_independent_target(root, doc.frontmatter, "route")
        if args.confirmation and not args.finalize_route:
            raise WorkctlError("FINALIZE_ROUTE_REQUIRED_FOR_CONFIRMATION")
        finalized_atomically = False
        atomic_intake_history: tuple[list[dict[str, Any]], dict[str, object]] | None = None
        if args.finalize_route:
            require_slice_revision_confirmation(
                doc.frontmatter,
                args.confirmation,
                {"accepted", "declined"},
            )
            route = doc.frontmatter.get("route")
            handoff = doc.frontmatter.get("handoff")
            if not isinstance(route, dict) or not isinstance(handoff, dict):
                raise WorkctlError("INVALID_TERMINAL_ROUTE")
            route["route_status"] = "terminal"
            route["slice_status"] = "complete"
            route["next_phase"] = "none"
            route["confirmation_gate"] = "none"
            handoff["route_status"] = "terminal"
            handoff["next_step"] = "none"
            if STRICT_INITIAL_INTAKE_REQUIRED:
                atomic_intake_history = refresh_intake_for_atomic_controller_transition(
                    doc.frontmatter
                )
            doc.frontmatter["status"] = "complete"
            if evidence_ref is not None and evidence_sha256 is not None:
                doc.frontmatter["completion_evidence"] = {
                    "ref": evidence_ref,
                    "sha256": evidence_sha256,
                    "completed_at": utc_now(),
                }
            bump_revision(
                doc.frontmatter,
                confirmation_id=args.confirmation,
                evidence_manifest=evidence_ref,
                rationale="Atomically finalize the route and complete the Plan.",
            )
            finalized_atomically = True
            validation_errors = validate_frontmatter(
                doc.frontmatter,
                reject_blocking_artifacts=True,
            )
        else:
            validation_errors = validate_plan(root)
        readiness = closeout_readiness(doc.frontmatter, report, validation_errors)
        if not readiness["ready"]:
            raise WorkctlError(
                f"CLOSEOUT_BLOCKED: {'; '.join(str(item) for item in readiness['blockers'])}"
            )
        if not finalized_atomically:
            doc.frontmatter["status"] = "complete"
            if evidence_ref is not None and evidence_sha256 is not None:
                doc.frontmatter["completion_evidence"] = {
                    "ref": evidence_ref,
                    "sha256": evidence_sha256,
                    "completed_at": utc_now(),
                }
            bump_revision(
                doc.frontmatter,
                evidence_manifest=evidence_ref,
                rationale="Complete the Plan after evidence-bound closeout.",
            )
        if atomic_intake_history is not None:
            prior_records, refreshed_record = atomic_intake_history
            plan_id = str(doc.frontmatter["plan_id"])
            for prior in prior_records:
                persist_intake_history_record(root, plan_id, prior)
            persist_intake_history_record(root, plan_id, refreshed_record)
        require_valid_candidate(doc)
        write_atomic(doc.path, dump_plan(doc))
        print(f"PLAN_COMPLETED revision={doc.frontmatter['revision']}")
