"""MarketLab command line interface.

Subcommands:
    download   Fetch historical candles from OKX into the Raw layer (parquet)
    normalize  Build the Normalized layer (dedup + OHLC checks + gap report)
    report     Research summary over normalized data + current regime
    live       Stream live OKX public data over WebSocket for N seconds

Examples:
    python -m marketlab download --inst BTC-USDT --bar 1m --days 3
    python -m marketlab normalize --inst BTC-USDT --bar 1m
    python -m marketlab report --inst BTC-USDT --bar 1m
    python -m marketlab live --seconds 15
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime

from marketlab import __version__
from marketlab.core.regime import RuleBasedRegimeDetector
from marketlab.data.okx import OKXPublicClient
from marketlab.data.okx.history import HistoryDownloader
from marketlab.data.okx.ws import OKXWebSocketClient, StreamConfig
from marketlab.data.store import (
    load_normalized,
    load_raw,
    normalize,
    save_normalized,
    save_raw_batch,
)
from marketlab.features import FeatureConfig, build_features


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.func(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="marketlab", description="MarketLab CLI")
    parser.add_argument("--version", action="version", version=f"MarketLab {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    dl = sub.add_parser("download", help="fetch history into the Raw layer")
    dl.add_argument("--inst", default="BTC-USDT")
    dl.add_argument("--bar", default="1m")
    dl.add_argument("--days", type=float, default=3.0)
    dl.add_argument("--end", default=None, help="tz-aware ISO end time (default now)")
    dl.set_defaults(func=_cmd_download)

    norm = sub.add_parser("normalize", help="build the Normalized layer")
    norm.add_argument("--inst", default="BTC-USDT")
    norm.add_argument("--bar", default="1m")
    norm.set_defaults(func=_cmd_normalize)

    rep = sub.add_parser("report", help="research summary + current regime")
    rep.add_argument("--inst", default="BTC-USDT")
    rep.add_argument("--bar", default="1m")
    rep.add_argument("--window", type=int, default=500, help="bars fed to regime detector")
    rep.set_defaults(func=_cmd_report)

    live = sub.add_parser("live", help="stream live public data")
    live.add_argument("--inst", default="BTC-USDT")
    live.add_argument("--bar", default="5m")
    live.add_argument("--seconds", type=float, default=15.0)
    live.add_argument("--channels", default="tickers,trades,candles")
    live.set_defaults(func=_cmd_live)
    return parser


def _cmd_download(args: argparse.Namespace) -> None:
    end = datetime.fromisoformat(args.end) if args.end else None
    with OKXPublicClient(timeout=30.0) as client:
        downloader = HistoryDownloader(client=client, inst_id=args.inst, bar=args.bar)
        frame = downloader.download(
            days=args.days,
            end=end,
            on_page=lambda n, rows: print(f"  page {n}: {rows} rows"),
        )
    try:
        path = save_raw_batch(frame, args.inst, args.bar)
    except FileExistsError as exc:
        print(f"skip (immutable batch exists): {exc}")
        return
    print(f"saved {len(frame)} candles -> {path}")


def _cmd_normalize(args: argparse.Namespace) -> None:
    raw = load_raw(args.inst, args.bar)
    frame, gaps = normalize(raw, args.bar)
    path = save_normalized(frame, args.inst, args.bar)
    print(f"normalized {len(frame)} rows -> {path}")
    print(f"quality: {gaps.summarize()}")


def _cmd_report(args: argparse.Namespace) -> None:
    candles = load_normalized(args.inst, args.bar)
    features = build_features(candles, FeatureConfig())
    window = candles.tail(args.window)

    regime = RuleBasedRegimeDetector().detect(window)

    last = float(window["close"].iloc[-1])
    first = float(window["close"].iloc[0])
    vol_col = next(c for c in features.columns if c.startswith("realized_vol_"))
    print(f"=== {args.inst} {args.bar} ===")
    print(
        f"span   : {window['timestamp'].iloc[0]} -> {window['timestamp'].iloc[-1]}"
        f" ({len(window)} bars)"
    )
    print(f"price  : {last:.2f}  ({(last / first - 1) * 100:+.3f}% over window)")
    print(f"regime : {regime.regime.value}  confidence={regime.confidence:.2f}")
    cols = ["close", "log_return_1", vol_col, "hl_range_pct"]
    cols += [f"return_lag{n}" for n in FeatureConfig().momentum_lookbacks]
    print(features[cols].tail().to_string(index=False))


def _cmd_live(args: argparse.Namespace) -> None:
    channels = tuple(c.strip() for c in args.channels.split(",") if c.strip())

    def handle(event: dict) -> None:
        channel = event["channel"]
        for row in event["data"][:2]:
            if channel == "tickers":
                print(f"[ticker] {row.get('instId')} last={row.get('last')} ts={row.get('ts')}")
            elif channel == "trades":
                print(f"[trade ] px={row.get('px')} sz={row.get('sz')} side={row.get('side')}")
            else:  # candles / candle{bar}
                print(f"[candle] {row}")

    config = StreamConfig(channels=channels, inst_id=args.inst, bar=args.bar)
    client = OKXWebSocketClient(config=config, on_data=handle)
    print(f"streaming {channels} for {args.seconds}s ...")
    try:
        asyncio.run(client.run(duration=args.seconds))
    finally:
        print("done")


if __name__ == "__main__":
    main()
