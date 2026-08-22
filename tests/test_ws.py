"""Tests for the OKX WebSocket client: parsing, payloads and reconnect loop."""

import asyncio
import json
import unittest

from marketlab.data.okx.ws import (
    BUSINESS_WS_URL,
    PUBLIC_WS_URL,
    OKXWebSocketClient,
    StreamConfig,
    channel_args,
    is_candle_channel,
    parse_message,
)


class TestParseMessage:
    def test_subscribe_ack(self):
        raw = json.dumps({"event": "subscribe", "arg": {"channel": "tickers"}})
        event = parse_message(raw)
        assert event["type"] == "subscribe"
        assert event["arg"]["channel"] == "tickers"

    def test_error_event(self):
        raw = json.dumps({"event": "error", "code": "60013", "msg": "bad args"})
        event = parse_message(raw)
        assert event["type"] == "error"
        assert event["code"] == "60013"

    def test_data_event_routes_channel(self):
        raw = json.dumps({"arg": {"channel": "trades"}, "data": [{"px": "67000"}]})
        event = parse_message(raw)
        assert event["type"] == "data"
        assert event["channel"] == "trades"
        assert event["data"][0]["px"] == "67000"

    def test_heartbeat_frames(self):
        assert parse_message("ping") == {"type": "ping"}
        assert parse_message(b"pong") == {"type": "pong"}

    def test_garbage_rejected(self):
        for bad in ("not json", "{}"):
            try:
                parse_message(bad)
            except ValueError:
                continue
            raise AssertionError(f"expected ValueError for {bad!r}")


class TestChannelArgs:
    def test_splits_public_and_business_endpoints(self):
        config = StreamConfig(
            channels=("tickers", "trades", "candles"), inst_id="ETH-USDT", bar="15m"
        )
        public, business = channel_args(config)
        assert public == [
            {"channel": "tickers", "instId": "ETH-USDT"},
            {"channel": "trades", "instId": "ETH-USDT"},
        ]
        assert business == [{"channel": "candle15m", "instId": "ETH-USDT"}]

    def test_candle_channel_detection(self):
        assert is_candle_channel("candles")
        assert is_candle_channel("candle1H")
        assert not is_candle_channel("tickers")

    def test_urls_point_to_correct_endpoints(self):
        config = StreamConfig()
        assert config.url_public == PUBLIC_WS_URL
        assert config.url_business == BUSINESS_WS_URL


class FakeWS:
    """Scripted connection: recv() replays items; an Exception item simulates a drop."""

    def __init__(self, script):
        self.script = list(script)
        self.sent = []
        self.url = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def send(self, message):
        self.sent.append(message)

    async def recv(self):
        if not self.script:
            await asyncio.sleep(3600)  # block until wait_for timeout cancels us
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class ReconnectFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_drop_triggers_backoff_and_resubscribe(self):
        ack = json.dumps({"event": "subscribe"})
        ticker = json.dumps({"arg": {"channel": "tickers"}, "data": [{"last": "67000"}]})

        first = FakeWS([ack, ticker, "ping", ConnectionError("dropped")])
        second = FakeWS([ack])
        seen_urls: list[str] = []
        use_first = [True]

        async def factory(url):
            seen_urls.append(url)
            conn = first if use_first[0] else second
            use_first[0] = False
            conn.url = url
            return conn

        sleeps: list[float] = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)
            await asyncio.sleep(0)

        events: list[dict] = []
        client = OKXWebSocketClient(
            config=StreamConfig(
                channels=("tickers",), ping_interval=0.02, reconnect_min=0.01, reconnect_max=0.05
            ),
            on_data=events.append,
            connection_factory=factory,
            sleep=fake_sleep,
        )

        await client.run(duration=0.3)

        # First connection: subscribed, delivered one data event, answered server ping.
        subscribe_op = json.dumps({"op": "subscribe", "args": channel_args(client.config)[0]})
        assert first.sent == [subscribe_op, "pong"]
        assert len(events) == 1
        assert events[0]["channel"] == "tickers"
        assert seen_urls[0] == PUBLIC_WS_URL
        # Reconnect happened exactly once with the minimum backoff.
        assert sleeps == [client.config.reconnect_min]
        assert second.sent[0] == subscribe_op

    async def test_candle_channel_streams_from_business_endpoint(self):
        ack = json.dumps({"event": "subscribe"})
        candle = json.dumps(
            {
                "arg": {"channel": "candle5m"},
                "data": [
                    ["1700000000000", "1", "2", "0.5", "1.5", "10", "15", "15", "1"]
                ],
            }
        )
        business_conn = FakeWS([ack, candle])
        connections = [business_conn]

        async def factory(url):
            assert url == BUSINESS_WS_URL  # candle channels must NOT hit /public
            return connections.pop(0)

        events: list[dict] = []

        async def fake_sleep(_seconds):
            await asyncio.sleep(0)

        client = OKXWebSocketClient(
            config=StreamConfig(channels=("candles",), ping_interval=0.02),
            on_data=events.append,
            connection_factory=factory,
            sleep=fake_sleep,
        )
        await client.run(duration=0.15)

        assert len(events) == 1
        assert events[0]["channel"] == "candle5m"
