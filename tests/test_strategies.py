"""Tests for strategy implementations (SPEC Phase 3)."""

import numpy as np
import pandas as pd
import pytest

from marketlab.strategies import (
    BuyAndHold,
    MeanReversion,
    Momentum,
    SmaCross,
)


def frame_from_close(close_values):
    idx = pd.date_range("2026-01-01", periods=len(close_values), freq="min")
    close = pd.Series(np.asarray(close_values, dtype=float), index=idx)
    return pd.DataFrame({"close": close})


class TestBuyAndHold:
    def test_always_long(self):
        signals = BuyAndHold().generate_signals(frame_from_close([100.0] * 10))
        assert (signals == 1.0).all()


class TestMomentum:
    def test_rising_market_signals_long_after_warmup(self):
        n = 60
        idx = pd.date_range("2026-01-01", periods=n, freq="min")
        prices = pd.Series(100.0 + 0.5 * np.arange(n), index=idx)
        signals = Momentum(lookback=20).generate_signals(prices.to_frame("close"))
        assert (signals.iloc[:20] == 0.0).all()  # warm-up not tradable
        assert (signals.iloc[20:] == 1.0).all()

    def test_falling_market_signals_short(self):
        n = 60
        idx = pd.date_range("2026-01-01", periods=n, freq="min")
        prices = pd.Series(200.0 - 0.5 * np.arange(n), index=idx)
        signals = Momentum(lookback=20).generate_signals(prices.to_frame("close"))
        assert (signals.iloc[20:] == -1.0).all()

    def test_invalid_params_rejected(self):
        with pytest.raises(ValueError):
            Momentum(lookback=0)


class TestMeanReversion:
    def test_extreme_dip_is_bought(self):
        values = [100.0] * 30 + [90.0]
        signals = MeanReversion(window=20, entry_z=2.0).generate_signals(
            frame_from_close(values)
        )
        assert signals.iloc[-1] == 1.0  # z ≈ -4.25 at the dip bar

    def test_quiet_market_stays_flat(self):
        rng = np.random.default_rng(3)
        values = 100.0 * (1 + rng.normal(0, 0.001, 120))
        signals = MeanReversion(window=20, entry_z=3.0).generate_signals(
            frame_from_close(values)
        )
        assert (signals == 0.0).all()


class TestSmaCross:
    def test_uptrend_then_downtrend_flips_signal_off(self):
        rise = np.linspace(100, 200, 60)
        fall = np.linspace(200, 100, 60)
        signals = SmaCross(fast=5, slow=20).generate_signals(frame_from_close(np.r_[rise, fall]))
        assert (signals.iloc[25:55] == 1.0).all()  # firmly above during the rise
        assert (signals.iloc[-15:] == 0.0).any() or (signals.iloc[-15:] == -1.0).any()
        # After enough falling bars the fast SMA must drop to/below the slow SMA.
        assert signals.iloc[-1] <= 0.0

    def test_invalid_params_rejected(self):
        with pytest.raises(ValueError):
            SmaCross(fast=50, slow=20)
