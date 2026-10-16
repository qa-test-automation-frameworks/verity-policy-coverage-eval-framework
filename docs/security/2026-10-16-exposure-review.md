# Dependency exposure review — 2026-10-16

This review classifies the unresolved all-extras dependency findings by the
code paths present in this repository. It is not a vulnerability exception,
security certification, or replacement for an upstream patch. The unsuppressed
dependency scan remains blocking until patched releases are available and
validated.

## Exact locked packages

The lockfile at this review is `uv.lock` SHA-256
`1a427f5edd08954a05377ee9c937fdf27c3eb31a2cd05be417828d862f45cc99`:

| Package | Version | Advisory | Current code-path assessment |
|---|---:|---|---|
| `chromadb` | 1.5.9 | [CVE-2026-45829](https://github.com/advisories/GHSA-f4j7-r4q5-qw2c), [CVE-2026-45830](https://github.com/advisories/GHSA-2wm9-hf6c-p5cr), [CVE-2026-45831](https://github.com/advisories/GHSA-xph7-9rjv-w5fr), [CVE-2026-45833](https://github.com/advisories/GHSA-36p7-vc44-83pf) | Application code constructs `chromadb.PersistentClient` in `src/sut/retriever.py`. Repository search found no Chroma `HttpClient`, server startup, or SimpleRBAC configuration. The cited server/API attack paths are therefore not enabled by the checked-in application configuration. This is a configuration-level exposure finding, not proof that the dependency is safe in every deployment. |
| `diskcache` | 5.6.3 | [CVE-2025-69872](https://github.com/advisories/GHSA-w8v5-vhqr-4h9v) | Transitive dependency of RAGAS; no direct import or configured shared cache path was found in this repository. The advisory requires an attacker to write to a cache directory later read by the application. This repository does not establish that trust boundary for deployments outside its own code. |
| `ragas` | 0.4.3 | [CVE-2026-6587](https://github.com/advisories/GHSA-95ww-475f-pr4f) | The repository calls text metric adapters in `src/verity/metrics/ragas_metrics.py`; no use of the vulnerable `MultiModalFaithfulness` collection metric or its URL-processing helper was found. Arbitrary retrieval-context URLs must not be passed into that vulnerable module. This is not a patched or globally safe version. |

The advisories currently list no patched versions for these locked releases.
The [upstream Chroma release page](https://github.com/chroma-core/chroma/releases)
shows stable 1.5.9 and a 1.5.10 development build; a development build is not
treated as a production fix. [RAGAS releases](https://github.com/vibrantlabsai/ragas/releases)
list 0.4.3 as latest. Recheck each advisory and released package before
changing this assessment.

The refreshed unsuppressed local `pip-audit --desc` run after applying
available fixes reports 9 records (6 unique advisory IDs) across these same
3 packages. Some advisory records appear more than once in the tool output.
The updates removed the actionable `fsspec` (fixed in 2026.6.0),
`langgraph-sdk` (fixed in 0.4.4; locked at 0.4.7), and `multidict` (fixed in
6.9.1) findings. These minimum versions are now constraints in `pyproject.toml`
and the exact versions are resolved in `uv.lock`. The deterministic suite
passes locally under Python 3.12.15: 1,724 passed, 2 skipped, total coverage
94.96%. The remaining findings have no fixed releases in the current scan and
are still not suppressed. The native machine-readable result is preserved in
[`scans/2026-10-16-after-transitive-fixes.json`](scans/2026-10-16-after-transitive-fixes.json).

## Gate disposition

The prior exact Verity run `38929092911` completed deterministic/evidence
steps, then failed at `Dependency vulnerability scan`; it tested the preceding
lockfile and found six packages. The refreshed local scan after the selective
updates is preserved in
[`scans/2026-10-16-after-transitive-fixes.json`](scans/2026-10-16-after-transitive-fixes.json).
A new remote CI and image scan are required for the updated lock before this
review can claim the repository gates are current.

No ignore entry was added and no expired exception was renewed. The current
container scan must also be rerun against the refreshed lock, and the three
remaining dependencies must be rechecked against upstream releases before the
security gate can be called healthy. Keep CI visibly red until then.
