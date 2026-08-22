"""Experiment Lab — reproducible run records and comparison (SPEC Phase 5).

Inspired by Qlib's experiment tracking, kept deliberately simple: every
backtest becomes one immutable JSON record under ``experiments/runs/`` with
everything needed to reproduce it (dataset fingerprint, strategy params,
cost config) plus the resulting metrics. Comparison is a DataFrame away.

This is the backbone of the A/B discipline (SPEC §32): an AI feature that
cannot show up as better metrics here gets deleted.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from marketlab import __version__
from marketlab.backtest.engine import BacktestConfig, BacktestResult, run_backtest
from marketlab.strategies.base import Strategy

EXPERIMENTS_ROOT = Path("experiments")
_RUNS_SUBDIR = "runs"


def fingerprint(frame: pd.DataFrame) -> str:
    """Stable content hash of a DataFrame (column-order sensitive)."""
    hashed = pd.util.hash_pandas_object(frame, index=True).values.tobytes()
    return hashlib.sha256(hashed).hexdigest()[:16]


@dataclass(frozen=True)
class DatasetInfo:
    """Identity of the exact data slice an experiment ran on."""

    inst_id: str
    bar: str
    start: str  # ISO timestamps
    end: str
    rows: int
    fingerprint: str


@dataclass(frozen=True)
class RunRecord:
    """One immutable experiment result."""

    run_id: str
    created_at: str
    label: str | None
    group: str | None
    dataset: DatasetInfo
    strategy_name: str
    strategy_params: dict
    config: dict
    metrics: dict[str, float]
    version: str = __version__
    git_sha: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, payload: dict) -> RunRecord:
        return cls(
            dataset=DatasetInfo(**payload["dataset"]),
            strategy_params=payload.get("strategy_params", {}),
            config=payload.get("config", {}),
            metrics=payload.get("metrics", {}),
            **{k: v for k, v in payload.items()
               if k not in ("dataset", "strategy_params", "config", "metrics")},
        )


def git_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip() or None
    except Exception:  # noqa: BLE001 - git may be unavailable outside a repo
        return None


class ExperimentLab:
    """Append-only store of run records."""

    def __init__(self, root: Path = EXPERIMENTS_ROOT) -> None:
        self.runs_dir = root / _RUNS_SUBDIR

    def save(self, record: RunRecord) -> Path:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        path = self.runs_dir / f"{record.created_at[:10]}_{record.run_id}.json"
        path.write_text(record.to_json(), encoding="utf-8")
        return path

    def load_all(self) -> list[RunRecord]:
        records = []
        for path in sorted(self.runs_dir.glob("*.json")):
            records.append(RunRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        return records

    def compare(
        self,
        group: str | None = None,
        sort_by: str = "sharpe",
        ascending: bool = False,
    ) -> pd.DataFrame:
        """All runs as a comparison table, newest first unless ``sort_by`` given."""
        rows = []
        for record in self.load_all():
            if group is not None and record.group != group:
                continue
            rows.append({
                "run_id": record.run_id,
                "created_at": record.created_at,
                "label": record.label or "",
                "group": record.group or "",
                "strategy": record.strategy_name,
                "params": json.dumps(record.strategy_params, ensure_ascii=False),
                "dataset": f"{record.dataset.inst_id}/{record.dataset.bar}",
                **{k: v for k, v in record.metrics.items()},
            })
        frame = pd.DataFrame(rows)
        if frame.empty or sort_by not in frame.columns:
            return frame
        return frame.sort_values(sort_by, ascending=ascending, ignore_index=True)


def describe_dataset(candles: pd.DataFrame, inst_id: str, bar: str) -> DatasetInfo:
    ohlcv = candles[["open", "high", "low", "close", "volume"]]
    return DatasetInfo(
        inst_id=inst_id,
        bar=bar,
        start=str(candles["timestamp"].iloc[0]),
        end=str(candles["timestamp"].iloc[-1]),
        rows=len(candles),
        fingerprint=fingerprint(ohlcv),
    )


def run_backtest_experiment(
    candles: pd.DataFrame,
    strategy: Strategy,
    *,
    inst_id: str,
    bar: str,
    config: BacktestConfig | None = None,
    lab: ExperimentLab | None = None,
    label: str | None = None,
    group: str | None = None,
    store: bool = True,
) -> tuple[RunRecord, BacktestResult]:
    """Execute one backtest and persist its full provenance."""
    config = config or BacktestConfig()
    prices = candles["close"].astype(float)
    signals = strategy.generate_signals(candles)
    result = run_backtest(prices, signals, config)

    record = RunRecord(
        run_id=uuid.uuid4().hex[:12],
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        label=label,
        group=group,
        dataset=describe_dataset(candles, inst_id, bar),
        strategy_name=strategy.name,
        strategy_params={
            k: v for k, v in vars(strategy).items() if isinstance(v, (int, float, str, bool))
        },
        config={
            "initial_capital": config.initial_capital,
            "fee_rate": config.fee_rate,
            "slippage_bps": config.slippage_bps,
            "bars_per_year": config.bars_per_year,
        },
        metrics=result.metrics,
        git_sha=git_sha(),
    )
    if store:
        (lab or ExperimentLab()).save(record)
    return record, result
