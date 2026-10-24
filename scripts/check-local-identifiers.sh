#!/usr/bin/env bash
set -euo pipefail
specific='/home/vyaspc|home-vyaspc|/Users/[^/[:space:]]+/|[A-Za-z]:\\Users\\'
generic='/home/[a-z_][a-z0-9_-]*/'
excludes=()
if [ -f .local-identifier-allowlist ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    path="${line%%#*}"
    path="${path%"${path##*[![:space:]]}"}"
    [ -n "$path" ] || continue
    case "$line" in
      *'#'*) reason="${line#*#}" ;;
      *) echo 'Local identifier exceptions need a reason' >&2; exit 2 ;;
    esac
    if [[ ! "$reason" =~ [^[:space:]] ]]; then echo 'Local identifier exceptions need a reason' >&2; exit 2; fi
    excludes+=(":(exclude)$path")
  done < .local-identifier-allowlist
fi
found=0
for pattern in "$specific" "$generic"; do
  set +e
  matches="$(git grep -nIE "$pattern" -- . "${excludes[@]}")"
  status=$?
  set -e
  if [ "$status" -gt 1 ]; then exit "$status"; fi
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    filtered="$line"
    if [ "$pattern" = "$generic" ]; then filtered="${line//\/home\/runner\//\/ci-runner\/}"; fi
    if [[ "$filtered" =~ $pattern ]]; then printf '%s\n' "$line"; found=1; fi
  done <<< "$matches"
done
if [ "$found" -ne 0 ]; then echo 'Local machine identifiers found' >&2; exit 1; fi
