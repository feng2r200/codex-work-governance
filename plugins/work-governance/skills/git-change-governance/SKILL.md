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
