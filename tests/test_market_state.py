"""Tests for the MarketState digital-twin state vector (SPEC §18)."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pandas as pd
import pytest

from marketlab.core.market_state import MarketState
from marketlab.core.regime import RegimeType


class TestMarketState:
    def test_minimal_state_defaults_optional_fields_to_none(self):
        state = MarketState(symbol="BTC-USDT", timestamp=datetime.now(UTC), price=67000.0)
        assert state.volume is None
        assert state.regime is None
        assert state.event_score is None
        assert state.order_book_imbalance is None

    def test_full_state_fields_accepted(self):
        state = MarketState(
            symbol="BTC-USDT",
            timestamp=pd.Timestamp("2026-08-22T10:00:00Z"),
            price=78000.0,
            volume=1234.5,
            return_24h=0.053,
            volatility=0.02,
            event_score=0.78,
            regime=RegimeType.BREAKOUT,
        )
        assert state.regime is RegimeType.BREAKOUT
        assert state.return_24h == pytest.approx(0.053)

    def test_non_positive_price_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            MarketState(symbol="BTC-USDT", timestamp=datetime.now(UTC), price=0.0)

    def test_state_is_immutable(self):
        state = MarketState(symbol="BTC-USDT", timestamp=datetime.now(UTC), price=1.0)
        with pytest.raises(FrozenInstanceError):
            state.price = 2.0
