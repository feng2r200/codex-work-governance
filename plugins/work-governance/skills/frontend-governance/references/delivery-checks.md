# Frontend Delivery Checks

Use these examples to clarify the current slice, not as a compulsory form or
full-application checklist. The contract can remain in task context for a small
change; ongoing state follows the selected provider and project authority.

## Reference Applicability

Retain only what affects this delivery:

- reference locator and revision, timestamp, or other capture basis;
- affected routes, components, and user tasks;
- whether the source establishes visual, interaction, or business behavior;
- approved differences and unknown behavior;
- promised delivery level and allowed sample or dependency mode; and
- the observation that can distinguish completion from a plausible shortcut.

For example, a supplied dashboard Demo may govern filter interaction and panel
layout while the application's API contract governs saving. A screenshot of
an Export button establishes its placement, not its file format or permissions.
Discover those facts from current requirements or ask only when the unresolved
choice is material. Do not manufacture a backend requirement for an explicitly
local interactive prototype, or downgrade an integrated application to one.

## Example Obligations

| Obligation | Stimulus | Observable result | Weak evidence to challenge |
| --- | --- | --- | --- |
| Search and clear | Enter a known matching query, then clear it | Expected records appear and the allowed baseline returns | Input or button style changes without filtering |
| Save with persistence | Edit, save, then reopen or reload as the contract requires | The saved values are read from the promised state owner | A toast with no state change, or only temporary local state |
| Local prototype save | Edit and save within an explicitly local prototype | Prototype state changes within its disclosed lifetime | A claim of backend persistence |
| Export selected data | Select a known subset and export | A usable file with correct records, fields, and scope | A download exists but contains empty or wrong business data |
| Request failure | Trigger an allowed controlled failure | Truthful error, valid recovery, no false success | Permanent loading, swallowed errors, or a success message |
| Product copy | Reach affected normal and error states | Product help remains; development narration is absent | Deleting a note while keeping its fake action |
| Responsive or shared change | Reach affected consumers in relevant supported layouts | Required controls remain usable and focus behavior is preserved | One screenshot of an unaffected viewport |

Persistent or external effects belong in the contract only when promised.
An artifact's valid shape is not proof of correct data or input binding. Check
the effect and relevant business predicate, not just its existence.

## Evidence And Remaining Scope

Use the smallest evidence that can establish each obligation. Bind it to the
page, implementation basis, data or fixture, dependency mode, and viewport or
state when relevant. A compact mapping can use:

| Required behavior | Reference or contract | Observed result and evidence | Outcome or remaining check |
| --- | --- | --- | --- |

Missing rendering access means the rendered obligation remains unverified.
Mocked success stays within the mock boundary. Approved differences need the
actual approval and changed requirement; an implementer cannot create an
exception simply by listing it in a report.

For a one-line label change, inspect that label and the relevant reachable
states. For an affected shared button, include its critical consumers. Expand
after a new change, failure, or unresolved risk, rather than repeating checks
whose evidence is still applicable.
