# Security Policy

## Supported Versions

This is a portfolio/demonstration project. Security fixes are applied to the latest commit on `main` only.

## Scope

This repository contains:
- A reusable LLM evaluation framework (`src/verity/`)
- A demonstration SUT with intentional seeded defects (`src/sut/`)
- Fictional policy documents used as corpus data

The seeded defects (PII leakage, prompt injection, refusal bypass) are **intentional** and confined to the SUT. They are test targets, not vulnerabilities in the framework itself.

## Reporting a Vulnerability

If you find a genuine security issue in the framework code (not a seeded SUT defect), please open a GitHub issue with the label `security`. For sensitive disclosures, contact the repository owner directly via the email listed in the GitHub profile.

Please include:
- A description of the vulnerability and potential impact
- Steps to reproduce
- Affected file(s) and line numbers if known

## Known Accepted Vulnerabilities in Dependencies

Three vulnerabilities in transitive dependencies are currently acknowledged and accepted (see `.pip-audit-ignore`):

| ID | Package | Reason accepted |
|----|---------|-----------------|
| PYSEC-2026-311 | chromadb | Requires `trust_remote_code=true`; not used in this project |
| CVE-2025-69872 | diskcache | Requires attacker write access to local cache directory |
| CVE-2026-6587 | ragas | Affects multi-modal module not imported in this project |

These will be re-evaluated when the affected packages release a fix.
