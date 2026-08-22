"""Historical candle downloader with cursor pagination (SPEC Phase 2 Raw layer).

OKX ``history-candles`` returns at most 100 rows per request; with ``after``
set it yields records strictly older than the cursor. The downloader walks
backwards page by page until the requested window is covered.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import pandas as pd

from marketlab.data.okx.client import DEFAULT_BAR


class CandleSource(Protocol):
    """Minimal interface the downloader needs (real client or test fake)."""

    def get_history_candles(
        self,
        inst_id: str = ...,
        bar: str = ...,
        after: int | None = ...,
        before: int | None = ...,
        limit: int = ...,
    ) -> pd.DataFrame: ...


@dataclass(frozen=True)
class HistoryDownloader:
    client: CandleSource
    inst_id: str = "BTC-USDT"
    bar: str = DEFAULT_BAR
    page_limit: int = 100  # OKX hard cap for history-candles
    pause_seconds: float = 0.15  # stay well under the 20 req / 2 s limit

    def download(
        self,
        days: float,
        end: datetime | None = None,
        on_page=None,
    ) -> pd.DataFrame:
        """Fetch ``days`` of candles ending at ``end`` (default: now), ascending.

        ``on_page(frame)`` is called after every page for progress reporting.
        """
        if days <= 0:
            raise ValueError("days must be positive")
        end_ts = _to_utc(end or datetime.now(UTC))
        start_ms = _ms(end_ts - timedelta(days=days))
        start_floor = pd.Timestamp(end_ts).floor("min") - pd.Timedelta(days=days)

        cursor_ms = _ms(end_ts)
        pages: list[pd.DataFrame] = []
        while True:
            page = self.client.get_history_candles(
                inst_id=self.inst_id,
                bar=self.bar,
                after=cursor_ms,
                limit=self.page_limit,
            )
            if page.empty:
                break
            pages.append(page)
            if on_page is not None:
                on_page(len(pages), len(page))
            oldest_ms = int(page["timestamp"].min().timestamp() * 1000)
            if oldest_ms >= cursor_ms:  # server not moving backwards: bail out
                raise RuntimeError(f"pagination stalled at cursor {cursor_ms}")
            cursor_ms = oldest_ms
            if oldest_ms <= start_ms or len(page) < self.page_limit:
                break
            time.sleep(self.pause_seconds)

        combined = (
            pd.concat(pages, ignore_index=True)
            .drop_duplicates(subset="timestamp", keep="first")
            .sort_values("timestamp", ignore_index=True)
        )
        return combined[
            (combined["timestamp"] >= start_floor) & (combined["timestamp"] <= end_ts)
        ].reset_index(drop=True)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("end timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _ms(ts: datetime) -> int:
    return int(ts.timestamp() * 1000)
