"""Strategy implementations. Every strategy shares the MarketState contract."""

from marketlab.strategies.base import Strategy
from marketlab.strategies.buy_and_hold import BuyAndHold
from marketlab.strategies.mean_reversion import MeanReversion
from marketlab.strategies.momentum import Momentum
from marketlab.strategies.sma_cross import SmaCross

__all__ = ["Strategy", "BuyAndHold", "SmaCross", "Momentum", "MeanReversion"]
