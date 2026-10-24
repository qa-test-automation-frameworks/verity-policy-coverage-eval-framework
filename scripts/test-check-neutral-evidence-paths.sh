#!/usr/bin/env bash
set -euo pipefail
scanner="$(cd "$(dirname "$0")" && pwd)/check-neutral-evidence-paths.sh"
workspace="$(mktemp -d)"
trap 'rm -rf "$workspace"' EXIT
cd "$workspace"
git init -q
mkdir scripts
printf '%s\n' 'work/evidence/security' > scripts/fixture.txt
git add scripts/fixture.txt
bash "$scanner"
printf '%s%s\n' 'work/' 'audit-2026-10-21/Q4/security' > scripts/fixture.txt
set +e
bash "$scanner" > result.log 2>&1
status=$?
set -e
if [ "$status" -ne 1 ]; then cat result.log; echo "Expected rejection, received $status" >&2; exit 1; fi
grep -q 'Use neutral work/evidence paths' result.log
