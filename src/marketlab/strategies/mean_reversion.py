"""Mean reversion strategy for RANGE regimes (SPEC §5 Range→Mean Reversion)."""

from __future__ import annotations

import pandas as pd

from marketlab.strategies.base import Strategy, _require_columns


class MeanReversion(Strategy):
    """Fade extreme z-score deviations from the rolling mean.

    z < -entry_z → long (oversold), z > +entry_z → short (overbought),
    otherwise flat.
    """

    name = "mean_reversion"

    def __init__(self, window: int = 20, entry_z: float = 2.0) -> None:
        if window <= 1 or entry_z <= 0:
            raise ValueError("window must be > 1 and entry_z positive")
        self.window = window
        self.entry_z = entry_z

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        _require_columns(ohlcv)
        close = ohlcv["close"].astype(float)
        rolling_mean = close.rolling(self.window).mean()
        rolling_std = close.rolling(self.window).std(ddof=1)

        valid = rolling_std.notna() & (rolling_std > 0)
        signals = pd.Series(0.0, index=ohlcv.index)
        if valid.any():
            z = (close - rolling_mean) / rolling_std
            # Comparisons against +/-inf behave correctly; NaN rows masked above.
            signals[valid & (z <= -self.entry_z)] = 1.0
            signals[valid & (z >= self.entry_z)] = -1.0
        return signals.rename(self.name)
