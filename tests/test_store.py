"""Tests for the three-layer store: Raw parquet batches + Normalized layer."""

from pathlib import Path

import pandas as pd
import pytest

from marketlab.data.store import (
    load_normalized,
    load_raw,
    normalize,
    save_normalized,
    save_raw_batch,
)


def candle_rows(stamps, close=100.0):
    n = len(stamps)
    return pd.DataFrame(
        {
            "timestamp": stamps,
            "open": [close] * n,
            "high": [close + 1] * n,
            "low": [close - 1] * n,
            "close": [close] * n,
            "volume": [1.0] * n,
            "confirmed": [1] * n,
        }
    )


def minutes(start, periods, freq="min"):
    return pd.date_range(start, periods=periods, freq=freq, tz="UTC")


class TestRawLayer:
    def test_batch_filename_covers_range_and_is_immutable(self, tmp_path: Path):
        frame = candle_rows(minutes("2026-08-21 10:00", 120))
        path = save_raw_batch(frame, "BTC-USDT", "1m", root=tmp_path)
        assert path.name.startswith("20260821T100000Z_20260821T115900Z")
        with pytest.raises(FileExistsError):
            save_raw_batch(frame, "BTC-USDT", "1m", root=tmp_path)

    def test_load_merges_batches_sorted(self, tmp_path: Path):
        later = candle_rows(minutes("2026-08-21 12:00", 10))
        earlier = candle_rows(minutes("2026-08-21 11:00", 10))
        save_raw_batch(later, "BTC-USDT", "1m", root=tmp_path)  # saved out of order
        save_raw_batch(earlier, "BTC-USDT", "1m", root=tmp_path)
        merged = load_raw("BTC-USDT", "1m", root=tmp_path)
        assert len(merged) == 20
        assert merged["timestamp"].is_monotonic_increasing

    def test_empty_batch_rejected(self, tmp_path: Path):
        with pytest.raises(ValueError, match="empty"):
            save_raw_batch(candle_rows([], close=1)[:0], "BTC-USDT", "1m", root=tmp_path)

    def test_missing_batches_raise_helpful_error(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="download"):
            load_raw("BTC-USDT", "1m", root=tmp_path)


class TestNormalize:
    def test_dedup_violations_and_gap_detection(self):
        stamps = minutes("2026-08-21 10:00", 10)  # bars 0..9
        raw = candle_rows(stamps)
        part_a = raw.iloc[:6].copy()
        part_a.loc[5, ["high", "low"]] = [90.0, 95.0]  # violate bar 5 IN PLACE (unique ts)
        bar4_dup = raw.iloc[[4]]  # exact duplicate of bar 4
        dirty = pd.concat([part_a, bar4_dup, raw.iloc[7:]], ignore_index=True)  # bar 6 missing

        clean, report = normalize(dirty, "1m")

        assert report.duplicates_removed == 1  # only bar4_dup
        assert report.ohlc_violations == 1  # bar 5 survives dedup with high < low
        assert report.missing_bars == 1  # bar 6 absent
        gap_start, gap_end = report.missing_ranges[0]
        assert gap_end - gap_start == pd.Timedelta(minutes=2)
        assert len(clean) == 9
        assert clean["timestamp"].is_monotonic_increasing

    def test_unknown_bar_rejected(self):
        with pytest.raises(ValueError, match="unknown bar"):
            normalize(candle_rows(minutes("2026-08-21", 3)), "7x")

    def test_missing_columns_rejected(self):
        with pytest.raises(ValueError, match="columns"):
            normalize(candle_rows(minutes("2026-08-21", 3)).drop(columns=["volume"]), "1m")

    def test_normalized_roundtrip(self, tmp_path: Path):
        clean, _ = normalize(candle_rows(minutes("2026-08-21", 5)), "1m")
        path = save_normalized(clean, "BTC-USDT", "1m", root=tmp_path)
        assert path.exists()
        loaded = load_normalized("BTC-USDT", "1m", root=tmp_path)
        pd.testing.assert_frame_equal(clean, loaded)

    def test_load_normalized_missing_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="normalize"):
            load_normalized("BTC-USDT", "1m", root=tmp_path)
