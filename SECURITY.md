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

## Dependency findings and exclusions

There are currently **no active vulnerability exclusions**. The three October 1,
2026 exclusions were removed after expiry; their historical rationale is retained
in [the archive](docs/security/expired-exceptions-2026-10-01.md). This does not mean
that the dependency scan is clean. Unresolved advisories fail the scanner gate.

Advisory fixes are selected from the actual locked environment, including optional
semantic/report/development dependencies. A scan of the smaller runtime alone
cannot establish that the full test environment is clean. Distinguish scanner
execution failure from a completed scan that found vulnerable packages.

Any future exclusion must name the advisory/package/version, affected path,
exposure reasoning, remediation action, accountable maintainer role, evidence of
review, and its own review/expiry date. Do not represent automated analysis as
independent human risk acceptance. `scripts/check_vuln_exceptions.py` rejects
expired, missing or malformed dates, duplicate IDs and reused dates. The scanner
continues to run independently; passing the exclusion-file check is not proof of
no vulnerabilities.
