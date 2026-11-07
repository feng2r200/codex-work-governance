---
name: frontend-governance
description: Use when creating, changing, or reviewing rendered frontend surfaces and reference fidelity, functional controls, product copy, or interaction acceptance matters. Covers Demo-driven implementation and existing UI changes; not backend-only work or discussion without a frontend deliverable.
---

# Frontend Governance

Keep the frontend delivery contract connected to the reference, implemented
behavior, product copy, and observed results. This Skill owns those obligations;
existing implementation, design, browser, and project Skills own their execution.
Apply only the investigation, edits, or review the current task authorizes.

## Bound The Surface And Reference

Identify the affected routes, components, user flows, and relevant project
contracts. For a reference, retain its locator and version or capture basis,
what it governs, and any already approved differences. Separate visual fidelity,
interaction behavior, and business or data semantics:

- An interactive Demo can establish observed navigation and state changes.
  Its sample data or local state does not establish a production API,
  persistence, identity, permission, or downstream-effect contract.
- A screenshot or design image establishes visible structure and copy; hidden
  behavior remains unknown until requirements or observations establish it.
- With no supplied reference, use the user's intended task, current product
  contracts, and existing components and design conventions. Absence of a
  design file does not authorize redesign or stack migration.

Establish the promised delivery level: visual prototype, interactive prototype,
or integration with the specified dependencies. Use sample data or mocks only
inside the allowed boundary and preserve necessary sample-data disclosures.
Do not silently lower the promised level when a dependency is unavailable.

Investigate discoverable gaps first. Preserve an explicit user choice of
contract or scope, and apply a conflicting reference only to its remaining
compatible aspects. Do not reopen that choice merely because the reference
differs. Route only a remaining material conflict or missing product choice
through [Goal Discovery](../goal-discovery/SKILL.md); use
[Project Truth Governance](../project-truth-governance/SKILL.md) when choosing
which source governs a claim. A selected Demo cannot silently override an
explicit business contract. Continue independent work while a choice is pending.

## Preserve Named Actions And Their Effects

For affected required behavior, establish the entry, user action, expected
observable result, and relevant data or dependency boundary. Include affected
shared consumers and critical adjacent regressions; do not inventory the whole
application for a local change. Keep approved navigation, controls, content,
and flows unless the current scope includes changing them.

Required controls must perform their promised action. Do not substitute static
results, fake progress, a toast, decorative interactivity, or explanatory text.
Do not remove a required control or relabel it optional to hide missing behavior.
An approved visual-only prototype may omit behavior; that exception does not
make a nonfunctional control a completed interactive feature.

Observe results where the promise can be falsified: filtered records, reopened
saved values when persistence is required, a downloaded file's actual contents,
or the relevant dependency effect. A success message alone is insufficient.
Choose loading, empty, error/recovery, disabled, responsive, focus, and keyboard
checks according to the changed surface and risk, rather than adding every
possible state to every edit. Use [Problem Discovery](../problem-discovery/SKILL.md)
when the coverage or result oracle needs a stronger challenge.

## Keep Copy In The Product's Audience

Product screens contain content a real end user needs to understand the domain,
perform an action, or interpret the current state. Keep useful help, onboarding,
validation, errors, status messages, and truthful sample-data labels.

Task interpretation, implementation plans, debug narration, prompt fragments,
acceptance notes, and delivery summaries belong in the conversation or appropriate
project records. Do not put them in the product UI unless that surface explicitly
requires such content for its users.

Inspect changed source strings and rendered text in relevant reachable states.
Search terms can identify candidates; audience and purpose decide whether copy
belongs. Do not use a keyword blacklist to delete legitimate product explanations.
Removing a development note does not repair the missing function it described;
verify copy and behavior as separate obligations.

## Verify The Promised Slice

Bind observations to the actual page or route, implementation revision, data or
fixture, dependency mode, and relevant viewport and state. Compare reference and
implementation under comparable conditions. Reuse evidence while that basis
remains applicable; reopen only affected checks after a relevant change.

Exercise every required interaction promised or affected by this slice, with
an observation of its result. A single smoke interaction cannot establish a
multi-flow delivery. Cover relevant runtime errors, layout, and accessibility
alongside those results. Source inspection, builds, screenshots, interactions,
and real integration each establish different claims; report their boundaries.

Use available project checks and the current browser or design Skill's routing
and fallback rules. This Skill does not select a universal browser, framework,
viewport, dependency, or test runner, and does not authorize installation or
external effects. If rendering or reference access is blocked, retain the exact
unverified obligation and continue independent safe work. Do not reinterpret a
build or HTTP response as successful browser acceptance.

Resolve each required obligation as verified, failed, unverified, or changed
by an explicitly approved difference. Keep failures and unknowns visible;
completion requires the remaining required obligations to be satisfied or the
user to approve the scope change. Use [Work Reporting](../work-reporting/SKILL.md)
for the final account rather than imposing a frontend-specific report template.

## Keep The Contract Small

A local copy or style repair needs only its affected surface and adjacent
checks. A new page, shared component, or multi-route flow may need a broader
contract. Neither case automatically requires a Plan, full-site capture,
independent reviewer, new design system, fixed document, or confirmation at
each step. Reuse current project authority and the selected durable state
provider instead of creating another mutable contract or execution ledger.

Read [Delivery Checks](references/delivery-checks.md) when reference boundaries
or concrete acceptance examples would help; do not load it for every simple edit.
