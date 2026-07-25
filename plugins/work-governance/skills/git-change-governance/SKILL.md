---
name: git-change-governance
description: Govern Git branch/worktree choice, dirty-state protection, staging scope, commit grouping, local commit, push/MR boundaries, and rollback-safe handoff. Use whenever Codex will inspect or change Git state, stage files, commit, report commit readiness, or decide whether main/master may be used.
---

# Git Change Governance

Load `work-governance:work-lifecycle` first. This skill handles only the Git
boundary; evidence and Plan authority remain lifecycle responsibilities.

## Rules

- Protect `main` and `master` by default. Prefer an existing isolated branch,
  a new branch, or a worktree for substantive changes.
- When a new worktree is needed, default to
  `<project-root>/.worktree/<task-or-branch-slug>`. Resolve the project root
  first. Derive the directory slug independently from the Git branch: map each
  run outside `[A-Za-z0-9._-]` to `-`, trim leading and trailing `.`, `-`, and
  `_`, and reject an empty slug, `.` or `..`. A slug must be one path component.
  Do not default to a sibling directory, home directory, or system temporary
  directory.
- Before `git worktree add`, verify that `.worktree/` is ignored and that the
  exact target neither exists, including as a dangling symlink, nor appears in
  `git worktree list --porcelain`. Reject a symlinked `.worktree/`. Resolve the
  physical project and `.worktree/` paths and prove the latter remains directly
  under the former before appending the validated one-component slug. Prefer
  an existing project ignore rule; otherwise use the repository-local
  `.git/info/exclude` for a local-only convention, or update `.gitignore` when
  the project should share the convention.
- Worktree placement does not choose branch semantics. For an existing branch,
  attach that exact branch. For a new branch, require an explicit, verified
  start point; never silently default the start point to the current `HEAD`.
  Use detached mode only when the task explicitly calls for it.
- Before creation, resolve `git rev-parse --path-format=absolute
  --git-common-dir` and evaluate both that common Git directory and the target
  path against the current sandbox or permission boundary. A project-local
  target reduces target-path boundary prompts but cannot guarantee that Git
  metadata writes need no approval.
- Use a worktree path outside the project root only when the user specifies it
  or a verified technical constraint requires it. Report the reason, exact
  path, sandbox/permission impact, and cleanup boundary before creation.
- Clean up only the exact registered target with `git worktree remove` after
  checking its dirty, locked, and associated-branch state. Never recursively
  delete the `.worktree/` root. Deleting the associated branch is a separate
  destructive action and requires explicit authorization.
- Direct local commit is allowed after authorized, validated work when the
  boundary is clear and no unrelated changes are included.
- Push, remote branches, MR/PR creation, and other remote-state changes require
  explicit user initiation.
- Never reset, checkout, clean, stash, delete, or overwrite user changes unless
  the user explicitly authorizes that exact high-impact operation.
- Stage by exact path unless the full dirty worktree has been proven to be the
  same delivery boundary.
- Exclude local config, caches, dependencies, build outputs, logs, generated
  scratch files, and unrelated user edits.

## Required Checks

Before Git action, inspect:

```bash
git status --short --branch
git branch --show-current
git worktree list --porcelain
```

Before creating a project-local worktree, resolve and validate its location:

```bash
repo_root=$(cd "$(git rev-parse --show-toplevel)" && pwd -P)
common_git_dir=$(git rev-parse --path-format=absolute --git-common-dir)
worktree_root="$repo_root/.worktree"
git check-ignore -q "$repo_root/.worktree/"
test ! -L "$worktree_root"
mkdir -p "$worktree_root"
worktree_root=$(cd "$worktree_root" && pwd -P)
test "$(dirname "$worktree_root")" = "$repo_root"
slug="<validated-one-component-slug>"
target="$worktree_root/$slug"
test ! -e "$target" && test ! -L "$target"
git worktree list --porcelain
```

After checking the registered worktree paths and the permission boundary for
both `$target` and `$common_git_dir`, choose the command that matches the
already-decided branch semantics:

```bash
git worktree add "$target" <existing-branch>
git worktree add -b <new-branch> "$target" <verified-start-point>
```

Before commit, inspect:

```bash
git diff -- <path>
git diff --cached --name-status
git diff --cached --check
```

Run validation that matches the commit claim. A commit message must not claim
more than the evidence proves.

## Commit Grouping

Group by delivery boundary:

- feature or fix plus direct tests;
- governance rule or skill update;
- documentation authority update;
- generated artifacts only when they are intended deliverables.

If multiple boundaries exist, commit separately or leave later groups unstaged.

## Reporting

Report repository, branch, isolation choice, staged files, commit hash, validation
commands with key output, excluded dirty files, and whether Push/MR remains a
separate user-initiated step.
