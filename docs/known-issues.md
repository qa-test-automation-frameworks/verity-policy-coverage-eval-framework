# Known Issues

Tracked, intentional `pytest.xfail` cases in the deterministic suite. This is a
public GitHub repo with no attached issue tracker, so each xfail carries a
short `KI-N` tag in its reason string, cross-referenced here rather than to an
external ticket.

| Tag | Location | Description | Rationale |
|-----|----------|--------------|-----------|
| KI-1 | `tests/deterministic/test_real_retrieval_quality.py:53` | `ctrl-missing-acupuncture-policy` fails the real-embedding retrieval benchmark | The corpus never mentions acupuncture, so embedding distances for every chunk cluster tightly with no distinguishing lexical/semantic signal. Real-embedding ranking of a "the corpus is silent on this" query is a materially harder problem than section/keyword-matched retrieval. The equivalent `FixtureRetriever` benchmark in `test_retrieval_benchmark.py` still gates this case deterministically, so coverage is not lost — only the real-embedding path is exempted. |
| KI-2 | `tests/deterministic/test_retriever_regression.py:73` | `ctrl-missing-acupuncture-policy` fails the real-retriever recorded-snapshot regression check | Same root cause as KI-1: near-tied embedding distances mean which chunks even make the cut (not just their order) varies between process runs, so a fixed recorded snapshot is not a meaningful regression signal for this specific case. |

Both entries concern the same underlying case (`ctrl-missing-acupuncture-policy`)
and the same root cause (no lexical/semantic signal in the real corpus for
this query) surfacing in two different test modules.

_Last reviewed: 2026-07-02._
