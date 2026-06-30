# Extending the Framework

This guide covers the four most common extension points: adding a provider, expanding the dataset, wiring a new evaluator, and adding a report artifact.

---

## Adding a Provider

The framework routes all LLM calls through `src/verity/providers.py` via LiteLLM. To use a different model or provider:

1. **Set environment variables.** The `Settings` class in `src/verity/config.py` reads `VERITY_PROVIDER`, `VERITY_MODEL`, and the matching API key (`VERITY_ZAI_API_KEY`, `VERITY_OPENROUTER_API_KEY`, or `VERITY_TOGETHER_API_KEY`).

2. **Add your key to `.env`.**
   ```bash
   VERITY_PROVIDER=openrouter
   VERITY_MODEL=openai/gpt-4o-mini
   VERITY_OPENROUTER_API_KEY=sk-...
   ```

3. **Update `resolved_provider()` if needed.** `Settings.resolved_provider()` maps provider name + model to a LiteLLM model string and API base URL. Add a new branch for providers not already listed.

4. **Re-record cassettes.** Any change to the model string or system prompt invalidates existing Tier-1 cassettes. Run `make record` to regenerate them from the authored YAML fixtures.

---

## Expanding the Dataset

### Adding a golden case

1. Add a new entry to `datasets/golden/cases.yaml` following the `GoldenCase` schema (`src/verity/golden.py`). Required fields: `id`, `query`, `member_id`, `behavior`, `ground_truth`.

2. Add a retrieval fixture at `datasets/cassettes/retrieval/<case_id>.json` — a JSON array of `{text, source, section, chunk_id}` objects.

3. For a clean control case (`expects_defect: false`), author the expected LLM response at `datasets/cassettes/authored/<case_id>.yaml`.

4. Run `make record CASE=<case_id>` to compute the SHA-256 request key and write the cassette.

5. Commit the new fixture, authored YAML, and generated cassette alongside the golden case.

### Adding a retrieval benchmark

Add an entry to `datasets/retrieval/benchmarks.yaml`. Each entry specifies a `case_id`, `query`, `expected_sources`, `required_terms`, and `min_context_precision`. The deterministic benchmark test (`tests/deterministic/test_retrieval_benchmark.py`) will pick it up automatically.

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
