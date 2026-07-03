# Extending the Framework

This guide covers the four most common extension points: adding a provider, expanding the dataset, wiring a new evaluator, and adding a report artifact.

---

## Extension Contracts

The sections below are how-tos; this section states the actual contract each extension point
must satisfy — the minimum shape the rest of the framework depends on, independent of any one
example. `src/verity/` is framework-stable (these contracts apply); `src/sut/` is the demo
application these contracts are exercised against, not itself an extension point.

| Extension point | Contract | Enforced by |
|---|---|---|
| **Provider** | A `Provider` enum member with a `_PROVIDER_DEFAULTS` entry (`canonical_model`, `litellm_prefix`, `litellm_model`, `api_base`) in `src/verity/config.py`, plus an `<name>_api_key` / `<name>_api_base` field pair on `Settings`. `resolve_provider()` must return a valid LiteLLM model string for it. | `tests/unit/test_config.py`; any live call routes through `LLMProvider`/LiteLLM, so a malformed entry fails on first live call. |
| **Golden dataset case** | A `GoldenCase` (`src/verity/golden.py`) — `id` unique, `query` non-empty, and enough of `must_contain`/`must_not_contain`/`expected_citations`/`expected_tool`/`semantic_metrics` set that at least one checker in `src/verity/checks.py` has something to assert against. | `verity.golden.load_golden()` validates via Pydantic at load time; `tests/deterministic/` and `tests/semantic/` parametrize over every loaded case, so a schema violation fails collection. |
| **Retrieval benchmark** | A `RetrievalBenchmark` (`src/verity/retrieval_eval.py`) — `case_id`, `query`, `expected_sources`, and `min_source_precision` in `[0, 1]`. `expected_chunk_ids` is optional and adds chunk-level precision/recall (source-level scoring alone can't tell "right file, wrong section" from a real hit); populate it from `datasets/retrieval/recorded_chunks.json` when available. | `tests/deterministic/test_retrieval_benchmark.py` parametrizes over every loaded benchmark; `tests/deterministic/test_retriever_regression.py::test_real_retrieval_chunk_precision_recall` exercises the chunk-level path against the real retriever. |
| **Adversarial probe** | An `AdversarialProbe` (`src/verity/adversarial.py`) with `category`, `prompt`, `defense`, and `expected_outcome` (`defended` or `breached` — both are valid, seeded-defect probes are expected to report `breached`). | `tests/adversarial/test_redteam_hermetic.py` parametrizes over every loaded probe. |
| **Semantic evaluator** | A `make_<metric>(judge) -> Metric` factory in `src/verity/metrics/` returning an object with `.measure(test_case)` (DeepEval) or `.single_turn_score(sample)` (RAGAS), plus a module-level `THRESHOLD_<METRIC>` constant. The optional structural types live in `src/verity/protocols.py` (`JudgeProtocol`, `MetricProtocol`, `MetricFactory`). Callers compare the returned score against that constant directly — the factory itself does not gate. | `tests/unit/test_semantic_metric_declarations.py` verifies that case-level metric declarations map to implemented semantic tests; wiring a new metric into a `tests/semantic/test_*.py` file following the existing pattern exercises the runtime path. |
| **Report artifact** | A script under `scripts/` exposing a pure `render_*()` function plus a `run()`/`main()` that writes `docs/<name>.md` and, if machine-readable output is needed, `reports/<name>/<name>.json`. Must run hermetically (no live API calls) so it can be added to the PR gate's evidence-smoke step. | `scripts/check_module_coverage.py` and the PR gate's "Hermetic Tier-2/3 evidence gate" step are examples of running a report script as a CI assertion, not just a doc generator. |

Most contracts remain structural and are checked by the tests above running the concrete
implementations. Judge and metric factory shapes also have optional `Protocol` definitions in
`src/verity/protocols.py`, so new adapter code can opt into type-checked contracts without
adding runtime inheritance. If you're adding a new instance of an existing extension point (a
provider, a golden case, a benchmark, a probe), the parametrized test suites already validate it
as soon as it's loaded. If you're adding a new *kind* of extension point not listed here, add a
row to this table when you do.

---

## Adding a Provider

The framework routes all LLM calls through `src/verity/providers.py` via LiteLLM. To use a different model or provider:

1. **Set environment variables.** The `Settings` class in `src/verity/config.py` reads `VERITY_PROVIDER`, `VERITY_MODEL`, and the matching API key (`VERITY_ZAI_API_KEY`, `VERITY_OPENROUTER_API_KEY`, `VERITY_TOGETHER_API_KEY`, `VERITY_NVIDIA_API_KEY`, or `VERITY_GOOGLE_API_KEY`).

2. **Add your key to `.env`.**
   ```bash
   VERITY_PROVIDER=openrouter
   VERITY_MODEL=openai/gpt-4o-mini
   VERITY_OPENROUTER_API_KEY=sk-...
   ```

3. **Update `resolved_provider()` if needed.** `Settings.resolved_provider()` maps provider name + model to a LiteLLM model string and API base URL. Update the routing table only for providers not already listed.

4. **Re-record cassettes.** Any change to the model string or system prompt invalidates existing Tier-1 cassettes. Run `make record` to regenerate them from the authored YAML fixtures.

---

## Expanding the Dataset

### Adding a golden case

1. Add a new entry to `datasets/golden/cases.yaml` following the `GoldenCase` schema (`src/verity/golden.py`). Required fields: `id`, `query`, `member_id`, `behavior`, `ground_truth`. For a case whose correct answer is a specific amount or date, prefer `numeric_expectations`/`date_expectations` over `must_contain`: they compare parsed values (`comparator: eq|gte|lte|gt|lt|range`, or an inclusive `on_or_after`/`on_or_before` date range) instead of an exact substring, so a correctly-worded but differently-formatted answer (e.g. "3800.00" vs "$3,800") still passes. See `ctrl-gold-oop-amendment` and `ctrl-bronze-oop-exact-boundary` in `datasets/golden/cases.yaml` for examples.

2. Add a retrieval fixture at `datasets/cassettes/retrieval/<case_id>.json` — a JSON array of `{text, source, section, chunk_id}` objects.

3. For a clean control case (`expects_defect: false`), author the expected LLM response at `datasets/cassettes/authored/<case_id>.yaml`.

4. Run `make record CASE=<case_id>` to compute the SHA-256 request key and write the cassette.

5. Commit the new fixture, authored YAML, and generated cassette alongside the golden case.

### Adding a retrieval benchmark

Add an entry to `datasets/retrieval/benchmarks.yaml`. Each entry specifies a `case_id`, `query`, `expected_sources`, `required_terms`, and `min_source_precision`. The deterministic benchmark test (`tests/deterministic/test_retrieval_benchmark.py`) will pick it up automatically.

### Adding an adversarial probe

Add a probe to `datasets/adversarial/probes.yaml` following the `AdversarialProbe` schema (`src/verity/adversarial.py`). Author the cassette in `datasets/adversarial/cassettes/` using `scripts/author_adversarial_cassettes.py`.

---

## Wiring a New Evaluator

Tier-2 evaluators live in `src/verity/metrics/`. Each metric is a thin adapter over DeepEval or RAGAS:

1. Add a factory function in the relevant module (e.g., `deepeval_metrics.py` or `ragas_metrics.py`).

2. Wire it into a semantic test in `tests/semantic/`. The pattern is:
   ```python
   metric = make_my_metric(judge)
   score = metric.measure(test_case)
   assert score >= threshold
   ```

3. Document the threshold in `docs/thresholds.md`.

4. Add judge calibration examples for the new metric to `datasets/calibration/labeled.yaml` if it uses a rubric that can drift.

---

## Adding a Report Artifact

Report artifacts go in `reports/` (git-ignored) and committed summaries go in `docs/`.

1. **Script.** Add a script in `scripts/` that generates the artifact. Follow the pattern in `scripts/defects_report.py`: pure render functions, a `run()` entry point, and a `main()` that writes `docs/<name>.md` and `reports/<name>/<name>.json`.

2. **Make target.** Add a target to the Makefile:
   ```make
   my-report:
       PYTHONPATH=src uv run python scripts/my_report.py
   ```

3. **Report site.** Add the new page to `scripts/build_report_site.py`. Follow the existing pattern: check for the doc, call `_md_to_html`, fall back to `_placeholder_html`.

4. **Nav.** Add the new page link to `_NAV` in `build_report_site.py`.

5. **Tests.** Add a unit test asserting the new page appears in `build_site()` return value.

---

## Updating Cassettes After a Breaking Change

Changing the model, temperature, system prompt template, corpus chunks, or tool schema changes the SHA-256 request key and invalidates all downstream cassettes. The manifest test (`tests/deterministic/test_regression_cassette.py`) will fail, listing the affected cases.

```bash
# Regenerate all cassettes
make record

# Regenerate one case
make record CASE=ctrl-gold-oop-amendment

# Commit
git add datasets/cassettes/
git commit -m "update cassettes: <reason>"
```
