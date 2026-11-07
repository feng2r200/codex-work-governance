---
name: git-change-governance
description: Use when choosing or changing Git branches and worktrees, protecting dirty state, staging or committing local work, deciding push boundaries, or cleaning up Git workspaces.
---

# Git Change Governance

This skill owns only the Git boundary. Use `work-governance:work-lifecycle` for
routing and `work-governance:execution-kernel` for the authority boundary and
the completion claim.

## Isolation

Prefer an existing isolated branch or worktree for substantive changes. Use the
current attached worktree when it is already isolated and its dirty state
belongs to the same delivery boundary.

When a new worktree is needed, choose its location in this order:

1. the current attached or already managed worktree;
2. an explicit user or project path;
3. the worktree root configured by the current agent host;
4. the host's documented default worktree root.

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

Authorization to modify repository content includes creating new,
non-rewriting local commits for that authorized work by default. Do not ask for
separate confirmation after each coherent stage unless the user or project
makes the task read-only, requests a confirmation-only proposal or review
before commit, excludes commits, or leaves repository, branch, or worktree
ownership unresolved.

Treat a local commit as a checkpoint for staged Git-tracked state, not as a
complete workspace backup, task-completion claim, or remote delivery. Commit
when the stage is independently meaningful and coherent and the claimed
validation has passed. Do not create mechanical or knowingly broken WIP
commits merely to clear the working tree.

Stage exact paths unless the entire dirty tree is proven to be one delivery
boundary. Exclude local configuration, caches, dependencies, build outputs,
logs, scratch files, and unrelated edits.

Before committing, inspect the unstaged diff, staged name/status set, and staged
whitespace checks. Group commits by repository and independently meaningful
delivery boundary; keep implementation, tests, and documentation together when
they establish one behavior instead of splitting mechanically by file type.

Push, remote branch changes, pull or merge requests, release tags, and other
remote state changes are separate actions. A local commit does not authorize
them. This default also does not authorize amend, rebase, reset, force updates,
branch or worktree deletion, or destructive cleanup. A hook or signing step
does not inherit authority for an external, credentialed, production, or
data-changing action it triggers.

## Cleanup And Handoff

Clean up only an exact registered worktree after checking its dirty, locked,
and branch state. Removing a worktree, removing its branch, and deleting
untracked data are separate decisions.

Also establish whether the target contains the current session's working
directory. Git may allow removing such a worktree, but doing so can disrupt
the session. Before authorized removal, ensure the session and any dependent
processes no longer need that directory, such as by safely relocating or
ending them. If that cannot be established, report the session-safety blocker
separately from the repository's worktree state.

A refusal from a host-managed workspace interface proves only that the managed
path is unavailable. It is not evidence that the worktree is unmerged, in use,
or protected by the repository itself. Re-derive the state from the repository
before reporting a cleanup result.

Report the repository, branch or detached state, isolation choice, committed
boundary and hash when applicable, validation evidence, excluded dirty files,
cleanup performed, and remote work that remains outside the current authority.
