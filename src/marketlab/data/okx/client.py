"""OKX v5 public market-data client (Phase 1 foundation).

Only public, unauthenticated endpoints are used here — no trading. The client
is transport-injectable so tests run against canned responses without network.
"""

from __future__ import annotations

from typing import Any

import httpx
import pandas as pd

DEFAULT_BASE_URL = "https://www.okx.com"
DEFAULT_BAR = "1m"
_DEFAULT_TIMEOUT = 10.0

_CANDLE_COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "volume_currency",
    "volume_quote",
    "confirmed",
]


class OKXError(RuntimeError):
    """Raised when OKX returns a non-success business code."""


class OKXPublicClient:
    """Thin wrapper over OKX REST v5 public endpoints.

    ``transport`` accepts any ``httpx.BaseTransport`` (e.g. MockTransport)
    for offline testing.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = _DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    # -- public API ---------------------------------------------------------

    def get_ticker(self, inst_id: str = "BTC-USDT") -> dict[str, Any]:
        """Latest ticker snapshot for a spot instrument."""
        payload = self._get("/api/v5/market/ticker", {"instId": inst_id})
        row = payload["data"][0]
        return {
            "inst_id": row["instId"],
            "last": float(row["last"]),
            "ask": _opt_float(row.get("askPx")),
            "bid": _opt_float(row.get("bidPx")),
            "open_24h": _opt_float(row.get("open24h")),
            "vol_24h": _opt_float(row.get("vol24h")),
            "timestamp": _ms_to_timestamp(row["ts"]),
        }

    def get_candles(
        self,
        inst_id: str = "BTC-USDT",
        bar: str = DEFAULT_BAR,
        limit: int = 300,
    ) -> pd.DataFrame:
        """Most recent OHLCV candles (max 300) as an ascending-time DataFrame."""
        payload = self._get(
            "/api/v5/market/candles",
            {"instId": inst_id, "bar": bar, "limit": limit},
        )
        return _parse_candles(payload["data"])

    def get_history_candles(
        self,
        inst_id: str = "BTC-USDT",
        bar: str = DEFAULT_BAR,
        after: int | None = None,
        before: int | None = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        """Older OHLCV candles for pagination (max 100 per request).

        ``after``/``before`` are epoch milliseconds. With ``after`` set, OKX
        returns records **older** than that timestamp — the cursor used by
        ``marketlab.data.okx.history.HistoryDownloader``.
        """
        params: dict[str, Any] = {"instId": inst_id, "bar": bar, "limit": limit}
        if after is not None:
            params["after"] = str(int(after))
        if before is not None:
            params["before"] = str(int(before))
        payload = self._get("/api/v5/market/history-candles", params)
        return _parse_candles(payload["data"])

    def get_trades(
        self,
        inst_id: str = "BTC-USDT",
        limit: int = 100,
    ) -> pd.DataFrame:
        """Recent public trades ascending in time."""
        payload = self._get("/api/v5/market/trades", {"instId": inst_id, "limit": limit})
        rows = payload["data"]
        frame = pd.DataFrame(rows)
        frame = frame.rename(
            columns={"tradeId": "trade_id", "px": "price", "sz": "size", "ts": "ts_ms"}
        )
        frame["price"] = frame["price"].astype(float)
        frame["size"] = frame["size"].astype(float)
        frame["timestamp"] = frame.pop("ts_ms").map(_ms_to_timestamp)
        return frame.sort_values("timestamp", ignore_index=True)[
            ["trade_id", "price", "size", "side", "timestamp"]
        ]

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> OKXPublicClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- internals ----------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self._http.get(path, params=params)
        response.raise_for_status()
        body = response.json()
        if body.get("code") != "0":
            raise OKXError(f"OKX error {body.get('code')}: {body.get('msg')}")
        if not body.get("data"):
            raise OKXError(f"OKX returned empty data for {path}")
        return body


def _parse_candles(rows: list[list[str]]) -> pd.DataFrame:
    """Parse OKX candle rows (newest-first) into an ascending-time frame."""
    frame = pd.DataFrame(rows, columns=_CANDLE_COLUMNS)
    frame["timestamp"] = frame["timestamp"].map(_ms_to_timestamp)
    numeric = ["open", "high", "low", "close", "volume"]
    frame[numeric] = frame[numeric].astype(float)
    frame["confirmed"] = frame["confirmed"].astype(int)
    return frame.sort_values("timestamp", ignore_index=True)


def _ms_to_timestamp(ms: str | int) -> pd.Timestamp:
    return pd.Timestamp(int(ms), unit="ms", tz="UTC")


def _opt_float(value: Any) -> float | None:
    return None if value in (None, "") else float(value)
