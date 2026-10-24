#!/usr/bin/env bash
set -euo pipefail
set +e
matches="$(git grep -nE 'work/audit-20[0-9]{2}' -- .github scripts src tests package.json)"
status=$?
set -e
if [ "$status" -gt 1 ]; then exit "$status"; fi
if [ "$status" -eq 0 ]; then printf '%s\n' "$matches"; echo 'Use neutral work/evidence paths' >&2; exit 1; fi
