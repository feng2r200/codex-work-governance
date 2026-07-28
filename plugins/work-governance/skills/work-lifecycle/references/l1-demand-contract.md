# L1 Demand Contract

Turn the request into an obligation set before implementation.

Define:

- target result: the user-visible or handoff-visible end state;
- included scope and explicit no-go boundaries;
- required artifacts and affected authority locations;
- obligations `O-###`;
- task slices `T-###` that each have a verification point;
- validations `V-###` that directly prove obligations;
- artifacts `A-###` and their expected, suspect, quarantined, or final state;
- confirmation gates for high-impact choices.

Give every planned validation a provenance class:

- a confirmed obligation;
- an observed failure;
- a code invariant;
- a supported integration boundary.

Do not invent hypothetical use cases merely to increase case count. Coverage
percentage, test count, and matrix size cannot substitute for the acceptance
evidence named by the target result. Prefer the smallest validation set that
can discriminate the important failure modes, then add cases only when new
evidence exposes a real gap.

Classify every scope exclusion. In schema-v4 Plans, use a structured
`disposition`:

- `not_required` or `forbidden` with the confirming authority reference;
- `deferred` when it remains part of the future route;
- `pending_confirmation` with a confirmation ID when the action lacks current
  authority;
- `transferred` with an owner, handoff reference, and the confirming resolution
  reference.

Do not turn missing authorization into a plain exclusion. When local delivery
can finish before a runtime, production, publication, or live-plugin change,
define delivery and activation separately and preserve the activation decision
as a route-level gate.

Do not treat examples, candidate designs, logs, or memory as confirmed facts.
If a future agent must obey the contract, write it into the Plan frontmatter.
If the contract is still a proposal, keep it in the reply or logs and ask for
confirmation before making it authority.

Validation standard: every must-have obligation has at least one planned check,
each check has a provenance class, and each high-impact action has an explicit
confirmation reference.
