"""Market Regime Engine — rule-based v1 (SPEC §3–4).

Classifies recent OHLCV history into one of seven regimes. Deterministic and
explainable by design; ML-based detectors (XGBoost/HMM/clustering) will be
compared against this baseline in Phase 15.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

import pandas as pd

_REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")


class RegimeType(StrEnum):
    """Regime labels (SPEC §4). EVENT_SHOCK requires an external news score."""

    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    BREAKOUT = "BREAKOUT"
    EVENT_SHOCK = "EVENT_SHOCK"


@dataclass(frozen=True)
class RegimeResult:
    """Detection output: label plus a confidence in [0, 1]."""

    regime: RegimeType
    confidence: float


@dataclass(frozen=True)
class RuleBasedRegimeDetector:
    """Cascade classifier: EVENT_SHOCK → BREAKOUT → TREND → VOLATILITY → RANGE.

    All thresholds are explicit constructor parameters so experiments can be
    recorded and compared (Phase 5 Experiment Lab).
    """

    trend_lookback: int = 60
    vol_short_window: int = 20
    breakout_lookback: int = 30
    breakout_vol_ratio: float = 1.3
    breakout_atr_margin: float = 0.25
    trend_stat_threshold: float = 2.0
    high_vol_ratio: float = 1.8
    low_vol_ratio: float = 0.55
    shock_event_score: float = 0.7
    shock_move: float = 0.02
    shock_volume_ratio: float = 2.0

    def detect(self, ohlcv: pd.DataFrame, event_score: float = 0.0) -> RegimeResult:
        """Classify the most recent bar of ``ohlcv``.

        ``event_score`` is the aggregated canonical-event impact in [0, 1]
        (Phase 8+); it stays 0 until the Event Intelligence Layer exists.
        """
        _validate(ohlcv)
        close = ohlcv["close"].astype(float)
        high = ohlcv["high"].astype(float)
        low = ohlcv["low"].astype(float)
        volume = ohlcv["volume"].astype(float)

        rets = pd.Series(close.values).pct_change()
        long_vol = float(rets.std(ddof=1))
        short_vol = float(rets.iloc[-self.vol_short_window :].std(ddof=1))
        vol_ratio = short_vol / long_vol if long_vol > 0 else 1.0

        window_ret = float(close.iloc[-1] / close.iloc[-self.trend_lookback - 1] - 1)
        dir_stat = (
            window_ret / (long_vol * math.sqrt(self.trend_lookback)) if long_vol > 0 else 0.0
        )

        atr = float((high - low).iloc[-self.breakout_lookback :].mean())
        prior_hi = float(high.iloc[-self.breakout_lookback - 1 : -2].max())
        prior_lo = float(low.iloc[-self.breakout_lookback - 1 : -2].min())
        last_close = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])
        fresh_up = prev_close <= prior_hi < last_close
        fresh_down = prev_close >= prior_lo > last_close

        volume_spike = float(volume.iloc[-1] / max(volume.median(), 1e-12))
        last_move = abs(float(close.iloc[-1] / close.iloc[-2] - 1))

        # 1) EVENT_SHOCK — news score high AND fast move AND volume spike (SPEC §4)
        if (
            event_score >= self.shock_event_score
            and last_move >= self.shock_move
            and volume_spike >= self.shock_volume_ratio
        ):
            return RegimeResult(RegimeType.EVENT_SHOCK, min(1.0, event_score))

        # 2) BREAKOUT — fresh breach of the prior range with volatility expansion
        if fresh_up or fresh_down:
            margin = self.breakout_atr_margin * max(atr, 1e-12)
            if vol_ratio >= self.breakout_vol_ratio and (
                (fresh_up and last_close - prior_hi >= margin)
                or (fresh_down and prior_lo - last_close >= margin)
            ):
                distance = (
                    (last_close - prior_hi) if fresh_up else (prior_lo - last_close)
                ) / max(atr, 1e-12)
                return RegimeResult(
                    RegimeType.BREAKOUT, min(1.0, 0.5 + 0.25 * distance)
                )

        # 3) TREND — statistically significant directional move over lookback
        if abs(dir_stat) >= self.trend_stat_threshold:
            regime = RegimeType.TREND_UP if dir_stat > 0 else RegimeType.TREND_DOWN
            return RegimeResult(regime, min(1.0, abs(dir_stat) / 4.0))

        # 4) VOLATILITY regimes relative to the full-sample baseline
        if vol_ratio >= self.high_vol_ratio:
            return RegimeResult(RegimeType.HIGH_VOLATILITY, min(1.0, vol_ratio - 1.0))
        if vol_ratio <= self.low_vol_ratio:
            return RegimeResult(RegimeType.LOW_VOLATILITY, min(1.0, 1.0 - vol_ratio))

        # 5) RANGE — nothing significant detected
        return RegimeResult(RegimeType.RANGE, min(1.0, 1.0 - abs(dir_stat) / 2.0))


def _validate(ohlcv: pd.DataFrame) -> None:
    missing = [c for c in _REQUIRED_COLUMNS if c not in ohlcv.columns]
    if missing:
        raise ValueError(f"ohlcv is missing columns: {missing}")
    min_len = max(RuleBasedRegimeDetector().trend_lookback, RuleBasedRegimeDetector().breakout_lookback) + 3
    if len(ohlcv) < min_len:
        raise ValueError(f"ohlcv needs at least {min_len} rows, got {len(ohlcv)}")
