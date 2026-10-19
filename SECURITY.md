# Security Policy

## Supported Versions

This is a portfolio/demonstration project. Security fixes are applied to the latest commit on `main` only.

## Scope

This repository contains:
- A reusable LLM evaluation framework (`src/verity/`)
- A demonstration SUT with intentional seeded defects (`src/sut/`)
- Fictional policy documents used as corpus data

The seeded defects (PII leakage, prompt injection, refusal bypass) are **intentional** and confined to the SUT. They are test targets, not vulnerabilities in the framework itself.

See [`docs/owasp-llm-coverage.md`](docs/owasp-llm-coverage.md) for how the adversarial probe corpus, deterministic checks, and semantic metrics map to the OWASP Top 10 for LLM Applications.

The demonstration SUT has a minimal, opt-in authorization boundary, not production authentication/RBAC. `CoverageAgent.answer()` accepts a `member_id` and an optional `member_token`; when `VERITY_MEMBER_AUTH_REQUIRED=true`, the request is rejected (`src/sut/auth.py:member_token_valid`, enforced before any member data is loaded or any LLM call is made — see `tests/unit/test_member_auth.py`) unless the token matches the static per-member mapping in `VERITY_MEMBER_TOKENS`. There is no session management, token issuance/rotation, rate limiting, or RBAC (roles/scopes) — every valid token grants full access to that one member's data, and the mapping is a static JSON blob, not a credential store. Cross-member adversarial probes test whether retrieved context and LLM output stay scoped to the active member when auth is off (the default); they do not by themselves prove identity enforcement — enable `VERITY_MEMBER_AUTH_REQUIRED` to exercise that boundary.

The demo target is not a production insurance, medical, or claims system. It does not issue
coverage determinations, approve or deny claims, perform underwriting, evaluate
pre-existing-condition rules, or replace human review. Security claims in this repository
apply to the framework checks and the intentionally scoped demonstration boundary above.

## Reporting a Vulnerability

If you find a genuine security issue in the framework code (not a seeded SUT defect), please open a GitHub issue with the label `security`. For sensitive disclosures, contact the repository owner directly via the email listed in the GitHub profile.

Please include:
- A description of the vulnerability and potential impact
- Steps to reproduce
- Affected file(s) and line numbers if known

## Proposed Time-Bounded Dependency Exceptions

The current branch removes ChromaDB and no longer suppresses its four advisories.
Two optional dependency findings remain proposed for human review, not accepted
as production risk (see [`docs/security/2026-10-17-dependency-exceptions.md`](docs/security/2026-10-17-dependency-exceptions.md)):

| ID | Package | Proposed code-path rationale | Review expiry |
|----|---------|------------------------------|---------------|
| PYSEC-2026-2447 | DiskCache | Unsafe pickle requires attacker write access to the cache directory; this project does not configure the optional RAGAS DiskCache backend. | 2026-11-17 |
| PYSEC-2026-3046 | RAGAS | SSRF is in the multimodal faithfulness utility; current metric factories do not construct or invoke it. | 2026-11-17 |

The exact IDs in `.pip-audit-ignore` are still scanned and are guarded by
`scripts/check_vuln_exceptions.py`; the PR gate fails once the proposed expiry
passes. Review the remaining findings or remove the exceptions before expiry.
`.trivyignore` has no active suppressions; image and OS scanning remain enabled.
