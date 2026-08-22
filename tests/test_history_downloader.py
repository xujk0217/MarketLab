"""Tests for HistoryDownloader pagination (offline, scripted client)."""

from datetime import UTC, datetime

import pandas as pd
import pytest

from marketlab.data.okx.history import HistoryDownloader

END = datetime(2026, 8, 22, 0, 0, tzinfo=UTC)


def make_frame(minutes_desc):
    """Rows newest-first like the OKX API (minutes offset from Jan 1)."""
    stamps = pd.Timestamp("2026-01-01", tz="UTC") + pd.to_timedelta(minutes_desc, unit="m")
    return pd.DataFrame(
        {
            "timestamp": stamps,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1.0,
            "confirmed": 1,
        }
    )


class FakeClient:
    def __init__(self, pages):
        self.pages = list(pages)
        self.cursors = []

    def get_history_candles(self, inst_id="BTC-USDT", bar="1m", after=None, before=None, limit=100):
        assert limit == 100
        self.cursors.append(after)
        return self.pages.pop(0) if self.pages else pd.DataFrame(columns=["timestamp"])


def full_day_pages(limit=100):
    """Every minute of Aug 21, newest first, chunked into full pages."""
    minutes = pd.Series(pd.date_range("2026-08-21 00:00", "2026-08-21 23:59", freq="min", tz="UTC"))
    desc = minutes.sort_values(ascending=False, ignore_index=True)
    return [
        desc.iloc[i : i + limit].to_frame(name="timestamp").assign(
            open=100.0, high=101.0, low=99.0, close=100.5, volume=1.0, confirmed=1
        )
        for i in range(0, len(desc), limit)
    ]


def test_paginates_backwards_and_reassembles_ascending():
    pages = full_day_pages()
    client = FakeClient(pages)
    downloader = HistoryDownloader(client=client)

    result = downloader.download(days=1.0, end=END)

    assert len(result) == 1440
    assert result["timestamp"].is_monotonic_increasing
    # Cursors walk strictly backwards from the end timestamp.
    assert client.cursors[0] == int(END.timestamp() * 1000)
    assert all(b < a for a, b in zip(client.cursors, client.cursors[1:], strict=False))


def test_short_page_stops_pagination():
    minutes = pd.Series(pd.date_range("2026-08-21 00:00", "2026-08-21 23:59", freq="min", tz="UTC"))
    desc = minutes.sort_values(ascending=False, ignore_index=True)
    pages = [
        desc.iloc[i : i + 100].to_frame(name="timestamp").assign(
            open=100.0, high=101.0, low=99.0, close=100.5, volume=1.0, confirmed=1
        )
        for i in (0, 100)  # two full pages...
    ]
    pages.append(desc.iloc[200:237].to_frame(name="timestamp").assign(  # ...then a short one
        open=100.0, high=101.0, low=99.0, close=100.5, volume=1.0, confirmed=1
    ))
    client = FakeClient(pages)
    downloader = HistoryDownloader(client=client)

    result = downloader.download(days=7.0, end=END)

    assert len(client.cursors) == 3  # stopped right after the short page
    assert len(result) == 237


def test_result_clipped_to_requested_window():
    pages = full_day_pages()
    # Last page also carries 10 rows from BEFORE the requested window start.
    below_start = pd.Series(
        pd.date_range("2026-08-20 23:50", "2026-08-20 23:59", freq="min", tz="UTC")
    ).sort_values(ascending=False, ignore_index=True)
    extra = below_start.to_frame(name="timestamp").assign(
        open=100.0, high=101.0, low=99.0, close=100.5, volume=1.0, confirmed=1
    )
    pages[-1] = (
        pd.concat([pages[-1], extra], ignore_index=True)
        .sort_values("timestamp", ascending=False, ignore_index=True)
    )
    client = FakeClient(pages)
    downloader = HistoryDownloader(client=client)

    result = downloader.download(days=1.0, end=END)

    assert result["timestamp"].min() >= pd.Timestamp("2026-08-21", tz="UTC")
    assert result["timestamp"].max() <= END
    assert len(result) == 1440


def test_stalled_cursor_raises():
    # A page whose oldest row is NOT older than the cursor cannot advance it.
    stuck = make_frame([0] * 5)
    stuck["timestamp"] = END  # identical to the initial cursor
    client = FakeClient([stuck])
    downloader = HistoryDownloader(client=client)
    with pytest.raises(RuntimeError, match="stalled"):
        downloader.download(days=1.0, end=END)


def test_invalid_days_rejected():
    with pytest.raises(ValueError, match="days"):
        HistoryDownloader(client=FakeClient([])).download(days=0)
