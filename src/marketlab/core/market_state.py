"""Unified market state — the Market Digital Twin state vector (SPEC §18).

Every layer of MarketLab (feeds, regime detector, strategies, backtest,
replay, live) reads and produces this same structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from marketlab.core.regime import RegimeType


@dataclass(frozen=True)
class MarketState:
    """A single point-in-time snapshot of everything MarketLab knows.

    Required fields form the minimal price-only twin; optional fields are
    filled in progressively by later phases (order book, funding, macro...).
    """

    symbol: str
    timestamp: pd.Timestamp | datetime
    price: float
    # price-derived
    volume: float | None = None
    return_1m: float | None = None
    return_5m: float | None = None
    return_1h: float | None = None
    return_24h: float | None = None
    volatility: float | None = None
    # microstructure (Phase 21+)
    spread: float | None = None
    order_book_imbalance: float | None = None
    trade_flow: float | None = None
    # derivatives / cross-asset (Phase 19+)
    funding_rate: float | None = None
    open_interest: float | None = None
    # event layer (Phase 8+)
    event_score: float | None = None
    # regime layer (Phase 6+)
    regime: RegimeType | None = None

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError(f"price must be positive, got {self.price}")
