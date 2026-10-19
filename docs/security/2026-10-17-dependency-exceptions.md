# Time-bounded dependency vulnerability review — 2026-10-17

This review proposes narrow, temporary exceptions for two optional dependency
findings in PR #31. It does not claim that the affected packages are fixed or
that the advisories are false positives. The four ChromaDB findings were
remediated in this branch by removing ChromaDB and replacing its local vector
index with SQLite plus FastEmbed. The remaining DiskCache and RAGAS exceptions
expire **2026-11-17** and must be reassessed or removed before then. Required
scanners continue to run against the complete Python environment and final
image; no severity classes or package paths are excluded.

## Evidence reviewed

- Verity PR #31 exact-head Python matrix run `39032443267` on commit `87de4a8`
  reports nine records across three packages and six unique advisory IDs. Both
  Python 3.12 and 3.13 pass lint, formatting, strict types, model preparation,
  deterministic tests, coverage, hermetic evidence checks and documentation
  regeneration before the dependency gate reports the same findings.
- Container scan run `39032443229` on `87de4a8` builds the final image and passes
  all packaged Tier-1 tests. Its retained Trivy JSON contains four Python
  package findings for ChromaDB and no OS-package findings. The exact artifact
  is `work/roadmap-evidence/a06-python-matrix-fix-2026-10-17/custom-distroless-87de4a8/trivy-results.json`.
- The initial review lock resolved ChromaDB `1.5.9`, DiskCache `5.6.3`, and RAGAS
  `0.4.3`; direct PyPI metadata checked on 2026-10-17 identifies these as the
  latest stable releases at the time of the initial review, so a version-only
  refresh did not remediate those initial findings.
- At initial review, the repository constructed only
  `chromadb.PersistentClient` in `src/sut/retriever.py`; it did not start or
  expose Chroma's FastAPI server, accept Chroma API requests, set
  `trust_remote_code`, or expose the embedding-function injection point to an
  external caller. Those controls reduced the documented remote attack paths
  but did not establish that the vulnerable library code was safe in every
  deployment. The current candidate removes ChromaDB entirely.
- The RAGAS SSRF advisory names the multimodal faithfulness collection utility.
  `src/verity/metrics/ragas_metrics.py` constructs only Faithfulness,
  ContextPrecision, ContextRecall, and AnswerRelevancy metrics; it does not
  construct the multimodal metric or pass untrusted retrieved-context URLs to
  it. The DiskCache advisory requires an attacker to write malicious pickle
  data to a cache directory before it is read. The repository does not
  configure RAGAS `DiskCacheBackend`; no application input is used as a cache
  path. This does not cover future integrations that enable persistent cache.

## Current remediation candidate

The updated lock resolves FastEmbed `0.9.0` and no longer includes ChromaDB.
FastEmbed's supported-model catalog includes the same
`sentence-transformers/all-MiniLM-L6-v2` model used previously. Local evaluation
against all 16 real retrieval benchmark queries produced exact ordered chunk-ID
parity with the former Chroma implementation; all 16 benchmark quality checks
passed. The SQLite persistence implementation, cache reload, corrupt-cache
rebuild, corpus fingerprint and retrieval tests passed locally (110 passed, 1
intentional skip in the focused suite). These are candidate implementation
results; hosted Python matrix and final-image scans must pass before declaring
the remediation complete.

## Remaining proposed exceptions

| Scanner ID | Package | Finding and local disposition |
|---|---|---|
| `PYSEC-2026-2447` | DiskCache | Pickle deserialization requires a cache directory writable by an attacker. The current application does not configure DiskCache or let request data select a cache path. |
| `PYSEC-2026-3046` / `CVE-2026-6587` | RAGAS | SSRF is in the multimodal faithfulness collection utility; current factories use text metrics and do not invoke that code path. |

Advisory sources: [Chroma pre-auth code execution](https://github.com/advisories/GHSA-f4j7-r4q5-qw2c), [Chroma cross-tenant authorization](https://github.com/advisories/GHSA-2wm9-hf6c-p5cr), [Chroma collection-update code execution](https://github.com/advisories/GHSA-36p7-vc44-83pf), [DiskCache pickle deserialization](https://github.com/advisories/GHSA-w8v5-vhqr-4h9v), and [RAGAS multimodal SSRF](https://github.com/advisories/GHSA-95ww-475f-pr4f). The second Chroma cross-tenant record is `CVE-2026-45831`; its package ID is `PYSEC-2026-3815`.

`.pip-audit-ignore` contains only the two remaining exact Python advisory IDs.
`.trivyignore` contains no active IDs, and no OS findings are ignored.
`scripts/check_vuln_exceptions.py` checks that every active exception has a
future expiry date.

## Required follow-up before expiry

1. Recheck the upstream release and advisory state for every ID.
2. Keep ChromaDB absent unless an explicitly fixed release and a separately
   reviewed design justify reintroducing it; retain benchmark evidence for the
   FastEmbed/SQLite replacement and do not create a Chroma network API.
3. Recheck whether RAGAS still requires DiskCache and whether its cache backend
   can be made optional without changing the semantic evaluation contract.
4. Re-run both Python versions, packaged Tier-1 tests, pip-audit, Trivy, the
   shared-app authorization/citation tests, and the negative security controls.
5. Remove each exception as soon as its issue is remediated. If an exception
   still needs renewal, provide new evidence and an explicit reviewer decision;
   never auto-extend it.

## Upstream disposition recheck — 2026-10-19

The latest public upstream status does not provide a safe released fix for
either remaining advisory:

- The [DiskCache advisory](https://github.com/advisories/GHSA-w8v5-vhqr-4h9v)
  still lists no patched version. Upstream PR
  [#364](https://github.com/grantjenks/python-diskcache/pull/364) proposes
  allowlist-only pickle reads and a breaking 6.0.0 release, but the maintainer
  states they do not intend to merge it as written: writes of unsupported
  objects would still succeed and later fail on read, and existing Django
  backend use cases would regress. The fork published from that proposal is
  therefore not treated as an approved drop-in fix. Keep the current exact,
  expiring finding visible and do not pin an unreviewed fork.
- The [RAGAS advisory](https://github.com/advisories/GHSA-95ww-475f-pr4f)
  still lists no patched version through 0.4.3; PyPI's release history lists
  0.4.3 (2026-01-13) as the latest stable release checked. The affected
  multimodal collection utility is not invoked by this repository's current
  text metric factories, but that limits the known path rather than fixing the
  vulnerable package.

This recheck supports retaining the existing narrow exceptions only until
their recorded expiry of 2026-11-17, pending independent review. It does not
clear either finding, certify the dependency tree, or authorize renewal. Recheck
the advisories and upstream release state before expiry. Sources checked:
[DiskCache GHSA](https://github.com/advisories/GHSA-w8v5-vhqr-4h9v),
[DiskCache upstream PR #364](https://github.com/grantjenks/python-diskcache/pull/364),
[RAGAS GHSA](https://github.com/advisories/GHSA-95ww-475f-pr4f), and
[RAGAS on PyPI](https://pypi.org/project/ragas/).

These proposed exceptions preserve visible, time-limited risk while allowing
unrelated quality work to proceed. They are not a security waiver for
production use of Chroma's server API or RAGAS's multimodal URL processing.
