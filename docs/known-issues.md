# Known Issues

Tracked, intentional `pytest.xfail` and `pytest.mark.quarantine` cases in the
deterministic and semantic suites. This is a public GitHub repo with no
attached issue tracker, so each entry carries a short `KI-N` tag (in its xfail
reason string, or in the marker's surrounding docstring for quarantine cases),
cross-referenced here rather than to an external ticket.

| Tag | Location | Description | Rationale |
|-----|----------|--------------|-----------|
| KI-1 | `tests/deterministic/test_real_retrieval_quality.py:53` | `ctrl-missing-acupuncture-policy` fails the real-embedding retrieval benchmark | The corpus never mentions acupuncture, so embedding distances for every chunk cluster tightly with no distinguishing lexical/semantic signal. Real-embedding ranking of a "the corpus is silent on this" query is a materially harder problem than section/keyword-matched retrieval. The equivalent `FixtureRetriever` benchmark in `test_retrieval_benchmark.py` still gates this case deterministically, so coverage is not lost — only the real-embedding path is exempted. |
| KI-2 | `tests/deterministic/test_retriever_regression.py:73` | `ctrl-missing-acupuncture-policy` fails the real-retriever recorded-snapshot regression check | Same root cause as KI-1: near-tied embedding distances mean which chunks even make the cut (not just their order) varies between process runs, so a fixed recorded snapshot is not a meaningful regression signal for this specific case. |
| KI-3 | `tests/semantic/test_faithfulness.py::test_clean_faithfulness`, `tests/semantic/test_relevancy.py::test_answer_relevancy` | Clean-control gating on faithfulness and answer relevancy is quarantined (informational, non-blocking) | The committed live control run recorded multiple failures concentrated on exactly these two metrics (see the Control-Case Results section of `docs/defects-caught.md`), and `docs/calibration-report.md` independently flags faithfulness below the 85%-agreement / 0.20-MAE bar for the same judge. Calibration cases for `answer_relevancy` were added alongside `hallucination` and `context_precision`, but no live judge run has measured agreement against them yet. Both tests keep running for signal; defect-detection gating (`test_defect_faithfulness_detected`) is unaffected. Remove the quarantine marker once a live calibration run clears the agreement bar for both metrics. |

KI-1 and KI-2 concern the same underlying case (`ctrl-missing-acupuncture-policy`)
and the same root cause (no lexical/semantic signal in the real corpus for
this query) surfacing in two different test modules.

_Last reviewed: 2026-07-02._
