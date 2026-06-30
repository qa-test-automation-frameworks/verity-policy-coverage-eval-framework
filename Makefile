.PHONY: install lint format type test smoke test-deterministic eval-semantic redteam redteam-live calibrate calibrate-live demo record clean

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
	PYTHONPATH=src uv run pytest -m live -v -s

test-deterministic:
	@echo "Tier 1 — Deterministic eval (cassette replay; no live calls) [M2]"
	PYTHONPATH=src uv run pytest tests/deterministic/ -m "not live" -v

eval-semantic:
	@echo "Tier 2 — Semantic eval (DeepEval + RAGAS; live LLM) [M3]"
	PYTHONPATH=src uv run pytest tests/semantic/ -m semantic -v

record:
	@echo "Writing hash-keyed cassettes from authored YAML fixtures (no API key required)"
	PYTHONPATH=src uv run python scripts/record_cassettes.py --author

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
# Cleanup
# ---------------------------------------------------------------------------
clean:
	rm -rf .chroma/ .pytest_cache/ .mypy_cache/ .ruff_cache/ reports/ htmlcov/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
