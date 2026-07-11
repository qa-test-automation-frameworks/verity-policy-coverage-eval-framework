from pathlib import Path

from scripts.dataset_inventory import count_cases, corpus_fingerprint, inventory


def test_inventory_uses_distinct_golden_and_calibration_counts() -> None:
    result = inventory(Path(__file__).parents[2])
    assert result["golden_cases"] == 69
    assert result["calibration_cases"] == 56
    assert len(result["corpus_fingerprint"]) == 64


def test_count_cases_ignores_non_case_yaml(tmp_path: Path) -> None:
    (tmp_path / "cases.yaml").write_text("cases:\n  - id: one\n  - id: two\n", encoding="utf-8")
    assert count_cases(tmp_path) == 2


def test_corpus_fingerprint_changes_with_content(tmp_path: Path) -> None:
    path = tmp_path / "policy.md"
    path.write_text("one", encoding="utf-8")
    first = corpus_fingerprint(tmp_path)
    path.write_text("two", encoding="utf-8")
    assert corpus_fingerprint(tmp_path) != first
