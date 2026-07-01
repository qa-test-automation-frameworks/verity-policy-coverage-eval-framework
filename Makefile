.PHONY: install lint format type test smoke test-deterministic eval-semantic hosted-models live-canary redteam redteam-live calibrate calibrate-live trace-demo defects-report report-allure report-site demo record docker-test clean mutation-test

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
install:
	uv sync --all-extras

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------
lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests

type:
	uv run mypy src

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
test:
	PYTHONPATH=src uv run pytest -m "not live" -v

smoke:
	@echo "Running live model-identity smoke test (requires API key in .env)"
	PYTHONPATH=src PYTHONUNBUFFERED=1 uv run pytest -m live -v -s

test-deterministic:
	@echo "Tier 1 — Deterministic eval (cassette replay; no live calls) [M2]"
	PYTHONPATH=src uv run pytest tests/deterministic/ -m "not live" -v

eval-semantic:
	@echo "Tier 2 — Semantic eval (DeepEval + RAGAS; live LLM) [M3]"
	PYTHONPATH=src uv run pytest tests/semantic/ -m semantic -v

hosted-models:
	@echo "Ranking zero-price hosted open-weight models"
	PYTHONPATH=src:. uv run python scripts/select_openrouter_free_models.py --limit 5

live-canary:
	@echo "Live canary with OpenRouter free route"
	@echo "(free-model slugs rotate — run 'make hosted-models' and pass VERITY_MODEL=<slug> to override the default below)"
	VERITY_PROVIDER=openrouter \
	VERITY_MODEL=$${VERITY_MODEL:-nvidia/nemotron-3-ultra-550b-a55b:free} \
	VERITY_SEMANTIC_SAMPLES=1 \
	PYTHONPATH=src uv run pytest \
		tests/live/test_model_identity.py \
		tests/semantic/test_refusal.py \
		tests/semantic/test_tool_use.py \
		-m "live or semantic" -v --maxfail=1

record:
	@echo "Writing hash-keyed cassettes from authored YAML fixtures (no API key required)"
	PYTHONPATH=src uv run python scripts/record_cassettes.py --author $(if $(CASE),--case $(CASE))

redteam:
	@echo "Tier 3 — Adversarial red-team: hermetic pytest (no API key required)"
	PYTHONPATH=src uv run pytest tests/adversarial/ -m adversarial -v

redteam-live:
	@echo "Tier 3 — Adversarial red-team: hermetic pytest + promptfoo live eval"
	PYTHONPATH=src uv run pytest tests/adversarial/ -m adversarial -v
	@if [ -z "$(VERITY_ZAI_API_KEY)" ]; then \
		echo "VERITY_ZAI_API_KEY not set — skipping promptfoo live eval"; \
	else \
		npx --yes promptfoo@latest eval --config promptfoo/redteam.yaml \
			--output reports/redteam/results.json; \
		echo "Promptfoo report written to reports/redteam/results.json"; \
	fi

calibrate:
	@echo "Judge calibration — hermetic replay (authored cassettes; no API key required)"
	PYTHONPATH=src uv run python scripts/run_calibration.py
	@echo "Report written to docs/calibration-report.md"

calibrate-live:
	@echo "Judge calibration — live judge calls (requires API key)"
	PYTHONPATH=src uv run python scripts/run_calibration.py --record

trace-demo:
	@echo "Trace demo — one hermetic agent run with OTEL file exporter (no API key required)"
	VERITY_TRACING=1 VERITY_TRACE_EXPORTER=file PYTHONPATH=src uv run python scripts/trace_demo.py

mutation-test:
	@echo "Mutation testing — src/sut/tools/coverage_calculator.py (requires: uv sync --extra mutation)"
	uv run mutmut run || true
	uv run mutmut results
	@echo "Spans written to reports/traces/"

defects-report:
	@echo "Defects-caught matrix — hermetic replay for defects 5-8; semantic ingestion when available"
	PYTHONPATH=src:. uv run python scripts/defects_report.py
	@echo "Report written to docs/defects-caught.md"

report-allure:
	@echo "Tier 1+3 hermetic suites with Allure results capture (no API key required)"
	PYTHONPATH=src uv run pytest tests/unit/ tests/deterministic/ tests/adversarial/ \
		-m "not live" --alluredir reports/allure-results -v
	@if command -v allure >/dev/null 2>&1; then \
		allure generate reports/allure-results --clean -o reports/allure-report; \
		echo "Allure HTML at reports/allure-report/index.html"; \
	else \
		echo "allure CLI not found — skipping HTML generation (results captured in reports/allure-results/)"; \
	fi

report-site:
	@echo "Building static report site in site/"
	$(MAKE) defects-report
	PYTHONPATH=src:. uv run python scripts/build_report_site.py
	@echo "Site ready at site/index.html"

# ---------------------------------------------------------------------------
# SUT demo
# ---------------------------------------------------------------------------
demo:
	@if [ -z "$(QUERY)" ]; then \
		echo "Usage: make demo QUERY='What is my deductible?'"; \
		exit 1; \
	fi
	PYTHONPATH=src uv run python -m sut.agent "$(QUERY)"

# ---------------------------------------------------------------------------
# Container
# ---------------------------------------------------------------------------
docker-test:
	@echo "Building container and running Tier-1 checks (no API key required)"
	docker build -t verity-eval:local . && docker run --rm verity-eval:local

# Cleanup
# ---------------------------------------------------------------------------
clean:
	rm -rf .chroma/ .pytest_cache/ .mypy_cache/ .ruff_cache/ reports/ htmlcov/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
