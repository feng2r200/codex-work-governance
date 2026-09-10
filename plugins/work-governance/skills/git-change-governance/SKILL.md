---
name: git-change-governance
description: Govern Git branch and worktree choice, dirty-state protection, staging scope, local commit grouping, push boundaries, and rollback-safe handoff.
---

# Git Change Governance

Load `work-governance:work-lifecycle` first. This skill owns only the Git
boundary; lifecycle owns the goal, authority, evidence, and final claim.

## Isolation

Protect `main` and `master` by default. Prefer an existing isolated branch or
managed worktree for substantive changes. Use the current attached worktree
when it is already isolated and the dirty state belongs to the same delivery
boundary.

When a new Codex-managed worktree is needed, choose the location in this order:

1. current attached or already managed worktree;
2. explicit user or project path;
3. Codex configured `git-worktree-root`;
4. Codex official default `$CODEX_HOME/worktrees`.

Do not default to a project-local `.work-governance/worktrees` path. Historical
registered worktrees may remain where Git already knows them, but new creation
follows the priority above.

Worktree placement does not choose branch semantics. Attach an existing branch
only when that exact branch was selected. Create a branch only from an explicit
and verified start point. Use detached mode only when the task calls for it.

## Dirty State

Before Git mutation, inspect the current state:

```bash
git status --short --branch
git branch --show-current
git worktree list --porcelain
```

Preserve unrelated changes. Never reset, clean, stash, checkout over, delete,
or overwrite user or unrelated agent work unless the user explicitly authorized
that exact operation.

## Staging And Commit

Stage exact paths unless the entire dirty tree has been proven to be one
delivery boundary. Exclude local config, caches, dependencies, build outputs,
logs, scratch files, and unrelated edits.

Before committing, inspect:

```bash
git diff -- <path>
git diff --cached --name-status
git diff --cached --check
```

Local commit is allowed after authorized, validated work when the boundary is
clear. Group commits by delivery boundary. Push, remote branches, pull or merge
requests, release tags, and other remote state changes require explicit user
initiation.

## Cleanup

Clean up only an exact registered worktree target after checking its dirty,
locked, and branch state. Removing the associated branch is separate
destructive work and needs explicit authority.

## Report

Report repository, branch, isolation choice, staged files, commit hash when one
was made, validation commands with key output, excluded dirty files, and
whether push or other remote work remains separate.
