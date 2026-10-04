# Patched uv runtime tool

Exact7c733c7 remote PR Gate37203402574 reached the dependency scan after both
Python3.12.15/3.13.16 quality/test steps passed. The gate correctly failed on nine
records in Chroma/diskcache/RAGAS. Actual Docker37203402571 built the new pinned
Python image, then Trivy reported four Chroma high/critical findings plus a new
uv tool finding: quinn-proto0.11.14/GHSA-4w2j-m93h-cj5j, fixed at0.11.15.
Neither failed run is represented as clean security or full runtime success.

The current tool baseline is now uv0.12.23 across helper, contributor instructions,
CI and digest-pinned container. The official release archive matched its publisher
SHA256 `9167d72b3319674b6303c4cbe071854bba13ebdf3d76b1a7cbdc175471fb66d6`;
its [publisher Cargo lock](https://github.com/astral-sh/uv/blob/0.12.23/Cargo.lock)
selects quinn-proto0.11.18. This fixes the source dependency behind the
[reported advisory](https://github.com/advisories/GHSA-4w2j-m93h-cj5j); actual
container scanning at the new revision still needs verification. No new project
package selection, Python version or lockfile change accompanies this tool fix.

Local frozen sync checked193 installed packages without changes. Actual tool
version0.12.23 and Python3.13.16 are recorded; the pinned bootstrap helper, Ruff,
mypy and all75 hermetic adversarial cases passed. The earlier1714 full-suite run
remains labeled with its original uv0.11.25, separately from this scoped tool check.

Native output, previous finding, publisher/version/checksum and current source
hashes are retained in `evidence/2026-10-04-runtime-tool/`. Project advisories
remain unresolved without new exclusions. Docker appuser model-cache portability
and portfolio-wide R03 remain required.
