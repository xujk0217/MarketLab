"""OKX public WebSocket streams: tickers / trades / candles with auto-reconnect.

OKX serves candlestick channels from the *business* endpoint while tickers and
trades live on the public endpoint, so this client maintains one reconnecting
connection per endpoint group. Connection handling is injectable
(``connection_factory`` + ``sleep``) so everything runs offline in tests.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

PUBLIC_WS_URL = "wss://ws.okx.com:8443/ws/v5/public"
BUSINESS_WS_URL = "wss://ws.okx.com:8443/ws/v5/business"


@dataclass(frozen=True)
class StreamConfig:
    url_public: str = PUBLIC_WS_URL
    url_business: str = BUSINESS_WS_URL
    channels: tuple[str, ...] = ("tickers", "trades", "candles")
    inst_id: str = "BTC-USDT"
    bar: str = "5m"  # candle channels subscribe as "candle{bar}"
    ping_interval: float = 20.0  # OKX drops idle connections after 30 s
    reconnect_min: float = 1.0
    reconnect_max: float = 30.0


def is_candle_channel(channel: str) -> bool:
    return channel == "candles" or channel.startswith("candle")


def channel_args(config: StreamConfig) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Split subscriptions into (public_args, business_args).

    Candle channels use OKX's precomposed names (``candle5m``, ``candle1H``...)
    and belong to the business endpoint.
    """
    public: list[dict[str, str]] = []
    business: list[dict[str, str]] = []
    for channel in config.channels:
        if is_candle_channel(channel):
            business.append({"channel": f"candle{config.bar}", "instId": config.inst_id})
        else:
            public.append({"channel": channel, "instId": config.inst_id})
    return public, business


def parse_message(raw: str | bytes) -> dict[str, Any]:
    """Classify one inbound text frame into a typed event dict.

    Returns {"type": "subscribe"|"error"|"pong", ...} for control frames,
    {"type": "ping"} for server heartbeat probes, or
    {"type": "data", "channel": ..., "data": [...]} for market payloads.
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if raw.strip() == "ping":  # server-level heartbeat probe
        return {"type": "ping"}
    if raw.strip() == "pong":
        return {"type": "pong"}
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"unparseable websocket frame: {raw[:80]!r}") from exc
    event = msg.get("event")
    if event in ("subscribe", "unsubscribe", "error"):
        return {"type": event, "code": msg.get("code"), "msg": msg.get("msg"), **msg}
    if "arg" in msg and "data" in msg:
        return {
            "type": "data",
            "channel": msg["arg"].get("channel"),
            "arg": msg["arg"],
            "data": msg["data"],
        }
    raise ValueError(f"unrecognized websocket payload: {raw[:80]!r}")


ConnectionFactory = Callable[[str], Awaitable[Any]]
SleepFunc = Callable[[float], Awaitable[None]]


@dataclass
class OKXWebSocketClient:
    """Subscribe to public channels forever; auto-resubscribe after drops."""

    config: StreamConfig = field(default_factory=StreamConfig)
    on_data: Callable[[dict[str, Any]], None] | None = None
    connection_factory: ConnectionFactory | None = None  # default: websockets.connect(url)
    sleep: SleepFunc = asyncio.sleep

    async def run(self, duration: float | None = None) -> None:
        """Stream until ``duration`` seconds elapse (None = forever)."""
        public_args, business_args = channel_args(self.config)
        tasks = []
        if public_args:
            tasks.append(
                asyncio.create_task(
                    self._stream(self.config.url_public, public_args, duration)
                )
            )
        if business_args:
            tasks.append(
                asyncio.create_task(
                    self._stream(self.config.url_business, business_args, duration)
                )
            )
        if tasks:
            await asyncio.gather(*tasks)

    async def _stream(self, url: str, args: list[dict[str, str]], duration: float | None) -> None:
        delay = self.config.reconnect_min
        deadline = None if duration is None else _loop_time() + duration
        while deadline is None or _loop_time() < deadline:
            try:
                async with await self._connect(url) as ws:
                    await ws.send(json.dumps({"op": "subscribe", "args": args}))
                    logger.info("subscribed on %s: %s", url, args)
                    delay = self.config.reconnect_min
                    await self._pump(ws, deadline)
            except Exception as exc:  # noqa: BLE001 - reconnect on ANY transport failure
                if deadline is not None and _loop_time() >= deadline:
                    break
                logger.warning("stream dropped (%s); reconnecting in %.1fs", exc, delay)
                await self.sleep(delay)
                delay = min(delay * 2, self.config.reconnect_max)

    async def _connect(self, url: str) -> Any:
        if self.connection_factory is not None:
            return await self.connection_factory(url)
        import websockets

        return await websockets.connect(url)

    async def _pump(self, ws: Any, deadline: float | None) -> None:
        next_ping = _loop_time() + self.config.ping_interval
        while True:
            now = _loop_time()
            if deadline is not None and now >= deadline:
                return
            horizon = min(next_ping, deadline) if deadline is not None else next_ping
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.0, horizon - now))
            except TimeoutError:
                if _loop_time() >= next_ping:
                    await ws.send("ping")
                    next_ping = _loop_time() + self.config.ping_interval
                continue
            event = parse_message(raw)
            kind = event["type"]
            if kind == "pong":
                continue
            if kind == "ping":
                await ws.send("pong")
                continue
            if kind == "error":
                raise RuntimeError(f"OKX ws error {event.get('code')}: {event.get('msg')}")
            if kind == "data" and self.on_data is not None:
                self.on_data(event)


def _loop_time() -> float:
    return asyncio.get_running_loop().time()
