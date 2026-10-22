# Known Issues

Tracked, intentional `pytest.xfail` and `pytest.mark.quarantine` cases in the
deterministic and semantic suites. This is a public GitHub repo with no
attached issue tracker, so each entry carries a short `KI-N` tag (in its xfail
reason string, or in the marker's surrounding docstring for quarantine cases),
cross-referenced here rather than to an external ticket.

| Tag | Location | Description | Rationale |
|-----|----------|--------------|-----------|
| KI-3 | `tests/semantic/test_faithfulness.py::test_clean_faithfulness`, `tests/semantic/test_relevancy.py::test_answer_relevancy` | Clean-control gating on faithfulness and answer relevancy is quarantined (informational, non-blocking) | The committed live control run recorded multiple failures concentrated on exactly these two metrics (see the Control-Case Results section of `docs/defects-caught.md`). `docs/calibration-report.md` now demonstrates the calibration math with synthetic replay across faithfulness, answer relevancy, hallucination, and context precision, but no fresh live judge/control run has cleared these controls yet. Both tests keep running for signal; defect-detection gating (`test_defect_faithfulness_detected`) is unaffected. Remove the quarantine marker once a live calibration/control run clears the agreement bar for both metrics. |

`check_claim_numbers_grounded` (`src/verity/checks.py`) verifies that every
number in an answer appears in a retrieved chunk. It runs against clean
controls in
`tests/deterministic/test_response_schema.py::test_claim_numbers_grounded_in_retrieved_chunks`
and supports defect #1's ungrounded-number checks. It does not determine
whether a retrieved premium is current. Defect #2 now has a separate authored
temporal amount oracle; the historical faithfulness results measure grounding
only, so live temporal evidence remains unresolved.

## Resolved

| Tag | Was | Resolution |
|-----|-----|------------|
| KI-1, KI-2 | `ctrl-missing-acupuncture-policy` failed the real-embedding retrieval benchmark and recorded-snapshot regression check, because near-tied embedding distances made which chunks even got retrieved unstable across process runs. | `PolicyRetriever.retrieve()` now applies an absolute distance ceiling (`_MAX_RELEVANT_DISTANCE`, see `src/sut/retriever.py`) and returns no chunks when even the closest candidate exceeds it — resolving both the flakiness (an empty result is always equal to itself) and the underlying gap (the retriever now correctly signals "no relevant section" instead of returning its least-bad guesses). The benchmark case is marked `no_answer: true` in `datasets/retrieval/benchmarks.yaml`; `test_real_retrieval_quality.py` asserts the empty result directly. `datasets/retrieval/recorded_chunks.json` was regenerated for this case. The `FixtureRetriever`-backed benchmark in `test_retrieval_benchmark.py` is unaffected — its hand-authored distractor context tests a different thing (how the agent reasons over "not affirmatively covered" context) and still gates deterministically. |

_Last reviewed: 2026-10-21._
