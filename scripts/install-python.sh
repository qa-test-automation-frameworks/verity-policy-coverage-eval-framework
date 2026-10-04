#!/usr/bin/env bash
set -euo pipefail
# Pin publisher metadata independently of the uv release for reproducible downloads.
version="${1:-$(cat .python-version)}"
case "$version" in
  3.12.15|3.13.16) ;;
  *) echo "Supported bootstrap baselines: Python3.12.15 or3.13.16; install .python-version with uv0.12.23." >&2; exit 2 ;;
esac
if [[ "$(uv --version)" != "uv 0.12.23"* ]]; then
  echo "Use uv0.12.23 for the reproducible bootstrap; see docs/runtime-policy.md." >&2
  exit 2
fi
uv python install "$version" --python-downloads-json-url \
  https://raw.githubusercontent.com/astral-sh/uv/46b84fd0bfec23b72f29e8e2185ba68a65052f48/crates/uv-python/download-metadata.json
