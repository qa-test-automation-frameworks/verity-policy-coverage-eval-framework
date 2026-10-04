# Real embedding model bootstrap — 2026-10-04

[PR gate run 37178349428](https://github.com/qa-test-automation-frameworks/verity-policy-coverage-eval-framework/actions/runs/37178349428)
failed in the deterministic/unit step on both Python versions. The Python 3.13
log recorded 1682 passes, 4 skips and 5 setup errors in chunk metadata tests.
Chroma's parallel model downloader reached checksum verification after the
shared `onnx.tar.gz` had disappeared. This happened before the vulnerability
exception check; an expired exception was not that run's first failure.

Provision the actual default embedding model serially before xdist starts:

```sh
uv sync --frozen --all-extras
make prepare-embeddings
PYTHONPATH=src uv run --no-sync pytest tests/deterministic/test_chunking_contract.py -n 2 -q
```

Preparation uses Chroma's real default embedding function and native asset
checksum verification, then checks that a nonempty vector was returned. CI runs
this step before parallel tests. No test is skipped, no assertion is removed,
and no fake embedding replaces retrieval behavior. A missing/unusable model
fails preparation explicitly.

Validation used CPython 3.13.14 and the isolated frozen dev/report environment:

- A new empty cache under `/tmp/portfolio-tools/verity-onnx-cold-check` downloaded
  the public asset and returned a real **384-dimensional** readiness embedding.
- All **6 unchanged chunk metadata/stable-ID tests passed with 2 workers**, in
  16.69 seconds, using that prepared cache. A temporary pytest plugin redirected
  only Chroma's cache path; model implementation, corpus, assertions and
  persistent collection behavior were unchanged.
- Ruff lint and formatting checks passed for the preparation script.

Network access is needed for initial dependencies/model assets. No provider API
key or paid LLM call was used. This repairs an observed bootstrap race; it does
not establish offline operation for every optional suite, resolve dependency
advisories, or prove the complete PR gate passed. The full remote gate must be
rechecked after the change.
