"""Strategy interface (SPEC §5).

Contract:
* ``generate_signals`` receives OHLCV history up to and including the current
  closed bar — never future data;
* It returns target positions in {-1, 0, +1} decided AT each bar close;
* The backtest engine / live runner applies signals from the NEXT bar,
  which structurally prevents lookahead bias.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    """Base class for every MarketLab strategy (rule-based or AI)."""

    name: str = "strategy"

    @abstractmethod
    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        """Map OHLCV history to per-bar target positions in {-1, 0, +1}."""
        raise NotImplementedError


def _require_columns(ohlcv: pd.DataFrame) -> None:
    missing = [c for c in ("close",) if c not in ohlcv.columns]
    if missing:
        raise ValueError(f"ohlcv is missing columns: {missing}")
