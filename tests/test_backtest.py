"""Tests for the vectorized backtest engine (SPEC Phase 4)."""

import pandas as pd
import pytest

from marketlab.backtest import BacktestConfig, run_backtest
from marketlab.strategies.buy_and_hold import BuyAndHold


def rising_prices(n=120):
    idx = pd.date_range("2026-01-01", periods=n, freq="min")
    return pd.Series(100.0 + 0.5 * pd.Series(range(n), index=idx), index=idx)


class TestBuyAndHold:
    def test_rising_market_is_profitable_with_single_entry(self):
        prices = rising_prices()
        result = run_backtest(prices, BuyAndHold().generate_signals(prices.to_frame("close")))
        assert result.metrics["total_return"] > 0
        assert result.metrics["trades"] == 1
        assert 0 < result.metrics["exposure"] <= 1

    def test_known_drawdown_series(self):
        idx = pd.date_range("2026-01-01", periods=4, freq="min")
        prices = pd.Series([100.0, 110.0, 90.0, 95.0], index=idx)
        config = BacktestConfig(initial_capital=100.0, fee_rate=0.0, slippage_bps=0.0)
        result = run_backtest(prices, BuyAndHold().generate_signals(prices.to_frame("close")), config)
        # equity: 100 → 110 → 90 → 95; deepest drawdown is bar 3 vs peak 110.
        assert result.equity.iloc[-1] == pytest.approx(95.0)
        assert result.metrics["max_drawdown"] == pytest.approx(90.0 / 110.0 - 1.0)


class TestCosts:
    def test_zero_signal_means_flat_equity_and_no_costs(self):
        prices = rising_prices()
        flat = pd.Series(0.0, index=prices.index)
        result = run_backtest(prices, flat)
        assert result.metrics["total_return"] == 0.0
        assert result.metrics["trades"] == 0
        assert result.metrics["sharpe"] == 0.0
        assert result.metrics["total_cost"] == 0.0

    def test_fees_strictly_reduce_returns(self):
        prices = rising_prices()
        signals = BuyAndHold().generate_signals(prices.to_frame("close"))
        free = run_backtest(
            prices, signals, BacktestConfig(fee_rate=0.0, slippage_bps=0.0)
        )
        costly = run_backtest(
            prices, signals, BacktestConfig(fee_rate=0.01, slippage_bps=50.0)
        )
        assert free.metrics["total_return"] > costly.metrics["total_return"]
        assert costly.metrics["total_cost"] > 0


class TestNoLookahead:
    def test_changing_signal_only_affects_future_equity(self):
        prices = rising_prices(60)
        signals = pd.Series(1.0, index=prices.index)
        k = 30
        shifted = signals.copy()
        shifted.iloc[k] = -1.0  # flip decision made at bar k's close

        base = run_backtest(prices, signals, BacktestConfig(initial_capital=100.0))
        altered = run_backtest(prices, shifted, BacktestConfig(initial_capital=100.0))

        # Equity through bar k must be identical (signal k not yet executed).
        pd.testing.assert_series_equal(
            base.equity.iloc[: k + 1], altered.equity.iloc[: k + 1]
        )
        # Bar k+1 onward must differ (rising market: short ≠ long).
        assert base.equity.iloc[k + 1] != altered.equity.iloc[k + 1]


class TestInputValidation:
    def test_misaligned_index_rejected(self):
        prices = rising_prices(10)
        other_index = pd.date_range("2027-01-01", periods=10, freq="min")
        with pytest.raises(ValueError, match="index"):
            run_backtest(prices, pd.Series(1.0, index=other_index))

    def test_empty_inputs_rejected(self):
        with pytest.raises(ValueError, match="non-empty"):
            run_backtest(pd.Series(dtype=float), pd.Series(dtype=float))

    def test_negative_price_rejected(self):
        idx = pd.date_range("2026-01-01", periods=5, freq="min")
        prices = pd.Series([100.0, -1.0, 102.0, 103.0, 104.0], index=idx)
        with pytest.raises(ValueError, match="positive"):
            run_backtest(prices, pd.Series(1.0, index=idx))
