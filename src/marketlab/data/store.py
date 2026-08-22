"""Three-layer market data store: Raw (immutable) → Normalized → cache.

Layout (all paths relative to the repo root, gitignored):

    data/raw/okx/{inst}/{bar}/{start}_{end}.parquet   immutable batches
    data/normalized/okx/{inst}/{bar}.parquet          derived, overwrite ok

Timestamps are tz-aware UTC everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

CANONICAL_COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "confirmed",
]

BAR_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1H": 3600,
    "2H": 7200,
    "4H": 14400,
    "1D": 86400,
}

RAW_ROOT = Path("data/raw")
NORMALIZED_ROOT = Path("data/normalized")
_MAX_REPORTED_RANGES = 50


def save_raw_batch(
    frame: pd.DataFrame,
    inst_id: str,
    bar: str,
    root: Path = RAW_ROOT,
) -> Path:
    """Persist one immutable batch file named by its covered UTC range.

    Refuses to overwrite an existing file — re-downloading an identical range
    is a no-op by design (Raw layer is append-only).
    """
    if frame.empty:
        raise ValueError("refusing to save empty raw batch")
    start = frame["timestamp"].min()
    end = frame["timestamp"].max()
    path = root / "okx" / inst_id / bar / (
        f"{start:%Y%m%dT%H%M%SZ}_{end:%Y%m%dT%H%M%SZ}.parquet"
    )
    if path.exists():
        raise FileExistsError(f"raw batch already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path


def load_raw(inst_id: str, bar: str, root: Path = RAW_ROOT) -> pd.DataFrame:
    """Load and concatenate every raw batch for (inst, bar), ascending."""
    directory = root / "okx" / inst_id / bar
    files = sorted(directory.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no raw batches under {directory} — run download first")
    frames = [pd.read_parquet(path) for path in files]
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values("timestamp", ignore_index=True)
    )


@dataclass(frozen=True)
class GapReport:
    """Data-quality summary produced while normalizing."""

    bar_seconds: int
    rows: int
    duplicates_removed: int
    ohlc_violations: int
    missing_bars: int
    missing_ranges: list[tuple[pd.Timestamp, pd.Timestamp]] = field(default_factory=list)

    def summarize(self) -> str:
        head = ", ".join(
            f"{a:%m-%d %H:%M}→{b:%m-%d %H:%M}" for a, b in self.missing_ranges[:5]
        )
        more = f" (+{len(self.missing_ranges) - 5} more)" if len(self.missing_ranges) > 5 else ""
        return (
            f"rows={self.rows} dup_removed={self.duplicates_removed} "
            f"ohlc_violations={self.ohlc_violations} "
            f"missing_bars={self.missing_bars} ranges=[{head}{more}]"
        )


def normalize(raw: pd.DataFrame, bar: str = "1m") -> tuple[pd.DataFrame, GapReport]:
    """Clean one instrument's candles into the canonical normalized schema."""
    if bar not in BAR_SECONDS:
        raise ValueError(f"unknown bar {bar!r}; expected one of {sorted(BAR_SECONDS)}")
    missing_cols = [c for c in CANONICAL_COLUMNS if c not in raw.columns]
    if missing_cols:
        raise ValueError(f"raw data is missing columns: {missing_cols}")

    frame = raw[CANONICAL_COLUMNS].copy()
    frame["confirmed"] = frame["confirmed"].astype(int)

    before_dedup = len(frame)
    frame = frame.drop_duplicates(subset="timestamp", keep="first").sort_values(
        "timestamp", ignore_index=True
    )
    duplicates_removed = before_dedup - len(frame)

    violations = int(
        (
            (frame["high"] < frame["low"])
            | (frame["high"] < frame["open"])
            | (frame["high"] < frame["close"])
            | (frame["low"] > frame["open"])
            | (frame["low"] > frame["close"])
        ).sum()
    )

    step = BAR_SECONDS[bar]
    deltas = frame["timestamp"].diff().dt.total_seconds().div(step)
    gap_mask = deltas > 1.0
    missing_ranges: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    missing_total = 0
    for idx in frame.index[gap_mask]:
        prev_end = frame["timestamp"].iloc[idx - 1]
        next_start = frame["timestamp"].iloc[idx]
        n_missing = int(deltas.iloc[idx]) - 1
        missing_total += n_missing
        if len(missing_ranges) < _MAX_REPORTED_RANGES:
            missing_ranges.append((prev_end, next_start))

    report = GapReport(
        bar_seconds=step,
        rows=len(frame),
        duplicates_removed=duplicates_removed,
        ohlc_violations=violations,
        missing_bars=missing_total,
        missing_ranges=missing_ranges,
    )
    return frame.reset_index(drop=True), report


def save_normalized(
    frame: pd.DataFrame,
    inst_id: str,
    bar: str,
    root: Path = NORMALIZED_ROOT,
) -> Path:
    """Overwrite-safe write of the derived normalized layer."""
    path = root / "okx" / inst_id / f"{bar}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path


def load_normalized(inst_id: str, bar: str, root: Path = NORMALIZED_ROOT) -> pd.DataFrame:
    path = root / "okx" / inst_id / f"{bar}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"no normalized data at {path} — run `normalize` first")
    return pd.read_parquet(path)
