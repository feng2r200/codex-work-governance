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

version_less() {
    local left="$1" right="$2" i
    local -a left_parts right_parts
    IFS=. read -r -a left_parts <<< "$left"
    IFS=. read -r -a right_parts <<< "$right"
    for i in 0 1 2; do
        if (( ${#left_parts[$i]} < ${#right_parts[$i]} )); then return 0; fi
        if (( ${#left_parts[$i]} > ${#right_parts[$i]} )); then return 1; fi
        if [[ "${left_parts[$i]}" < "${right_parts[$i]}" ]]; then return 0; fi
        if [[ "${left_parts[$i]}" > "${right_parts[$i]}" ]]; then return 1; fi
    done
    return 1
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
[[ -f "$keep_dir/plugin.json" && "$(manifest_value "$keep_dir/plugin.json" name 2>/dev/null || true)" == "work-governance" && "$(manifest_value "$keep_dir/plugin.json" version 2>/dev/null || true)" == "$keep_version" ]] \
    || die "keep version manifest does not match: $keep_dir"

# Complete this preflight before deleting anything, including in dry-run mode.
for candidate in "$cache_root"/*; do
    [[ -d "$candidate" && ! -L "$candidate" && "$candidate" != "$keep_dir" ]] || continue
    candidate_version="$(basename "$candidate")"
    [[ "$candidate_version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || continue
    manifest="$candidate/plugin.json"
    [[ -f "$manifest" && "$(manifest_value "$manifest" name 2>/dev/null || true)" == "work-governance" && "$(manifest_value "$manifest" version 2>/dev/null || true)" == "$candidate_version" ]] || continue
    if version_less "$keep_version" "$candidate_version"; then
        die "verified newer version exists: $candidate_version (keep: $keep_version)"
    fi
done

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
    if [[ ! "$candidate_version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || ! version_less "$candidate_version" "$keep_version" || [[ ! -f "$manifest" || "$(manifest_value "$manifest" name 2>/dev/null || true)" != "work-governance" \
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
