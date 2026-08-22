"""MarketLab command line interface.

Subcommands:
    download     Fetch historical candles from OKX into the Raw layer (parquet)
    normalize    Build the Normalized layer (dedup + OHLC checks + gap report)
    report       Research summary over normalized data + current regime
    live         Stream live OKX public data over WebSocket for N seconds
    backtest     Run one strategy backtest and record it as an experiment
    experiments  Compare recorded experiment runs

Examples:
    python -m marketlab download --inst BTC-USDT --bar 1m --days 3
    python -m marketlab normalize --inst BTC-USDT --bar 1m
    python -m marketlab report --inst BTC-USDT --bar 1m
    python -m marketlab live --seconds 15
    python -m marketlab backtest --strategy sma_cross --param fast=10 --param slow=50 \\
        --label baseline --group ab-1
    python -m marketlab experiments --group ab-1
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime

import pandas as pd

from marketlab import __version__
from marketlab.backtest.engine import BacktestConfig
from marketlab.core.regime import RuleBasedRegimeDetector
from marketlab.data.okx import OKXPublicClient
from marketlab.data.okx.history import HistoryDownloader
from marketlab.data.okx.ws import OKXWebSocketClient, StreamConfig
from marketlab.data.store import (
    BAR_SECONDS,
    load_normalized,
    load_raw,
    normalize,
    save_normalized,
    save_raw_batch,
)
from marketlab.experiments import ExperimentLab, run_backtest_experiment
from marketlab.features import FeatureConfig, build_features
from marketlab.strategies import (
    BuyAndHold,
    MeanReversion,
    Momentum,
    SmaCross,
)

STRATEGY_REGISTRY = {
    "buy_and_hold": BuyAndHold,
    "sma_cross": SmaCross,
    "momentum": Momentum,
    "mean_reversion": MeanReversion,
}


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

    bt = sub.add_parser("backtest", help="run + record one strategy backtest")
    bt.add_argument("--inst", default="BTC-USDT")
    bt.add_argument("--bar", default="1m")
    bt.add_argument("--strategy", required=True, choices=sorted(STRATEGY_REGISTRY))
    bt.add_argument("--param", action="append", default=[], metavar="KEY=VALUE",
                    help="strategy constructor parameter (repeatable)")
    bt.add_argument("--days", type=float, default=None, help="use only the last N days of data")
    bt.add_argument("--capital", type=float, default=10_000.0)
    bt.add_argument("--fee", type=float, default=0.001)
    bt.add_argument("--slippage-bps", type=float, default=5.0)
    bt.add_argument("--label", default=None)
    bt.add_argument("--group", default=None, help="tag for A/B comparison runs")
    bt.set_defaults(func=_cmd_backtest)

    exp = sub.add_parser("experiments", help="compare recorded experiment runs")
    exp.add_argument("--group", default=None)
    exp.add_argument("--sort", default="sharpe")
    exp.add_argument("--last", type=int, default=20, help="show at most N rows")
    exp.set_defaults(func=_cmd_experiments)

    ar = sub.add_parser("arena", help="strategy x regime performance matrix (SPEC §27)")
    ar.add_argument("--inst", default="BTC-USDT")
    ar.add_argument("--bar", default="1m")
    ar.add_argument("--days", type=float, default=None)
    ar.add_argument("--metric", default="total_return",
                    choices=["total_return", "sharpe", "max_drawdown"])
    ar.add_argument("--step", type=int, default=None, help="labeling step in bars")
    ar.add_argument("--fee", type=float, default=0.001)
    ar.add_argument("--slippage-bps", type=float, default=5.0)
    ar.set_defaults(func=_cmd_arena)
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


def _cmd_arena(args: argparse.Namespace) -> None:
    from collections import Counter

    from marketlab.arena import arena

    candles_frame = load_normalized(args.inst, args.bar)
    if args.days is not None:
        bars_per_day = 86_400 / BAR_SECONDS[args.bar]
        candles_frame = candles_frame.tail(int(args.days * bars_per_day))

    strategies = {name: cls() for name, cls in STRATEGY_REGISTRY.items()}
    config = BacktestConfig(fee_rate=args.fee, slippage_bps=args.slippage_bps)
    matrix, segments = arena(
        candles_frame,
        strategies,
        config=config,
        step=args.step,
        metric=args.metric,
    )

    distribution = Counter(s.regime.value for s in segments)
    print(f"=== Strategy Arena: {args.inst} {args.bar} "
          f"({len(candles_frame)} bars, metric={args.metric}) ===")
    print("regime segments: " + ", ".join(
        f"{regime} x{count}" for regime, count in sorted(distribution.items())
    ))
    if args.metric == "total_return":
        matrix = matrix.map(lambda v: v if pd.isna(v) else f"{v:+.2%}")
    with pd.option_context("display.width", 200):
        print(matrix.to_string())


def _coerce(value: str):
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            continue
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    return value


def _parse_params(pairs: list[str]) -> dict:
    params = {}
    for pair in pairs:
        key, sep, raw = pair.partition("=")
        if not sep:
            raise SystemExit(f"invalid --param {pair!r}; expected KEY=VALUE")
        params[key.strip()] = _coerce(raw.strip())
    return params


def _cmd_backtest(args: argparse.Namespace) -> None:
    candles_frame = load_normalized(args.inst, args.bar)
    if args.days is not None:
        bars_per_day = 86_400 / BAR_SECONDS[args.bar]
        candles_frame = candles_frame.tail(int(args.days * bars_per_day))
    strategy = STRATEGY_REGISTRY[args.strategy](**_parse_params(args.param))
    config = BacktestConfig(
        initial_capital=args.capital,
        fee_rate=args.fee,
        slippage_bps=args.slippage_bps,
    )
    record, result = run_backtest_experiment(
        candles_frame,
        strategy,
        inst_id=args.inst,
        bar=args.bar,
        config=config,
        label=args.label,
        group=args.group,
    )
    print(f"recorded run {record.run_id} ({len(candles_frame)} bars, "
          f"{record.dataset.fingerprint})")
    print(json.dumps(result.metrics, indent=2))


def _cmd_experiments(args: argparse.Namespace) -> None:
    frame = ExperimentLab().compare(group=args.group, sort_by=args.sort)
    if frame.empty:
        print("no experiment runs recorded yet - use the `backtest` command")
        return
    preferred = [
        "run_id", "created_at", "label", "group", "strategy", "params",
        "dataset", "total_return", "sharpe", "max_drawdown", "trades", "exposure",
    ]
    columns = [c for c in preferred if c in frame.columns]
    frame = frame[columns].head(args.last)
    with pd.option_context("display.width", 200, "display.max_columns", None):
        print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
