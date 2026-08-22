"""Tests for the feature layer (SPEC Phase 2)."""

import numpy as np
import pandas as pd
import pytest

from marketlab.features import FeatureConfig, build_features


def candles_frame(closes, volumes=None):
    n = len(closes)
    idx = pd.date_range("2026-08-21", periods=n, freq="min", tz="UTC")
    close = pd.Series(np.asarray(closes, dtype=float), index=idx)
    if volumes is None:
        volumes = [1.0] * n
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.asarray(volumes, dtype=float),
        }
    )


class TestBuildFeatures:
    def test_log_return_and_range_are_exact(self):
        frame = build_features(candles_frame([100.0, 101.0, 100.5]))
        assert frame["log_return_1"].iloc[1] == pytest.approx(np.log(101.0 / 100.0))
        assert frame["log_return_1"].iloc[0] != frame["log_return_1"].iloc[0]  # NaN warm-up
        # high = close*1.01, low = close*0.99 → range/close = 0.02
        assert np.allclose(frame["hl_range_pct"], 0.02)

    def test_volume_ratio_known_value(self):
        frame = build_features(
            candles_frame([100.0] * 3, volumes=[10.0, 20.0, 30.0]),
            FeatureConfig(volume_window=2, realized_vol_window=2),
        )
        # rolling mean of last 2 volumes at bar 2 = (20+30)/2 = 25
        assert frame["volume_ratio_2"].iloc[2] == pytest.approx(30.0 / 25.0)

    def test_momentum_lookback_columns(self):
        closes = list(np.linspace(100, 110, 61))
        frame = build_features(candles_frame(closes), FeatureConfig(momentum_lookbacks=(5, 60)))
        for lag in (5, 60):
            col = f"return_lag{lag}"
            assert col in frame.columns
            expected = closes[-1] / closes[-1 - lag] - 1
            assert frame[col].iloc[-1] == pytest.approx(expected)

    def test_realized_vol_matches_manual_std(self):
        rng = np.random.default_rng(7)
        closes = 100 * np.cumprod(1 + rng.normal(0, 0.001, 80))
        frame = build_features(candles_frame(list(closes)), FeatureConfig(realized_vol_window=10))
        manual = pd.Series(np.log(closes)).diff().rolling(10).std(ddof=1)
        assert frame["realized_vol_10"].iloc[-1] == pytest.approx(manual.iloc[-1])

    def test_invalid_config_rejected(self):
        with pytest.raises(ValueError):
            FeatureConfig(realized_vol_window=1)
        with pytest.raises(ValueError):
            FeatureConfig(momentum_lookbacks=(0,))

    def test_missing_column_rejected(self):
        with pytest.raises(ValueError, match="open"):
            build_features(pd.DataFrame({"timestamp": [1], "volume": [1]}))
