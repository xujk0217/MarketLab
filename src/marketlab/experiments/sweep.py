"""Parameter grid sweeps (Phase 3-4 research tooling).

One sweep = the cartesian product of parameter axes, each combination run as
its own experiment record under a shared group so ``experiments --group`` can
compare them. Parameter keys are validated against the strategy constructor
BEFORE any run, so a typo fails fast instead of 11 runs in.
"""

from __future__ import annotations

import inspect
import itertools
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pandas as pd

from marketlab.backtest.engine import BacktestConfig, BacktestResult
from marketlab.experiments import ExperimentLab, RunRecord, run_backtest_experiment
from marketlab.strategies.base import Strategy


def coerce_scalar(value: str) -> Any:
    """'20' -> int, '2.0' -> float, 'true' -> bool, else str."""
    if not isinstance(value, str):
        return value
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            continue
    lowered = value.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    return value


def expand_grid(spec: dict[str, list[Any]]) -> Iterator[dict[str, Any]]:
    """Cartesian product of axis values, e.g. {a:[1,2], b:['x']} -> 2 combos."""
    if not spec:
        yield {}
        return
    keys = sorted(spec)
    for values in itertools.product(*(spec[k] for k in keys)):
        yield dict(zip(keys, values, strict=True))


def validate_params(strategy_cls: type[Strategy], params: dict[str, Any]) -> None:
    """Reject unknown constructor parameters before any run happens."""
    signature = inspect.signature(strategy_cls.__init__)
    accepted = {name for name in signature.parameters if name != "self"}
    unknown = set(params) - accepted
    if unknown:
        raise ValueError(
            f"{strategy_cls.name} does not accept {sorted(unknown)}; "
            f"valid params: {sorted(accepted)}"
        )


@dataclass(frozen=True)
class SweepEntry:
    label: str
    params: dict[str, Any]
    record: RunRecord
    result: BacktestResult


def run_sweep(
    candles: pd.DataFrame,
    strategy_cls: type[Strategy],
    grid: dict[str, list[Any]],
    *,
    inst_id: str,
    bar: str,
    config: BacktestConfig | None = None,
    lab: ExperimentLab | None = None,
    group: str,
) -> list[SweepEntry]:
    """Run every grid combination and store one record per combination."""
    config = config or BacktestConfig()
    entries: list[SweepEntry] = []
    for params in expand_grid(grid):
        validate_params(strategy_cls, params)
        strategy = strategy_cls(**params)
        label = ",".join(f"{k}={params[k]}" for k in sorted(params)) or "default"
        record, result = run_backtest_experiment(
            candles,
            strategy,
            inst_id=inst_id,
            bar=bar,
            config=config,
            lab=lab,
            label=label,
            group=group,
        )
        entries.append(SweepEntry(label=label, params=params, record=record, result=result))
    return entries


def sweep_table(entries: list[SweepEntry], sort_by: str = "sharpe") -> pd.DataFrame:
    """Comparison table over one sweep's results."""
    rows = [
        {
            "label": entry.label,
            "total_return": entry.result.metrics["total_return"],
            "sharpe": entry.result.metrics["sharpe"],
            "max_drawdown": entry.result.metrics["max_drawdown"],
            "trades": entry.result.metrics["trades"],
            "total_cost": entry.result.metrics["total_cost"],
            "run_id": entry.record.run_id,
        }
        for entry in entries
    ]
    frame = pd.DataFrame(rows)
    if frame.empty or sort_by not in frame.columns:
        return frame
    return frame.sort_values(sort_by, ascending=False, ignore_index=True)
