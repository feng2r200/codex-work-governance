# Changelog

All notable changes to Work Governance are documented here. The project follows
[Semantic Versioning](https://semver.org/) for public releases.

## Unreleased

### Added

- A complete Simplified Chinese README with bidirectional language navigation.
- Portable Agent Plugins manifest alongside the Codex compatibility manifest.
- Public installation, contribution, security, support, and community guidance.
- Continuous integration for policy contracts and lint checks.

### Changed

- Publisher metadata now credits `feng2r200` explicitly.
- Repository history no longer carries project-local governance runtime data or
  personal absolute paths on the rewritten `main` lineage.

## 2.0.0 release candidate

- Reframed Work Governance as a composable, tool-neutral policy layer.
- Split goal discovery, Plan governance, SubAgent governance, Git boundaries,
  validation, project truth, archive curation, and reporting into independent
  Skills behind a small lifecycle router.
- Removed the embedded state engine and mandatory persistence coupling.
