"""Strategy Arena v2 — per-regime strategy comparison (SPEC §27, Phase 7).

Method (no lookahead anywhere):
1. Label the timeline in steps: at each step the rule-based detector classifies
   the TRAILING window, and that label is assigned to the NEXT block of bars.
2. Compute every strategy's per-bar returns once over the full history
   (signals decided at bar close, applied from the next bar — same execution
   model as the backtest engine).
3. Aggregate per-bar returns inside each regime segment into segment metrics.

The result answers: "which strategy works in which market?"
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from marketlab.backtest.engine import BacktestConfig
from marketlab.core.regime import RegimeType, RuleBasedRegimeDetector
from marketlab.strategies.base import Strategy


@dataclass(frozen=True)
class Segment:
    """A contiguous block of bars carrying one trailing-detected label."""

    start: int  # inclusive positional index
    end: int  # exclusive
    regime: RegimeType


def detector_min_rows(detector: RuleBasedRegimeDetector) -> int:
    """Minimum history the detector accepts."""
    return max(detector.trend_lookback, detector.breakout_lookback) + 3


def label_segments(
    candles: pd.DataFrame,
    detector: RuleBasedRegimeDetector | None = None,
    step: int | None = None,
) -> list[Segment]:
    """Assign regimes to successive blocks of ``step`` bars.

    Anti-lookahead guarantee: the label of block ``[start, end)`` is detected
    from the window STRICTLY BEFORE ``start`` — never from the block itself —
    so a segment's own price action cannot influence its label (SPEC §42).
    """
    detector = detector or RuleBasedRegimeDetector()
    step = step or detector.trend_lookback
    n = len(candles)
    min_rows = detector_min_rows(detector)
    if n <= min_rows:
        raise ValueError(f"need more than {min_rows} bars for arena labeling, got {n}")
    segments: list[Segment] = []
    start = min_rows
    while start < n:
        end = min(start + step, n)
        window = candles.iloc[start - min_rows : start]
        result = detector.detect(window)
        segments.append(Segment(start, end, result.regime))
        start = end
    return segments


def segment_metrics(returns: pd.Series, bars_per_year: float) -> dict[str, float]:
    """Metrics for one contiguous slice of per-bar strategy returns."""
    if len(returns) == 0:
        raise ValueError("empty return series")
    growth = float((1.0 + returns).prod())
    total_return = growth - 1.0
    std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    sharpe = (
        float(returns.mean()) / std * math.sqrt(bars_per_year) if std > 0 else 0.0
    )
    equity = (1.0 + returns).cumprod()
    max_drawdown = float((equity / equity.cummax() - 1.0).min())
    return {
        "total_return": total_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "n_bars": float(len(returns)),
    }


def _per_bar_returns(
    prices: pd.Series,
    signals: pd.Series,
    config: BacktestConfig,
) -> pd.Series:
    """Engine-equivalent per-bar strategy returns (next-bar execution + costs)."""
    positions = signals.astype(float).shift(1).fillna(0.0)
    asset_returns = prices.pct_change().fillna(0.0)
    turnover = positions.diff().abs()
    turnover.iloc[0] = abs(float(positions.iloc[0]))
    cost_rate = config.fee_rate + config.slippage_bps / 10_000.0
    return positions * asset_returns - turnover * cost_rate


REGIME_ORDER = [
    RegimeType.TREND_UP,
    RegimeType.TREND_DOWN,
    RegimeType.RANGE,
    RegimeType.LOW_VOLATILITY,
    RegimeType.HIGH_VOLATILITY,
    RegimeType.BREAKOUT,
    RegimeType.EVENT_SHOCK,
]


def arena(
    candles: pd.DataFrame,
    strategies: dict[str, Strategy],
    *,
    config: BacktestConfig | None = None,
    detector: RuleBasedRegimeDetector | None = None,
    step: int | None = None,
    metric: str = "total_return",
    min_segment_bars: int = 20,
) -> tuple[pd.DataFrame, list[Segment]]:
    """Build the strategy × regime matrix.

    Returns ``(matrix, segments)`` where ``matrix`` is indexed by strategy name
    with one column per observed regime, holding ``metric`` values aggregated
    over all segments sharing that regime.
    """
    config = config or BacktestConfig()
    if not strategies:
        raise ValueError("strategies dict must not be empty")
    segments = label_segments(candles, detector, step)

    rows = {}
    for name, strategy in strategies.items():
        returns = _per_bar_returns(candles["close"].astype(float),
                                   strategy.generate_signals(candles), config)
        cells: dict[RegimeType, list[pd.Series]] = {}
        for segment in segments:
            if segment.end - segment.start < min_segment_bars:
                continue
            cells.setdefault(segment.regime, []).append(
                returns.iloc[segment.start : segment.end]
            )
        rows[name] = {}
        for regime, slices in cells.items():
            # Concatenating the per-bar returns of all same-regime segments
            # equals the compounded result of trading ONLY during that regime
            # (flat in between) — the Strategy Router hypothesis of SPEC §5.
            pooled = pd.concat(slices)
            rows[name][regime.value] = segment_metrics(
                pooled, config.bars_per_year
            )[metric]

    matrix = pd.DataFrame.from_dict(rows, orient="index")
    ordered = [r.value for r in REGIME_ORDER if r.value in matrix.columns]
    matrix = matrix.reindex(columns=ordered)
    return matrix, segments
