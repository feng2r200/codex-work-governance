#!/usr/bin/env bash
set -euo pipefail

script_name="$(basename "$0")"
cache_root=""
keep_version=""
dry_run="0"

usage() {
    cat <<EOF
Usage: $script_name --cache-root DIR --keep-version VERSION [--dry-run]

Remove only verified historical work-governance plugin versions from one exact
local cache root. The source checkout and marketplace are never touched.
EOF
}

die() {
    printf 'work_governance_cache_prune_error=%s\n' "$*" >&2
    exit 1
}

absolute_path() {
    case "$1" in
        /*) printf '%s\n' "$1" ;;
        *) printf '%s/%s\n' "$(pwd -P)" "$1" ;;
    esac
}

manifest_value() {
    local manifest="$1"
    local key="$2"
    awk -F'"' -v wanted="$key" '
        $2 == wanted { print $4; found=1; exit }
        END { if (!found) exit 1 }
    ' "$manifest"
}

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --cache-root)
            [[ "$#" -ge 2 ]] || die "--cache-root requires a value"
            cache_root="$(absolute_path "$2")"
            shift
            ;;
        --keep-version)
            [[ "$#" -ge 2 ]] || die "--keep-version requires a value"
            keep_version="$2"
            shift
            ;;
        --dry-run)
            dry_run="1"
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "unknown option: $1"
            ;;
    esac
    shift
done

[[ -n "$cache_root" ]] || die "--cache-root is required"
[[ -n "$keep_version" ]] || die "--keep-version is required"
[[ -d "$cache_root" && ! -L "$cache_root" ]] || die "cache root must be a real directory: $cache_root"
[[ "$(basename "$cache_root")" == "work-governance" ]] \
    || die "refusing a cache root whose basename is not work-governance: $cache_root"
[[ "$keep_version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] \
    || die "keep version must be a semantic version: $keep_version"

keep_dir="$cache_root/$keep_version"
[[ -d "$keep_dir" && ! -L "$keep_dir" ]] \
    || die "keep version directory is missing: $keep_dir"

removed=0
skipped=0
for candidate in "$cache_root"/*; do
    [[ -d "$candidate" ]] || continue
    if [[ -L "$candidate" ]]; then
        printf 'work_governance_cache_prune_skipped=%s\n' "$candidate"
        skipped=$((skipped + 1))
        continue
    fi
    [[ "$candidate" == "$keep_dir" ]] && {
        printf 'work_governance_cache_prune_kept=%s\n' "$candidate"
        continue
    }
    manifest="$candidate/plugin.json"
    candidate_version="$(basename "$candidate")"
    if [[ ! -f "$manifest" || "$(manifest_value "$manifest" name 2>/dev/null || true)" != "work-governance" \
        || "$(manifest_value "$manifest" version 2>/dev/null || true)" != "$candidate_version" ]]; then
        printf 'work_governance_cache_prune_skipped=%s\n' "$candidate"
        skipped=$((skipped + 1))
        continue
    fi
    if [[ "$dry_run" == "1" ]]; then
        printf 'work_governance_cache_prune_would_remove=%s\n' "$candidate"
    else
        rm -rf -- "$candidate"
        printf 'work_governance_cache_prune_removed=%s\n' "$candidate"
    fi
    removed=$((removed + 1))
done

printf 'work_governance_cache_prune_dry_run=%s\n' "$([[ "$dry_run" == "1" ]] && printf true || printf false)"
printf 'work_governance_cache_prune_removed_count=%s\n' "$removed"
printf 'work_governance_cache_prune_skipped_count=%s\n' "$skipped"
