# Native execution evidence

The PR gate emits one schema-v3 record per Python matrix entry from pytest's
native JUnit XML. The record is scoped to `verity.deterministic-py<version>`;
the matrix entries remain separate, and the overall workflow result is not
presented as one combined test population. On Python 3.12.15, the gate also
runs the intentionally failing `evidence_control` testcase in isolation and
records it as `verity.failure-control-py3.12.15`. The gate is healthy only if
pytest exits nonzero, exactly one testcase is reported failed, and the native
failure message contains `VERITY_EVIDENCE_CONTROL_FAILURE`.

The adapter counts JUnit testcase invocations. Selected includes skipped
testcases; executed excludes skips; failures and errors count as failed final
outcomes. It reconciles each suite and the report totals with their testcase
children. Missing, malformed, empty, or inconsistent reports are recorded as
unavailable evidence and cannot pass validation. Testcase names and failure
messages are not copied into the portfolio record. pytest JUnit XML does not
provide a reliable retry count, so `retried` is zero and the limitation is
explicitly recorded.

The semantic-evaluation workflow emits a separate `verity.semantic-evaluation`
record for full-suite runs. Manual smoke runs emit `verity.semantic-smoke` under
the same optional credentialed evidence policy, keeping their quick compatibility
signal separate from full-suite history. If no provider key is configured, the
selected suite records an explicit optional skip
with null counts. If execution is attempted but the native JUnit or semantic
result manifest is absent, it records unavailable evidence. A provider key
that exists for a different provider does not turn a missing selected-provider
key into a skip; that remains a configuration failure. Semantic evaluation is
credentialed, optional, and uses the quarterly freshness policy; it does not
replace the required deterministic gate.

The schema and freshness-policy files are pinned snapshots of the shared
portfolio evidence contract. Their current SHA-256 values are:

- `portfolio/evidence/evidence-v3.schema.json`:
  `40502a47e825755d216e35ea19716ad7de69e47accd6aed1cfb3607160e4d1b9`
- `portfolio/evidence/freshness-policies.json`:
  `1313329c1c06bd3a056dd1ed7d25c631036cae58480fdc4e767f22a0a01a568e`

Run `uv run --extra dev -- python scripts/evidence.py --help` for the adapter
interface. Validate a generated record with
`uv run --extra dev -- python scripts/validate_evidence.py reports/evidence/<record>.json`.
The workflows upload native JUnit XML and records as ephemeral 30-day GitHub
Actions artifacts. Durable publication and portfolio dashboard ingestion are
separate publication and dashboard work; these artifacts are not durable portfolio
history and do not establish production behavior.

The execution record is immutable and is written before the trusted publisher
runs, so its `publication.disposition` may say `pending` with an explanation
that the workflow run has not yet been published. After the publisher validates
and uploads that run, the public `latest.json` index records its final
publication status. Review the index for current publication state; the earlier
record describes the state at execution time and is not rewritten.
