---
name: project-archive-curation
description: Use when reviewing completed project work or conversations for archival, deciding what knowledge must be retained first, and separating durable work records, shared project context, project authority, and raw history. Do not use for ordinary file backup or storage cleanup.
---

# Project Archive Curation

Curate useful project knowledge before completed work leaves the active view.
This skill decides retention and archive readiness; host and persistence Skills
own their own inspection, write, publication, and archive mechanics.

## Establish The Review Boundary

Identify the target project, relevant period, included work or conversation
kinds, and the outcome the review should preserve. Distinguish four different
requests:

- read-only inventory and recommendation;
- durable capture or source drafting;
- publication, import, or readback verification; and
- archival of exact completed items.

Authority for one does not grant the next. Exclude the current curation work
unless it later reaches a terminal outcome and is reviewed separately.

## Inventory From The Owning Surface

Use the current project host or index as authority for project membership and
archive state. A local mirror, transcript directory, memory entry, or
persistence registry may supply evidence, but its absence does not prove that
the project or its history is empty.

For each candidate, inspect enough of its real outcome to recover:

- the intended result and whether it was actually delivered;
- material findings, decisions, attempts, and validation;
- open questions, risks, follow-up work, and superseded conclusions;
- current artifacts and the authority that now governs them; and
- stable provenance such as work, conversation, artifact, or record IDs.

Do not infer archive readiness from a title or UI status alone. Keep different
item kinds separate when their ownership, visibility, or archive mechanisms
differ.

## Choose The Retention Layer

Place each retained fact in the layer that serves its future consumer:

- **Project authority:** use project-native contracts, architecture, domain,
  or operations documents for rules that people and tools are expected to
  obey.
- **Durable work memory:** use an available persistence capability for scoped
  findings, decisions, questions, risks, attempts, evidence, reusable
  knowledge, and justified semantic relations.
- **Shared project context:** use a concise audience-facing source or snapshot
  when future project conversations need the context without invoking the
  persistence capability.
- **Raw history:** keep the original completed conversation or work item as
  archived provenance rather than turning its full transcript into current
  guidance.

These layers may link to one another, but they must not become competing
mutable authorities. Reuse existing durable records and authoritative
documents instead of restating them. Keep shared context as a thin projection
with an `as_of` point, original IDs, current/historical/superseded/open status,
authority links, and known drift checks.

Load a persistence-tool Skill only when existing state can change the curation
decision or a valuable record is ready to capture. A read-only audit must not
initialize persistence, create a Plan, or bind an ambient mirror merely because
no existing binding is found. Historical work that predates durable capture
may need one bounded curation pass; missing records are not evidence that the
work had no durable value.

## Decide Archive Readiness

Classify each candidate as `archive-ready`, `retain-first`, `keep-active`, or
`insufficient-evidence`. An item is archive-ready only when:

- its relevant work is terminal or its successor is explicit;
- its deliverable and current authority are identified;
- valuable cognition is already retained, or the review explicitly concludes
  that nothing durable should be promoted;
- unresolved obligations have a current owner or durable destination;
- provenance remains recoverable after the item leaves the active view; and
- any published shared context has been read back when publication accuracy
  matters.

Archive readiness is not a completion claim for the underlying product,
deployment, migration, or follow-up work.

## Produce A Coverage Map

For non-trivial reviews, map each candidate's stable ID and kind to its outcome,
open obligations, current authority, durable records, shared context, evidence,
and archive classification. Keep the format proportional; a small case does
not need a large template.

The map should make gaps visible before mutation. In particular, show when an
existing record already covers the semantic result, when a one-time curation
is still needed, and when a proposed source would merely duplicate authority.

## Keep Confirmation Gates Separate

After the read-only review, request only the smallest next authorization that
has a clear consumer and validation boundary. Keep these gates independent:

1. persist durable cognition or draft shared context;
2. publish or import the shared context;
3. read back and verify the published result; and
4. archive the exact approved items.

Report candidates and exclusions, selected retention layers, unresolved gaps
or conflicts, verification performed, and the precise next gate. Do not imply
that drafting, capture, or successful readback authorized archival.
