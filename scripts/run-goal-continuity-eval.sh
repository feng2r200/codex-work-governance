#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
arguments=(goal-continuity)
if [[ "${KEEP_EVAL_WORKSPACE:-0}" == "1" ]]; then
  arguments+=(--keep-workspace)
fi
exec uv run "$repo_root/scripts/run_behavior_trial.py" "${arguments[@]}"
