# Time-bounded dependency vulnerability review — status updated 2026-10-19

This record tracks the two narrow, temporary dependency exceptions retained
with Verity PR #31. It does not claim that the affected packages are fixed or
that the advisories are false positives. The four ChromaDB findings were
remediated by removing ChromaDB and replacing its local vector index with
SQLite plus FastEmbed. The remaining DiskCache and RAGAS exceptions expire
**2026-11-17** and must be reassessed by **2026-11-02** or removed before then.
`pip-audit` scans
the installed Python environment while suppressing only these two exact IDs.
Trivy scans the final image at `CRITICAL,HIGH`; it does not block on medium/low
findings. The Tier-1 image now omits the optional semantic extra, while
semantic CI still installs it. These are distinct scanner and packaging
boundaries, not a claim that every scanner blocks on every severity.

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
- The RAGAS advisory names both `_try_process_url` and
  `_try_process_local_file` in multimodal collection processing. The review of
  the pinned RAGAS 0.4.3 wheel also found `MultiModalRelevance` imports the
  shared image-processing helper. `src/verity/metrics/ragas_metrics.py`
  constructs only text metrics; no multimodal metric or `ImageTextPrompt` is
  used by this project. This reduces current call-path exposure but does not
  remove the vulnerable package code. The DiskCache advisory requires
  attacker-controlled pickle data to be read from a cache; the repository does
  not configure `DiskCacheBackend` or accept a cache path from application
  input. Semantic tests build `retrieved_contexts` from `CoverageAgent` results;
  the agent's `PolicyRetriever` embeds and searches the checked-in local policy
  corpus (`src/sut/corpus`), while `tests/semantic/test_detector_canaries.py`
  uses a literal synthetic context. No user-supplied document or remote URL is
  passed to these RAGAS samples. This does not cover future integrations.
- The review also noted that RAGAS's older `ImageTextPrompt` path checks
  resolved IP addresses but follows redirects. A redirect-based bypass was not
  verified, so this is an unconfirmed adjacent risk, not an established
  exploit. The reviewer did not independently verify the reported 16-query
  retrieval-parity result or trace every optional import in the dependency
  graph.

## Merged remediation status

PR #31 merged to default branch as `5035ebfa7ab44cf9a0567fcaba02caadfedf65bd`
on 2026-10-19. The updated lock resolves FastEmbed `0.9.0` and no longer
includes ChromaDB.
FastEmbed's supported-model catalog includes the same
`sentence-transformers/all-MiniLM-L6-v2` model used previously. Local evaluation
against all 16 real retrieval benchmark queries produced exact ordered chunk-ID
parity with the former Chroma implementation; all 16 benchmark quality checks
passed. The SQLite persistence implementation, cache reload, corrupt-cache
rebuild, corpus fingerprint and retrieval tests passed locally (110 passed, 1
intentional skip in the focused suite). Post-merge PR Gate `39198035150`,
Documentation `39198035156`, shared-app `39198035148`, report publication
`39198059171`, and the exact-main container scan `39198035125` succeeded. A
second main run after PR #33 (`39201389357`, `39201389392`, `39201389349`,
`39201389505`, and `39201389386`) also passed the Python matrix, docs,
shared-app, report-publishing and final-image scan. These checks verify the
merged remediation and active exception gates; they do not clear the remaining
advisories.

## Remaining owner-approved exceptions

| Scanner ID | Package | Finding and local disposition |
|---|---|---|
| `PYSEC-2026-2447` / `GHSA-w8v5-vhqr-4h9v` / `CVE-2025-69872` | DiskCache | Unsafe pickle deserialization in affected versions through 5.6.3; no fixed release was listed at review time. The current application does not instantiate DiskCache or let request data select a cache path. RAGAS is the only direct dependency requiring DiskCache in the reviewed lock. |
| `PYSEC-2026-3046` / `GHSA-95ww-475f-pr4f` / `CVE-2026-6587` | RAGAS | Affected versions 0.2.3–0.4.3; the advisory covers SSRF and local-file reads through multimodal URL/file helpers. The shared helper is also imported by `MultiModalRelevance`; this project currently uses text metrics only. |

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

Replacing the four RAGAS-backed metrics with DeepEval equivalents could remove
RAGAS and its transitive DiskCache dependency, clearing both remaining
exceptions. That is a metric-contract change, not a dependency-only update:
thresholds and calibration evidence would need to be rebuilt and reviewed.
This review therefore keeps the current text metrics behind the documented
import guards and does not claim that a migration has been completed.

This recheck supports retaining the existing narrow exceptions only until
their recorded expiry of 2026-11-17. It does not clear either finding, certify
the dependency tree, or authorize renewal. Recheck the advisories and upstream
release state before expiry. Sources checked:
[DiskCache GHSA](https://github.com/advisories/GHSA-w8v5-vhqr-4h9v),
[DiskCache upstream PR #364](https://github.com/grantjenks/python-diskcache/pull/364),
[RAGAS GHSA](https://github.com/advisories/GHSA-95ww-475f-pr4f), and
[RAGAS on PyPI](https://pypi.org/project/ragas/).

## Owner and AI-assisted review record

The repository owner approved the two exact, expiring exceptions by authorizing
PR #31 and its merge. That authorization was the owner decision; the absence of
a separate GitHub PR approval is not evidence that the merge was unauthorized.
The owner later accepted the 2026-10-19 review by Claude Opus 5.5 in Claude Code,
who did not contribute to the repository, together with the owner's review as
sufficient for this portfolio's R02 gate. This is an explicit owner waiver of
the former human-review requirement. It is not human review, human adoption,
endorsement, or security certification. Review provenance and findings are at
[the portfolio review record](https://github.com/qa-test-automation-frameworks/.github/blob/main/docs/verification/2026-10-19-independent-review.md).

Reviewed: 2026-10-19. Reassess by: 2026-11-02. Expiry: 2026-11-17.
Reviewer: Claude Opus 5.5 in Claude Code + Prayag Vyas (owner). Owner
disposition: retain through 2026-11-17; no renewal authorized.
This applies to `PYSEC-2026-2447` and `PYSEC-2026-3046` only, subject to the
controls below. Any future renewal requires a new dated owner decision and
review record.

## Review-driven controls — 2026-10-19

- `.pip-audit-ignore` records reviewer, review date, reassessment deadline,
  review-record path, disposition, and expiry for each ignored ID. The
  validator confirms the
  linked record exists and contains the exact ID, date, reviewer, and decision;
  metadata authorizes one ID only. It rejects malformed/dangling entries,
  requires reassessment within 14 days, fails after the reassessment deadline
  and on the expiry date, and caps the total exception window at 30 days.
- A daily workflow checks the exception files, so an expired exception fails
  visibly even without a code push. Pull requests that change the exception
  metadata run the same validation.
- Ruff's TID251 banned-API rules guard `diskcache`, `ragas.cache`, RAGAS
  collections, and the multimodal prompt module from project imports without
  an explicit policy change and review.
- `scripts/check_vuln_exception_scope.py` binds each active ignored ID to its
  reviewed package and affected version range in `uv.lock`. It fails if a
  package is removed or upgraded outside the affected range, forcing maintainers
  to remove or re-review a stale exception. The semantic dependency declaration
  remains broad for compatibility, so the lockfile check is the enforced scope.
- The final Tier-1 image installs the `dev` extra but not `semantic`; semantic
  evaluation installs its dependencies in its own workflow.
- The only `actions/cache` directory in the reviewed workflows is
  `~/.cache/fastembed`; do not add the relative `.cache` directory used by
  DiskCache to any Actions cache, because that could preserve attacker-written
  pickle data between runs.
- Trivy's configured threshold remains `CRITICAL,HIGH`; `pip-audit` is the
  active gate that detects these medium/low Python advisories. This record now
  states that distinction accurately.

These approved exceptions preserve visible, time-limited risk while allowing
unrelated quality work to proceed. They are not a security waiver for
production use of Chroma's server API or RAGAS's multimodal URL/file processing.
