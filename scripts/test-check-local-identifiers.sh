#!/usr/bin/env bash
set -euo pipefail
scanner="$(cd "$(dirname "$0")" && pwd)/check-local-identifiers.sh"
workspace="$(mktemp -d)"
trap 'rm -rf "$workspace"' EXIT
cd "$workspace"
git init -q
printf 'synthetic fixture\n' > sample.txt
git add sample.txt
bash "$scanner"
expect_failure() {
  local status
  set +e
  bash "$scanner" > result.log 2>&1
  status=$?
  set -e
  if [ "$status" -ne 1 ]; then cat result.log; echo "Expected rejection, received $status" >&2; exit 1; fi
  grep -q 'Local machine identifiers found' result.log
}
printf '%s%s\n' 'home-' 'vyaspc-x' > sample.txt
git add sample.txt
expect_failure
printf 'sample.txt # Synthetic exception used only in this temporary self-test\n' > .local-identifier-allowlist
bash "$scanner"
rm .local-identifier-allowlist
printf '%s\n' '/home/runner/work/x' > sample.txt
bash "$scanner"
printf '%s%s\n' '/home/' 'another-user/project' >> sample.txt
expect_failure
printf '%s%s\n' '/Users/' 'someone/project' > sample.txt
expect_failure
printf '%s%s\n' 'C:' '\Users\someone\project' > sample.txt
expect_failure
