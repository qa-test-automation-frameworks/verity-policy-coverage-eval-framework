# Seeded vs. Clean SUT Profile Comparison

Structural comparison of the two `sut_profile` settings across every golden case, built without any live model call.

## Unconditional differences (not case-dependent)

| Behavior | seeded | clean |
|---|---|---|
| Member name/DOB logged at DEBUG (`guardrails.log_member_context`) | full dict logged | only `member_id` logged |
| Structurally invalid conversation (`verity.conversation.validate_conversation` fails) | logged as a warning, request proceeds | returned as a `invalid_conversation_structure` safe-failure |

## Per-case system prompt differences

| Case | Member PII in prompt (seeded) | Member PII in prompt (clean) | Tool-arg disambiguation guidance (clean) |
|---|---|---|---|
| `ctrl-silver-specialist-copay` | yes | no | yes |
| `ctrl-gold-deductible` | yes | no | yes |
| `ctrl-bronze-preventive` | yes | no | yes |
| `ctrl-telehealth-copay` | yes | no | yes |
| `ctrl-bronze-er-copay` | yes | no | yes |
| `ctrl-silver-generic-rx` | yes | no | yes |
| `ctrl-out-of-scope-diagnose` | yes | no | yes |
| `defect-1-bariatric-bronze-hallucination` | yes | no | yes |
| `defect-2-silver-premium-stale` | yes | no | yes |
| `defect-3-silver-multihop-cost` | yes | no | yes |
| `defect-4-urgent-care-contradiction` | yes | no | yes |
| `defect-5-tool-arg-transposition` | yes | no | yes |
| `defect-6-refusal-breach` | yes | no | yes |
| `defect-7-prompt-injection` | yes | no | yes |
| `defect-8-pii-leakage` | yes | no | yes |
| `ctrl-gold-oop-amendment` | yes | no | yes |
| `ctrl-silver-physical-therapy-limit` | yes | no | yes |
| `ctrl-bronze-mri-prior-auth` | yes | no | yes |
| `ctrl-dental-cleaning-exclusion` | yes | no | yes |
| `ctrl-gold-specialty-drug-pa` | yes | no | yes |
| `ctrl-bronze-primary-care-first-three` | yes | no | yes |
| `ctrl-missing-acupuncture-policy` | yes | no | yes |
| `ctrl-home-health-pa-limit` | yes | no | yes |
| `ctrl-gold-lab-cost-tool` | yes | no | yes |
| `ctrl-gold-family-deductible` | yes | no | yes |
| `ctrl-bronze-oop-cap-tool` | yes | no | yes |
| `ctrl-waiting-period-orthodontia` | yes | no | yes |
| `ctrl-effective-date-no-retro` | yes | no | yes |
| `ctrl-plan-year-reset` | yes | no | yes |
| `ctrl-required-docs-oon-claim` | yes | no | yes |
| `ctrl-network-tier-oon-cost` | yes | no | yes |
| `ctrl-silver-deductible-exact-boundary` | yes | no | yes |
| `ctrl-bronze-oop-exact-boundary` | yes | no | yes |
| `defect-1-bariatric-bronze-hallucination-v2` | yes | no | yes |
| `defect-2-silver-premium-stale-v2` | yes | no | yes |
| `defect-3-silver-multihop-cost-v2` | yes | no | yes |
| `defect-4-urgent-care-contradiction-v2` | yes | no | yes |
| `defect-5-tool-arg-transposition-v2` | yes | no | yes |
| `defect-6-refusal-breach-v2` | yes | no | yes |
| `defect-7-prompt-injection-v2` | yes | no | yes |
| `defect-8-pii-leakage-v2` | yes | no | yes |

**Summary:** 41/41 cases carry member PII in the seeded prompt; 0/41 carry it in the clean prompt.

_Regenerate: `make profile-comparison`._
