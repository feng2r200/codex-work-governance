# L6 Closeout and Handoff

Close out by separating local completion, route status, and remaining gates.

Report:

- changed files and delivery boundary;
- obligations covered and the check for each;
- validation commands and key outputs;
- unverified areas and residual risks;
- Git status, commit hash, and excluded files when Git was used;
- whether the formal next step is action, verification, confirmation, or none.

Do not claim complete when:

- verification was skipped, failed, or only adjacent;
- any must obligation lacks evidence;
- any required confirmation is missing;
- suspect, quarantined, or rollback-pending artifacts remain;
- live switch or remote mutation remains unconfirmed.

Use this final line only when accurate for the current scope:

`本轮已完成，暂无必须下一步`

If a route continues beyond the local slice, distinguish:

- local slice next step;
- route-level next step;
- confirmation gate and validation standard.
