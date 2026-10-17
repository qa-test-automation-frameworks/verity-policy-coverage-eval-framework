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
The Chroma maintainers merged [PR #7237](https://github.com/chroma-core/chroma/pull/7237)
on July 7, 2026, to reject `trust_remote_code` in embedding-function kwargs and
configuration schemas; that is relevant upstream remediation for the
ChromaDB code-execution finding, but it is not yet a published package fix.
The [upstream Chroma release page](https://github.com/chroma-core/chroma/releases)
still shows stable 1.5.9 and a 1.5.10 development build, and [PyPI](https://pypi.org/project/chromadb/)
still lists 1.5.9 as the released package. Do not substitute an unpublished
development build for the required production-compatible release. [RAGAS
releases](https://github.com/vibrantlabsai/ragas/releases) list 0.4.3 as latest.
Recheck each advisory and released package before changing this assessment.

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

## Gate disposition — rechecked 2026-10-16

The refreshed local scan is now corroborated by exact remote checks on the
roadmap branch. PR Gate `38933601017` ran Python 3.12.15 and 3.13.16: lint,
type, deterministic tests, coverage, hermetic evidence and evidence validation
passed; both matrix legs then failed at the unsuppressed dependency scan with
9 rows across ChromaDB 1.5.9, DiskCache 5.6.3 and RAGAS 0.4.3. This is the
same three-package exposure described above, with no fixed versions reported.

Container scan `38933600908` built the pinned Python 3.13.16 image and passed
the non-root offline ONNX smoke. Updating the base interpreter copies of
`msgpack`, `setuptools` and `urllib3` to the exact versions already in `uv.lock`
reduced Trivy's Python findings from 12 to 8 (4 HIGH, 4 CRITICAL). The refreshed
base digest reduced Debian findings from 45 to 44, but Trivy still reports 44
HIGH Debian findings plus the 8 Python findings. The image gate remains red.

No ignore entry was added and no expired exception was renewed. The current
code paths and container boundary narrow exposure, but they do not patch these
packages or clear either scan. Keep CI visibly red until upstream fixes or a
validated dependency/platform replacement resolves the findings.

## Upstream recheck — 2026-10-17

A fresh check of the official PyPI release pages and GitHub Advisory Database
found no released patch for the locked findings and no version-only dependency
change to apply:

| Package | Locked version | Current PyPI release | Advisory state on 2026-10-17 |
|---|---:|---:|---|
| ChromaDB | 1.5.9 | 1.5.9 | CVE-2026-45829, CVE-2026-45830, CVE-2026-45831 and CVE-2026-45833 all still list no patched version. |
| DiskCache | 5.6.3 | 5.6.3 | CVE-2025-69872 still lists no patched version. |
| RAGAS | 0.4.3 | 0.4.3 | CVE-2026-6587 still lists no patched version. |

Sources: [ChromaDB on PyPI](https://pypi.org/project/chromadb/), [DiskCache on PyPI](https://pypi.org/project/diskcache/), [RAGAS on PyPI](https://pypi.org/project/ragas/), and the [ChromaDB advisories](https://github.com/advisories/GHSA-f4j7-r4q5-qw2c), [second ChromaDB advisory](https://github.com/advisories/GHSA-2wm9-hf6c-p5cr), [third ChromaDB advisory](https://github.com/advisories/GHSA-xph7-9rjv-w5fr), [fourth ChromaDB advisory](https://github.com/advisories/GHSA-36p7-vc44-83pf), [DiskCache advisory](https://github.com/advisories/GHSA-w8v5-vhqr-4h9v), and [RAGAS advisory](https://github.com/advisories/GHSA-95ww-475f-pr4f).

The ChromaDB security fix is merged upstream but not released as a stable
PyPI package: [PR #7237](https://github.com/chroma-core/chroma/pull/7237)
blocks the unsafe option at both the Python and config-schema layers. This
narrows the path to a future supported upgrade; it does not make locked 1.5.9
patched, nor does it address the other three ChromaDB advisories, DiskCache,
RAGAS, or the Trivy findings.

This is a release/advisory metadata recheck, not a new `pip-audit`, Trivy, or
compatibility run. The existing locks remain unchanged; do not downgrade,
exclude, or suppress packages solely to make a scanner green. Re-evaluate when
an upstream patch is released or when a replacement is supported by a bounded
compatibility experiment.

### DiskCache community-fork candidate

The recheck also surfaced `diskcache-community` 5.7.0, a newly published
community fork that retains the Python import name `diskcache` and states that
it adds `SafeDisk` as an opt-in backend. Its PyPI page includes a verified
publishing attestation for the fork repository and release commit, but its
package name differs from the vulnerable upstream distribution. A scanner
showing no advisory against that new distribution would not by itself prove
that the cache now uses the safe backend. RAGAS's transitive cache integration
has not been configured or tested with `SafeDisk`, and this change would not
resolve the separate ChromaDB or RAGAS advisories. Therefore the fork is a
candidate for a bounded compatibility/security experiment, not an adopted fix
or a basis for closing R02.

Sources: [diskcache-community 5.7.0 on PyPI](https://pypi.org/project/diskcache-community/5.7.0/), including its publishing attestation, and the [fork's README](https://github.com/secondwindoss/diskcache-community), which describes the opt-in `SafeDisk` behavior and migration constraints.

## DiskCache community-fork probe — 2026-10-17

A bounded isolated smoke test evaluated `diskcache-community==5.7.0`, the
candidate fork described above. Under Python 3.12.15, its opt-in `SafeDisk`
backend round-tripped supported JSON-like values, created its new cache
directory with mode `0700`, rejected writes of an unsupported custom object,
and rejected a pickle payload resolving `os.system` with `UnpicklingError`; the
marker command did not execute. The script and output are preserved under
`work/roadmap-evidence/diskcache-community-2026-10-17/`.

This is a positive unit-level result for the fork's opt-in backend, not a
replacement qualification. In the pinned RAGAS v0.4.3 source,
`DiskCacheBackend` imports `Cache` and calls `Cache(cache_dir)` without selecting
`SafeDisk` ([source](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/cache.py#L789-L816)). The repository's RAGAS metric factories do not pass a cache, and a source search found no direct `diskcache` use, but the lock still includes it through RAGAS. The fork's documented `SafeDisk` is opt-in; replacing the distribution name through `uv exclude-dependencies` would not make RAGAS's default backend safe. We did not change the lock or scanner inputs, and did not claim the advisory resolved.

Decision: do not adopt the fork for this application yet. The standalone SafeDisk control passed, but no RAGAS `DiskCacheBackend` integration, cache-serialization compatibility, full dependency resolution, or end-to-end scan was exercised. A future adoption requires an explicit safe-backend adapter or an upstream default fix, plus those compatibility checks. The current dependency/image scan remains unsuppressed and blocking.
