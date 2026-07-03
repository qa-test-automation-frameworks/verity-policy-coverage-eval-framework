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

## Known Accepted Vulnerabilities in Dependencies

Three vulnerabilities in transitive dependencies are currently acknowledged and accepted (see `.pip-audit-ignore`):

| ID | Package | Reason accepted | Expires |
|----|---------|-----------------|---------|
| PYSEC-2026-311 | chromadb | Requires `trust_remote_code=true`; not used in this project | 2026-10-01 |
| CVE-2025-69872 | diskcache | Requires attacker write access to local cache directory | 2026-10-01 |
| CVE-2026-6587 | ragas | Affects multi-modal module not imported in this project | 2026-10-01 |

Each entry in `.pip-audit-ignore` carries an `Expires:` date. `scripts/check_vuln_exceptions.py`
runs in the PR gate and fails once that date passes, so an accepted risk cannot silently
outlive its review window — the entry must be re-evaluated and either re-dated (with updated
reasoning) or removed once the affected package releases a fix.
