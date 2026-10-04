#!/usr/bin/env bash
set -euo pipefail
# uv0.11.25 predates these security patches; use publisher metadata at a fixed commit.
version="${1:-$(cat .python-version)}"
case "$version" in
  3.12.15|3.13.16) ;;
  *) echo "Supported bootstrap baselines: Python3.12.15 or3.13.16; install .python-version with uv0.11.25." >&2; exit 2 ;;
esac
if [[ "$(uv --version)" != "uv 0.11.25"* ]]; then
  echo "Use uv0.11.25 for the reproducible bootstrap; see docs/runtime-policy.md." >&2
  exit 2
fi
uv python install "$version" --python-downloads-json-url \
  https://raw.githubusercontent.com/astral-sh/uv/46b84fd0bfec23b72f29e8e2185ba68a65052f48/crates/uv-python/download-metadata.json
