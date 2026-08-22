"""Feature engineering on normalized candles (SPEC Phase 2 Feature layer).

Pure, vectorized pandas — no lookahead: every feature at row t only uses
data up to and including bar t (rolling windows are trailing by definition).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FeatureConfig:
    realized_vol_window: int = 60
    volume_window: int = 60
    momentum_lookbacks: tuple[int, ...] = (5, 15, 60)

    def __post_init__(self) -> None:
        if self.realized_vol_window < 2 or self.volume_window < 1:
            raise ValueError("windows must be positive (vol window >= 2)")
        if any(n <= 0 for n in self.momentum_lookbacks):
            raise ValueError("momentum lookbacks must be positive")


_DEFAULT_CONFIG = FeatureConfig()


def build_features(
    candles: pd.DataFrame, config: FeatureConfig = _DEFAULT_CONFIG
) -> pd.DataFrame:
    """Append research features to an OHLCV frame with a ``close``/``volume``."""
    for col in ("open", "high", "low", "close", "volume"):
        if col not in candles.columns:
            raise ValueError(f"candles missing column {col!r}")

    frame = candles.copy()
    close = frame["close"].astype(float)
    volume = frame["volume"].astype(float)
    log_close = np.log(close)
    log_return_1 = log_close.diff()

    frame["log_return_1"] = log_return_1
    frame[f"realized_vol_{config.realized_vol_window}"] = log_return_1.rolling(
        config.realized_vol_window
    ).std(ddof=1)
    vol_mean = volume.rolling(config.volume_window).mean()
    frame[f"volume_ratio_{config.volume_window}"] = volume / vol_mean.where(vol_mean > 0)
    frame["hl_range_pct"] = (frame["high"].astype(float) - frame["low"].astype(float)) / close

    for lookback in config.momentum_lookbacks:
        frame[f"return_lag{lookback}"] = close.pct_change(lookback)
    return frame
