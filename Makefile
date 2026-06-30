.PHONY: install lint format type test smoke test-deterministic eval-semantic redteam calibrate demo record clean

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
	@echo "Tier 3 — Adversarial / red-team (Promptfoo/DeepTeam) [M5]"
	@echo "Not yet implemented — see M5"

calibrate:
	@echo "Tier 3 — Judge calibration harness [M4]"
	@echo "Not yet implemented — see M4"

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
