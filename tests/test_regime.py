"""Tests for the rule-based Regime Detector (SPEC §3–4).

Synthetic series are engineered so each regime has a unique signature;
thresholds in the detector are calibrated against these constructions.
"""

import numpy as np
import pandas as pd
import pytest

from marketlab.core.regime import RegimeType, RuleBasedRegimeDetector


def make_ohlcv(close_values, volume=None):
    close = pd.Series(np.asarray(close_values, dtype=float))
    if volume is None:
        volume = np.full(len(close), 1000.0)
    return pd.DataFrame(
        {
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close * 1.0005,
            "low": close * 0.9995,
            "close": close,
            "volume": np.asarray(volume, dtype=float),
        }
    )


@pytest.fixture(scope="module")
def detector():
    return RuleBasedRegimeDetector()


def test_steady_uptrend_detected_as_trend_up(detector):
    close = 100.0 * (1.002 ** np.arange(300))
    result = detector.detect(make_ohlcv(close))
    assert result.regime is RegimeType.TREND_UP
    assert result.confidence >= 0.5


def test_sine_wave_detected_as_range(detector):
    close = 100.0 + 0.5 * np.sin(np.arange(300) / 6.0)
    result = detector.detect(make_ohlcv(close))
    assert result.regime is RegimeType.RANGE


def test_volatility_expansion_detected_as_high_volatility(detector):
    rng = np.random.default_rng(11)
    calm = rng.normal(0, 0.0005, 270)
    wild = rng.normal(0, 0.004, 30)
    close = 100.0 * np.cumprod(1 + np.concatenate([calm, wild]))
    result = detector.detect(make_ohlcv(close))
    assert result.regime is RegimeType.HIGH_VOLATILITY


def test_volatility_compression_detected_as_low_volatility(detector):
    rng = np.random.default_rng(12)
    wild = rng.normal(0, 0.004, 270)
    calm = rng.normal(0, 0.0002, 30)
    close = 100.0 * np.cumprod(1 + np.concatenate([wild, calm]))
    result = detector.detect(make_ohlcv(close))
    assert result.regime is RegimeType.LOW_VOLATILITY


def test_upward_gap_detected_as_breakout(detector):
    rng = np.random.default_rng(13)
    base = 100.0 + rng.normal(0, 0.05, 300)
    base[-1] = 105.0  # single fresh gap far above the prior range
    result = detector.detect(make_ohlcv(base))
    assert result.regime is RegimeType.BREAKOUT
    assert result.confidence > 0.5


def test_event_score_with_fast_move_triggers_event_shock(detector):
    rng = np.random.default_rng(14)
    base = 100.0 + rng.normal(0, 0.05, 300)
    base[-1] = 95.5  # fast -4.5% move
    volume = np.full(300, 1000.0)
    volume[-1] = 6000.0  # 6x median volume
    shocked = detector.detect(make_ohlcv(base, volume), event_score=0.9)
    assert shocked.regime is RegimeType.EVENT_SHOCK

    # Same market data without a news score must NOT be EVENT_SHOCK.
    plain = detector.detect(make_ohlcv(base, volume), event_score=0.0)
    assert plain.regime is not RegimeType.EVENT_SHOCK


def test_missing_column_raises(detector):
    frame = make_ohlcv(np.full(100, 100.0)).drop(columns=["volume"])
    with pytest.raises(ValueError, match="volume"):
        detector.detect(frame)


def test_too_short_history_raises(detector):
    with pytest.raises(ValueError, match="rows"):
        detector.detect(make_ohlcv(np.full(10, 100.0)))
