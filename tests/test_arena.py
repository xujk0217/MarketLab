"""Tests for the Strategy Arena (SPEC §27, Phase 7)."""

import numpy as np
import pandas as pd
import pytest

from marketlab.arena import arena, label_segments, segment_metrics
from marketlab.backtest.engine import BacktestConfig, run_backtest
from marketlab.core.regime import RegimeType
from marketlab.strategies import BuyAndHold


def uptrend_candles(n=400):
    idx = pd.date_range("2026-08-20", periods=n, freq="min", tz="UTC")
    close = pd.Series(100.0 * (1.002 ** np.arange(n)), index=idx)
    return pd.DataFrame(
        {
            "timestamp": idx,
            "open": close,
            "high": close * 1.0005,
            "low": close * 0.9995,
            "close": close,
            "volume": 1000.0,
        }
    )


class TestLabelSegments:
    def test_segments_cover_history_without_gaps(self):
        candles = uptrend_candles()
        segments = label_segments(candles)
        # Labeling starts after the detector's minimum warm-up window.
        assert segments[0].start == 63  # max(60, 30) + 3
        assert segments[-1].end == len(candles)
        for a, b in zip(segments, segments[1:], strict=False):
            assert a.end == b.start

    def test_steady_uptrend_labels_all_trend_up(self):
        candles = uptrend_candles()
        segments = label_segments(candles)
        assert all(s.regime is RegimeType.TREND_UP for s in segments)

    def test_too_short_history_rejected(self):
        with pytest.raises(ValueError, match="bars"):
            label_segments(uptrend_candles(50))


class TestSegmentMetrics:
    def test_known_values(self):
        returns = pd.Series([0.10, -0.10])
        metrics = segment_metrics(returns, bars_per_year=365 * 24 * 60)
        assert metrics["total_return"] == pytest.approx((1.1 * 0.9) - 1.0)
        assert metrics["max_drawdown"] == pytest.approx(0.99 / 1.10 - 1.0)
        assert metrics["n_bars"] == 2

    def test_zero_variance_sharpe_is_zero(self):
        metrics = segment_metrics(pd.Series([0.01] * 5), bars_per_year=100.0)
        assert metrics["sharpe"] == 0.0

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            segment_metrics(pd.Series(dtype=float), bars_per_year=1.0)


class TestArena:
    def test_buyhold_cell_matches_engine_over_labeled_region(self):
        candles = uptrend_candles()  # entirely TREND_UP → one regime column
        config = BacktestConfig(fee_rate=0.0, slippage_bps=0.0)
        matrix, segments = arena(
            candles, {"buy_and_hold": BuyAndHold()}, config=config, step=60
        )
        engine = run_backtest(
            candles["close"], BuyAndHold().generate_signals(candles), config
        )
        # Arena aggregates only the labeled region (warm-up bars excluded),
        # so compare against the engine's return over that same region.
        labeled_start = segments[0].start
        expected = (
            engine.equity.iloc[-1] / engine.equity.iloc[labeled_start - 1] - 1.0
        )
        assert matrix.loc["buy_and_hold", "TREND_UP"] == pytest.approx(expected)

    def test_matrix_has_no_unexpected_columns_and_no_nan_for_covered_regimes(self):
        candles = uptrend_candles()
        matrix, _ = arena(candles, {"bh": BuyAndHold()}, step=60)
        assert list(matrix.columns) == ["TREND_UP"]
        assert not matrix.isna().any().any()

    def test_multiple_strategies_indexed_by_name(self):
        from marketlab.strategies import Momentum, SmaCross

        candles = uptrend_candles()
        matrix, _ = arena(
            candles,
            {"bh": BuyAndHold(), "mom": Momentum(lookback=20), "sma": SmaCross(5, 20)},
            step=120,
        )
        assert set(matrix.index) == {"bh", "mom", "sma"}

    def test_empty_strategies_rejected(self):
        with pytest.raises(ValueError):
            arena(uptrend_candles(), {})
