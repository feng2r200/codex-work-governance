#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec uv run --no-project python "$root/scripts/evaluate_continuation_readiness.py"
