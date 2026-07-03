# Dataset Coverage Matrix

Cross-tabulation of all 69 cases in `datasets/golden/*.yaml` by plan tier, risk weight, expectation category, and seeded-defect linkage. Regenerate after adding cases so this stays a true picture of dataset breadth rather than a stale snapshot.

## By plan tier

| Plan | Cases | Share |
|---|---:|---:|
| bronze | 10 | 14% |
| cross-plan | 39 | 57% |
| gold | 9 | 13% |
| silver | 11 | 16% |

## By risk weight

| Risk weight | Cases | Share |
|---|---:|---:|
| high | 16 | 23% |
| medium | 53 | 77% |

## By behavior

| Behavior | Cases | Share |
|---|---:|---:|
| answer | 58 | 84% |
| refuse | 11 | 16% |

## By expectation category

A case may declare more than one category, so counts sum to more than 69.

| Category | Cases | Share of dataset |
|---|---:|---:|
| amount | 37 | 54% |
| coverage_decision | 19 | 28% |
| evidence | 47 | 68% |
| limits | 7 | 10% |
| refusal | 11 | 16% |
| tool_behavior | 9 | 13% |
| uncertainty | 5 | 7% |

## Seeded-defect linkage

8/8 seeded defects have at least one golden case with a matching `defect_id` (see `docs/seeded-defects.md` for the full catalog).

| Defect | Cases |
|---|---|
| #1 | `defect-1-bariatric-bronze-hallucination`, `defect-1-bariatric-bronze-hallucination-v2` |
| #2 | `defect-2-silver-premium-stale`, `defect-2-silver-premium-stale-v2` |
| #3 | `defect-3-silver-multihop-cost`, `defect-3-silver-multihop-cost-v2` |
| #4 | `defect-4-urgent-care-contradiction`, `defect-4-urgent-care-contradiction-v2` |
| #5 | `defect-5-tool-arg-transposition`, `defect-5-tool-arg-transposition-v2` |
| #6 | `defect-6-refusal-breach`, `defect-6-refusal-breach-v2` |
| #7 | `defect-7-prompt-injection`, `defect-7-prompt-injection-v2` |
| #8 | `defect-8-pii-leakage`, `defect-8-pii-leakage-v2` |

_Regenerate: `make dataset-matrix`._
