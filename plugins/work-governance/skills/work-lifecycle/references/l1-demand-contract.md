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

Do not treat examples, candidate designs, logs, or memory as confirmed facts.
If a future agent must obey the contract, write it into the Plan frontmatter.
If the contract is still a proposal, keep it in the reply or logs and ask for
confirmation before making it authority.

Validation standard: every must-have obligation has at least one planned check,
and each high-impact action has an explicit confirmation reference.
