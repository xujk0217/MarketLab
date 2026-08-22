"""SMA cross trend strategy (SPEC Phase 3)."""

from __future__ import annotations

import pandas as pd

from marketlab.strategies.base import Strategy, _require_columns


class SmaCross(Strategy):
    """Long when the fast SMA is above the slow SMA, flat otherwise."""

    name = "sma_cross"

    def __init__(self, fast: int = 20, slow: int = 50) -> None:
        if fast <= 0 or slow <= fast:
            raise ValueError("require 0 < fast < slow")
        self.fast = fast
        self.slow = slow

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        _require_columns(ohlcv)
        close = ohlcv["close"].astype(float)
        sma_fast = close.rolling(self.fast).mean()
        sma_slow = close.rolling(self.slow).mean()
        signals = (sma_fast > sma_slow).astype(float)
        # Warm-up bars without a slow SMA are not tradable.
        signals[sma_slow.isna()] = 0.0
        return signals.rename(self.name)
