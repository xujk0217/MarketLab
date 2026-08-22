"""Time-series momentum strategy for TREND regimes (SPEC §5 Trend→Momentum)."""

from __future__ import annotations

import pandas as pd

from marketlab.strategies.base import Strategy, _require_columns


class Momentum(Strategy):
    """Sign of the N-bar return with a dead-band to avoid churn."""

    name = "momentum"

    def __init__(self, lookback: int = 20, deadband: float = 0.0) -> None:
        if lookback <= 0 or deadband < 0:
            raise ValueError("lookback must be positive and deadband non-negative")
        self.lookback = lookback
        self.deadband = deadband

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        _require_columns(ohlcv)
        close = ohlcv["close"].astype(float)
        momentum_return = close.pct_change(self.lookback)

        signals = pd.Series(0.0, index=ohlcv.index)
        valid = momentum_return.notna()
        signals[valid & (momentum_return > self.deadband)] = 1.0
        signals[valid & (momentum_return < -self.deadband)] = -1.0
        return signals.rename(self.name)
