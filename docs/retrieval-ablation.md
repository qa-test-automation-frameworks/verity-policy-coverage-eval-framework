# Retrieval Parameter Ablation

Measures how `source_precision` and the benchmark pass rate in `datasets/retrieval/benchmarks.yaml` move as each hand-tuned retrieval constant in `src/sut/retriever.py` is varied, holding the other constants at their current default. Answers the caveat those constants carry in code: "hand-tuned starting point, not backed by a committed ablation study."

Run against the real `PolicyRetriever` (local ONNX embeddings); `no_answer` benchmark cases are excluded from pass-rate/precision aggregation since they measure a different property (see `docs/known-issues.md`).

## Lexical overlap weight (`_LEXICAL_WEIGHT`)

| Value | Pass rate | Mean source precision |
|---|---|---|
| 0.00 | 40% | 0.511 |
| 0.25 | 87% | 0.744 |
| 0.50 *(current default)* | 100% | 0.789 |
| 0.75 | 93% | 0.867 |
| 1.00 | 93% | 0.867 |

## Distance margin (`_DISTANCE_MARGIN`)

| Value | Pass rate | Mean source precision |
|---|---|---|
| 0.10 | 87% | 0.889 |
| 0.15 | 87% | 0.867 |
| 0.20 *(current default)* | 100% | 0.789 |
| 0.30 | 80% | 0.711 |
| 0.40 | 60% | 0.667 |

## No-answer distance ceiling (`_MAX_RELEVANT_DISTANCE`)

| Value | Pass rate | Mean source precision |
|---|---|---|
| 0.35 | 100% | 0.789 |
| 0.40 | 100% | 0.789 |
| 0.45 *(current default)* | 100% | 0.789 |
| 0.50 | 100% | 0.789 |
| 0.55 | 100% | 0.789 |

_Regenerate: `make retrieval-ablation`._
