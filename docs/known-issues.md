# Known Issues

Tracked, intentional `pytest.xfail` and `pytest.mark.quarantine` cases in the
deterministic and semantic suites. This is a public GitHub repo with no
attached issue tracker, so each entry carries a short `KI-N` tag (in its xfail
reason string, or in the marker's surrounding docstring for quarantine cases),
cross-referenced here rather than to an external ticket.

| Tag | Location | Description | Rationale |
|-----|----------|--------------|-----------|
| KI-3 | `tests/semantic/test_faithfulness.py::test_clean_faithfulness`, `tests/semantic/test_relevancy.py::test_answer_relevancy` | Clean-control gating on faithfulness and answer relevancy is quarantined (informational, non-blocking) | The committed live control run recorded multiple failures concentrated on exactly these two metrics (see the Control-Case Results section of `docs/defects-caught.md`), and `docs/calibration-report.md` independently flags faithfulness below the 85%-agreement / 0.20-MAE bar for the same judge. Calibration cases for `answer_relevancy` were added alongside `hallucination` and `context_precision`, but no live judge run has measured agreement against them yet. Both tests keep running for signal; defect-detection gating (`test_defect_faithfulness_detected`) is unaffected. Remove the quarantine marker once a live calibration run clears the agreement bar for both metrics. |

Because the faithfulness judge is quarantined while its calibration is
pending, defects #1 (bariatric hallucination) and #2 (stale Silver premium)
are not left entirely to the judge: `check_claim_numbers_grounded`
(`src/verity/checks.py`) is a deterministic, judge-independent check that
verifies every number the answer states also appears in some retrieved
chunk's text — the same class of ungrounded-number hallucination these
defects exercise. It currently runs against the clean-control cases in
`tests/deterministic/test_response_schema.py::test_claim_numbers_grounded_in_retrieved_chunks`
(asserting grounding holds absent a defect); it is available as the
deterministic backstop signal for these defect cases once faithfulness
calibration clears and gating is revisited.

## Resolved

| Tag | Was | Resolution |
|-----|-----|------------|
| KI-1, KI-2 | `ctrl-missing-acupuncture-policy` failed the real-embedding retrieval benchmark and recorded-snapshot regression check, because near-tied embedding distances made which chunks even got retrieved unstable across process runs. | `PolicyRetriever.retrieve()` now applies an absolute distance ceiling (`_MAX_RELEVANT_DISTANCE`, see `src/sut/retriever.py`) and returns no chunks when even the closest candidate exceeds it — resolving both the flakiness (an empty result is always equal to itself) and the underlying gap (the retriever now correctly signals "no relevant section" instead of returning its least-bad guesses). The benchmark case is marked `no_answer: true` in `datasets/retrieval/benchmarks.yaml`; `test_real_retrieval_quality.py` asserts the empty result directly. `datasets/retrieval/recorded_chunks.json` was regenerated for this case. The `FixtureRetriever`-backed benchmark in `test_retrieval_benchmark.py` is unaffected — its hand-authored distractor context tests a different thing (how the agent reasons over "not affirmatively covered" context) and still gates deterministically. |

_Last reviewed: 2026-07-02._
