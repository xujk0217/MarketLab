"""Buy & Hold — the baseline every strategy must beat (SPEC §27)."""

from __future__ import annotations

import pandas as pd

from marketlab.strategies.base import Strategy


class BuyAndHold(Strategy):
    name = "buy_and_hold"

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=ohlcv.index, name=self.name)
