"""Unit tests for the statistical threshold engine."""

from __future__ import annotations

import pytest

from verity.statistics import StatResult, aggregate, run_n_samples, threshold_pass


class TestAggregate:
    def test_single_score(self) -> None:
        stat = aggregate([0.8])
        assert stat.n == 1
        assert stat.mean == pytest.approx(0.8)
        assert stat.median == pytest.approx(0.8)
        assert stat.stdev == 0.0

    def test_multiple_scores_mean(self) -> None:
        scores = [0.6, 0.8, 1.0]
        stat = aggregate(scores)
        assert stat.mean == pytest.approx(0.8)

    def test_median_odd(self) -> None:
        stat = aggregate([0.2, 0.5, 0.9])
        assert stat.median == pytest.approx(0.5)

    def test_median_even(self) -> None:
        stat = aggregate([0.4, 0.6])
        assert stat.median == pytest.approx(0.5)

    def test_stdev_calculated(self) -> None:
        stat = aggregate([0.0, 1.0])
        assert stat.stdev > 0

    def test_pass_rate_all_above(self) -> None:
        stat = aggregate([0.8, 0.9, 1.0], score_threshold=0.7)
        assert stat.pass_rate == pytest.approx(1.0)

    def test_pass_rate_none_above(self) -> None:
        stat = aggregate([0.1, 0.2, 0.3], score_threshold=0.5)
        assert stat.pass_rate == pytest.approx(0.0)

    def test_pass_rate_partial(self) -> None:
        stat = aggregate([0.3, 0.7, 0.9], score_threshold=0.5)
        assert stat.pass_rate == pytest.approx(2 / 3)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            aggregate([])

    def test_scores_preserved(self) -> None:
        original = [0.3, 0.7, 0.9]
        stat = aggregate(original)
        assert stat.scores == original

    def test_n_equals_len_scores(self) -> None:
        stat = aggregate([0.1, 0.2, 0.3, 0.4])
        assert stat.n == 4


class TestRunNSamples:
    def test_calls_fn_n_times(self) -> None:
        count = 0

        def fn() -> float:
            nonlocal count
            count += 1
            return 0.5

        run_n_samples(fn, n=7)
        assert count == 7

    def test_returns_stat_result(self) -> None:
        stat = run_n_samples(lambda: 0.9, n=3)
        assert isinstance(stat, StatResult)

    def test_n_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="n must be >= 1"):
            run_n_samples(lambda: 0.5, n=0)

    def test_deterministic_fn(self) -> None:
        stat = run_n_samples(lambda: 0.75, n=5)
        assert stat.mean == pytest.approx(0.75)
        assert stat.stdev == pytest.approx(0.0)
        assert stat.pass_rate == pytest.approx(1.0)

    def test_alternating_scores(self) -> None:
        results = [0.3, 0.7, 0.3, 0.7]
        idx = [0]

        def fn() -> float:
            v = results[idx[0] % len(results)]
            idx[0] += 1
            return v

        stat = run_n_samples(fn, n=4, score_threshold=0.5)
        assert stat.pass_rate == pytest.approx(0.5)


class TestThresholdPass:
    def _stat(self, mean: float, median: float, pass_rate: float) -> StatResult:
        return StatResult(
            scores=[mean],
            mean=mean,
            median=median,
            stdev=0.0,
            pass_rate=pass_rate,
            n=1,
        )

    def test_mean_mode_pass(self) -> None:
        stat = self._stat(mean=0.8, median=0.7, pass_rate=0.9)
        assert threshold_pass(stat, threshold=0.7, mode="mean") is True

    def test_mean_mode_fail(self) -> None:
        stat = self._stat(mean=0.6, median=0.9, pass_rate=1.0)
        assert threshold_pass(stat, threshold=0.7, mode="mean") is False

    def test_median_mode(self) -> None:
        stat = self._stat(mean=0.5, median=0.8, pass_rate=0.5)
        assert threshold_pass(stat, threshold=0.7, mode="median") is True

    def test_pass_rate_mode(self) -> None:
        stat = self._stat(mean=0.5, median=0.5, pass_rate=0.8)
        assert threshold_pass(stat, threshold=0.7, mode="pass_rate") is True

    def test_all_mode_all_pass(self) -> None:
        stat = self._stat(mean=0.9, median=0.9, pass_rate=0.9)
        assert threshold_pass(stat, threshold=0.7, mode="all") is True

    def test_all_mode_one_fails(self) -> None:
        stat = self._stat(mean=0.9, median=0.9, pass_rate=0.5)
        assert threshold_pass(stat, threshold=0.7, mode="all") is False

    def test_invalid_mode_raises(self) -> None:
        stat = self._stat(0.5, 0.5, 0.5)
        with pytest.raises(ValueError, match="mode must be one of"):
            threshold_pass(stat, threshold=0.5, mode="invalid")

    def test_default_mode_is_mean(self) -> None:
        stat = self._stat(mean=0.8, median=0.2, pass_rate=0.2)
        assert threshold_pass(stat, threshold=0.7) is True

    def test_stat_str(self) -> None:
        stat = self._stat(0.8, 0.75, 0.9)
        s = str(stat)
        assert "n=1" in s
        assert "mean=0.800" in s
