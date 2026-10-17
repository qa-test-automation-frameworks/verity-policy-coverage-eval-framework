# Time-bounded dependency vulnerability review — 2026-10-17

This review proposes narrow, temporary exceptions for the current dependency
and image scanners for human review in PR #31. It does not claim that the packages are fixed or that the
advisories are false positives. All exceptions expire **2026-11-17** and must be
reassessed or removed before then. The required scanners continue to run against
the complete Python environment and final image; no severity classes or package
paths are excluded.

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
- The current lock resolves ChromaDB `1.5.9`, DiskCache `5.6.3`, and RAGAS
  `0.4.3`; direct PyPI metadata checked on 2026-10-17 identifies these as the
  latest stable releases, so a version-only refresh does not remediate them.
- Chroma advisories describe network API routes. This repository constructs
  only `chromadb.PersistentClient` in `src/sut/retriever.py`; it does not start
  or expose Chroma's FastAPI server, accept Chroma API requests, set
  `trust_remote_code`, or expose the programmatic embedding-function injection
  point to an external caller. The project Docker image has no server entry point and runs the evaluation/test
  command as a non-root user. These controls reduce the documented remote
  attack paths, but do not establish that the vulnerable library code is safe
  in every deployment.
- The RAGAS SSRF advisory names the multimodal faithfulness collection utility.
  `src/verity/metrics/ragas_metrics.py` constructs only Faithfulness,
  ContextPrecision, ContextRecall, and AnswerRelevancy metrics; it does not
  construct the multimodal metric or pass untrusted retrieved-context URLs to
  it. The DiskCache advisory requires an attacker to write malicious pickle
  data to a cache directory before it is read. The repository does not
  configure RAGAS `DiskCacheBackend`; no application input is used as a cache
  path. This does not cover future integrations that enable persistent cache.

## Active exceptions

| Scanner ID | Package | Finding and local disposition |
|---|---|---|
| `PYSEC-2026-311` / `CVE-2026-45829` | ChromaDB | Pre-auth model-code execution requires the Chroma HTTP API and `trust_remote_code`; neither is exposed or enabled by this project. |
| `PYSEC-2026-3813` / `CVE-2026-45830` | ChromaDB | Cross-tenant collection access requires the authenticated Chroma server API; the project uses the embedded persistent client with no external Chroma API. |
| `PYSEC-2026-3815` / `CVE-2026-45831` | ChromaDB | Cross-tenant authorization failure requires the Chroma server authorization path; the project does not expose or configure that service. |
| `PYSEC-2026-3814` / `CVE-2026-45833` | ChromaDB | Collection-update model-code execution requires the server API, update permission, and `trust_remote_code`; these conditions are absent in the current app path. |
| `PYSEC-2026-2447` | DiskCache | Pickle deserialization requires a cache directory writable by an attacker. The current application does not configure DiskCache or let request data select a cache path. |
| `PYSEC-2026-3046` / `CVE-2026-6587` | RAGAS | SSRF is in the multimodal faithfulness collection utility; current factories use text metrics and do not invoke that code path. |

Advisory sources: [Chroma pre-auth code execution](https://github.com/advisories/GHSA-f4j7-r4q5-qw2c), [Chroma cross-tenant authorization](https://github.com/advisories/GHSA-2wm9-hf6c-p5cr), [Chroma collection-update code execution](https://github.com/advisories/GHSA-36p7-vc44-83pf), [DiskCache pickle deserialization](https://github.com/advisories/GHSA-w8v5-vhqr-4h9v), and [RAGAS multimodal SSRF](https://github.com/advisories/GHSA-95ww-475f-pr4f). The second Chroma cross-tenant record is `CVE-2026-45831`; its package ID is `PYSEC-2026-3815`.

The image-level `.trivyignore` contains only the four exact ChromaDB CVE IDs
found in this image. `.pip-audit-ignore` contains the six exact unique advisory
IDs reported by the Python scanner. `scripts/check_vuln_exceptions.py` checks
that every active entry in both files has a future expiry date.

## Required follow-up before expiry

1. Recheck the upstream release and advisory state for every ID.
2. Replace ChromaDB with a maintained local retrieval store or upgrade to
   explicitly fixed releases if compatible fixes become available; do not
   retain Chroma API exposure or `trust_remote_code` as an implicit assumption.
3. Recheck whether RAGAS still requires DiskCache and whether its cache backend
   can be made optional without changing the semantic evaluation contract.
4. Re-run both Python versions, packaged Tier-1 tests, pip-audit, Trivy, the
   shared-app authorization/citation tests, and the negative security controls.
5. Remove each exception as soon as its issue is remediated. If an exception
   still needs renewal, provide new evidence and an explicit reviewer decision;
   never auto-extend it.

These proposed exceptions preserve visible, time-limited risk while allowing
unrelated quality work to proceed. They are not a security waiver for
production use of Chroma's server API or RAGAS's multimodal URL processing.
