---
name: git-change-governance
description: Use when choosing or changing Git branches and worktrees, protecting dirty state, staging or committing local work, deciding push boundaries, or cleaning up Git workspaces.
---

# Git Change Governance

This skill owns only the Git boundary. Use `work-governance:work-lifecycle` for
the broader goal, authority, and completion claim.

## Isolation

Prefer an existing isolated branch or worktree for substantive changes. Use the
current attached worktree when it is already isolated and its dirty state
belongs to the same delivery boundary.

When a new worktree is needed, choose its location in this order:

1. the current attached or already managed worktree;
2. an explicit user or project path;
3. the worktree root configured by the current Codex environment;
4. Codex's official default, `$CODEX_HOME/worktrees`.

Do not create a project-local governance directory merely to hold worktrees.
Placement does not choose branch semantics: verify the repository, start point,
target path, and branch or detached mode independently.

Treat the project's current default branch and authoritative project guidance
as the stable integration target. Do not assume it is named `main`.

## Dirty State

Before Git mutation, inspect the current branch, status, and registered
worktrees. Preserve unrelated changes. Do not reset, clean, stash, switch over,
delete, or overwrite user or other-agent work unless the exact action and target
are authorized.

## Staging And Commit

Stage exact paths unless the entire dirty tree is proven to be one delivery
boundary. Exclude local configuration, caches, dependencies, build outputs,
logs, scratch files, and unrelated edits.

Before committing, inspect the unstaged diff, staged name/status set, and staged
whitespace checks. Local commits are allowed only when the work and commit are
authorized, the boundary is coherent, and the claimed validation passed.
Group commits by repository and independently meaningful delivery boundary.

Push, remote branch changes, pull or merge requests, release tags, and other
remote state changes are separate actions. A local commit does not authorize
them.

## Cleanup And Handoff

Clean up only an exact registered worktree after checking its dirty, locked,
and branch state. Removing a worktree, removing its branch, and deleting
untracked data are separate decisions.

Report the repository, branch or detached state, isolation choice, committed
boundary and hash when applicable, validation evidence, excluded dirty files,
cleanup performed, and remote work that remains outside the current authority.
