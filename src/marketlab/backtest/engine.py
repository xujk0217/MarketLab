"""Vectorized position-based backtest engine (SPEC Phase 4).

Fee / slippage / PnL / drawdown / Sharpe on bar-level target positions,
with next-bar execution to structurally prevent lookahead bias.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

_COST_BPS_TO_RATE = 10_000.0


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 10_000.0
    fee_rate: float = 0.001  # 0.1% per side (OKX spot taker reference)
    slippage_bps: float = 5.0  # basis points per side
    bars_per_year: float = 365.0 * 24 * 60  # default: 1-minute crypto bars


@dataclass
class BacktestResult:
    """Equity curve plus standard research metrics."""

    equity: pd.Series
    positions: pd.Series
    metrics: dict[str, float] = field(default_factory=dict)


def run_backtest(
    prices: pd.Series,
    signals: pd.Series,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Simulate ``signals`` over ``prices``.

    Execution model: the signal decided at bar close ``t`` is traded at bar
    ``t+1``'s close-to-close return — i.e. positions are shifted forward one
    bar before applying returns. Turnover costs (fee + slippage) are charged
    on every position change.
    """
    config = config or BacktestConfig()
    if prices.empty or len(prices) != len(signals):
        raise ValueError("prices/signals must be non-empty and of equal length")
    if not prices.index.equals(signals.index):
        raise ValueError("prices and signals must share the same index")
    if (prices <= 0).any():
        raise ValueError("prices must be strictly positive")

    positions = signals.astype(float).shift(1).fillna(0.0)
    asset_returns = prices.pct_change().fillna(0.0)

    turnover = positions.diff().abs()
    turnover.iloc[0] = abs(float(positions.iloc[0]))
    cost_rate = config.fee_rate + config.slippage_bps / _COST_BPS_TO_RATE

    strategy_returns = positions * asset_returns - turnover * cost_rate
    equity = config.initial_capital * (1.0 + strategy_returns).cumprod()
    equity.name = "equity"

    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0

    n_bars = len(equity)
    total_return = float(equity.iloc[-1] / config.initial_capital - 1.0)
    growth_factor = max(float(equity.iloc[-1]) / config.initial_capital, 1e-12)
    annualized_log_return = math.log(growth_factor) * (config.bars_per_year / n_bars)
    if annualized_log_return > 709.0:  # exp overflow guard for absurd runs
        annualized_return = math.inf
    else:
        annualized_return = math.expm1(annualized_log_return)

    ret_std = float(strategy_returns.std(ddof=1)) if n_bars > 1 else 0.0
    if ret_std > 0:
        sharpe = (
            float(strategy_returns.mean()) / ret_std * math.sqrt(config.bars_per_year)
        )
    else:
        sharpe = 0.0

    metrics = {
        "total_return": total_return,
        "annualized_return": float(annualized_return),
        "sharpe": float(sharpe),
        "max_drawdown": float(drawdown.min()),
        "trades": int((turnover > 0).sum()),
        "exposure": float((positions != 0.0).mean()),
        "total_cost": float((turnover * cost_rate).sum()),
    }
    return BacktestResult(equity=equity, positions=positions, metrics=metrics)
