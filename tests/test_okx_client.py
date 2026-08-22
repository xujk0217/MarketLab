"""Tests for the OKX v5 public REST client (offline via MockTransport)."""

import httpx
import pandas as pd
import pytest

from marketlab.data.okx import OKXPublicClient
from marketlab.data.okx.client import OKXError


def _mock_client(handler):
    return OKXPublicClient(transport=httpx.MockTransport(handler))


class TestTicker:
    def test_ticker_parsed_into_typed_fields(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v5/market/ticker"
            assert request.url.params["instId"] == "BTC-USDT"
            return httpx.Response(
                200,
                json={
                    "code": "0",
                    "msg": "",
                    "data": [
                        {
                            "instId": "BTC-USDT",
                            "last": "67000.5",
                            "askPx": "67000.6",
                            "bidPx": "67000.4",
                            "open24h": "65000",
                            "vol24h": "12345.6",
                            "ts": "1700000000000",
                        }
                    ],
                },
            )

        ticker = _mock_client(handler).get_ticker("BTC-USDT")
        assert ticker["last"] == pytest.approx(67000.5)
        assert ticker["ask"] == pytest.approx(67000.6)
        assert ticker["bid"] == pytest.approx(67000.4)
        assert ticker["vol_24h"] == pytest.approx(12345.6)
        assert ticker["timestamp"] == pd.Timestamp("2023-11-14T22:13:20Z")

    def test_business_error_raises_okx_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"code": "50011", "msg": "Rate Limit Reached", "data": []}
            )

        with pytest.raises(OKXError, match="50011"):
            _mock_client(handler).get_ticker()


CANDLES = {
    "code": "0",
    "msg": "",
    "data": [
        ["1700000002000", "67100", "67200", "67050", "67150", "10", "671500", "671500", "1"],
        ["1700000001000", "67000", "67100", "66950", "67100", "12", "805200", "805200", "1"],
        ["1700000000000", "66900", "67000", "66850", "67000", "8", "536000", "536000", "1"],
    ],
}


class TestCandles:
    def test_candles_sorted_ascending_with_numeric_types(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v5/market/candles"
            return httpx.Response(200, json=CANDLES)

        candles = _mock_client(handler).get_candles(limit=3)
        assert list(candles["close"]) == [67000.0, 67100.0, 67150.0]
        assert candles["open"].dtype == float
        assert list(candles["confirmed"]) == [1, 1, 1]
        assert candles["timestamp"].iloc[0] < candles["timestamp"].iloc[-1]


class TestTrades:
    def test_trades_parsed_and_sorted_ascending(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v5/market/trades"
            return httpx.Response(
                200,
                json={
                    "code": "0",
                    "msg": "",
                    "data": [
                        {"tradeId": "2", "px": "67001", "sz": "0.2", "side": "sell", "ts": "1700000001000"},
                        {"tradeId": "1", "px": "67000", "sz": "0.1", "side": "buy", "ts": "1700000000000"},
                    ],
                },
            )

        trades = _mock_client(handler).get_trades(limit=2)
        assert list(trades["price"]) == [67000.0, 67001.0]
        assert trades["size"].dtype == float
        assert set(trades.columns) == {"trade_id", "price", "size", "side", "timestamp"}


class TestHTTPFailures:
    def test_http_error_propagates(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        with pytest.raises(httpx.HTTPStatusError):
            _mock_client(handler).get_ticker()

    def test_empty_data_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"code": "0", "msg": "", "data": []})

        with pytest.raises(OKXError, match="empty"):
            _mock_client(handler).get_ticker()
