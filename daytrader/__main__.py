"""Command line entry point.

    python -m daytrader fetch      # download candles into the local cache
    python -m daytrader backtest   # compare strategies, write out/report.md
    python -m daytrader selftest   # end-to-end run on synthetic data, no network
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from .backtest.runner import run_matrix, write_report
from .config import load_config
from .data import loader
from .strategies import available


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_fetch(args, cfg) -> int:
    symbols = args.symbols.split(",") if args.symbols else cfg.data.symbols
    interval = args.interval or cfg.data.interval
    days = args.days or cfg.data.history_days
    failed = []
    for symbol in symbols:
        try:
            df = loader.update(symbol.strip(), interval, days, cfg.cache_dir)
            print(f"{symbol:<10} {len(df):>7,} bars  {df.index[0]:%Y-%m-%d} .. {df.index[-1]:%Y-%m-%d}")
        except Exception as exc:  # network, symbol typo, exchange outage
            failed.append(symbol)
            print(f"{symbol:<10} FAILED: {exc}", file=sys.stderr)
    if failed:
        print(f"\n{len(failed)} symbol(s) failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


def _load_all(cfg, symbols: list[str], source: str) -> dict[str, pd.DataFrame]:
    data = {}
    for symbol in symbols:
        symbol = symbol.strip()
        data[symbol] = loader.load(
            symbol, cfg.data.interval, cfg.cache_dir,
            source=source, synthetic_bars=cfg.data.synthetic_bars,
        )
    return data


def cmd_backtest(args, cfg) -> int:
    symbols = args.symbols.split(",") if args.symbols else cfg.data.symbols
    strategies = available() if args.strategy in (None, "all") else args.strategy.split(",")
    source = args.source or cfg.data.source

    data = _load_all(cfg, symbols, source)
    bars = sum(len(d) for d in data.values())
    note = f"{source} ({bars:,} bars across {len(data)} symbol(s))"
    if source == "synthetic":
        note += " -- SYNTHETIC: proves the machinery, says nothing about real edge"

    matrix, results = run_matrix(cfg, strategies, data)
    if matrix.empty:
        print("no results produced", file=sys.stderr)
        return 1

    path = write_report(cfg, matrix, results, cfg.out_dir, note, data)
    cols = ["strategy", "segment", "trades", "win_rate", "profit_factor",
            "expectancy_r", "total_return_pct", "max_drawdown_pct"]
    from .backtest.runner import aggregate
    print()
    print(aggregate(matrix)[cols].round(2).to_string(index=False))
    print(f"\nreport: {path}")
    if source == "synthetic":
        print("\nSynthetic data. Run `python -m daytrader fetch` on a machine with "
              "exchange access before drawing any conclusion.")
    return 0


def cmd_costs(args, cfg) -> int:
    """What fees and slippage cost per unit of risk, before any strategy exists."""
    from .backtest import costs as cost_module

    symbols = args.symbols.split(",") if args.symbols else cfg.data.symbols
    data = _load_all(cfg, symbols, args.source or cfg.data.source)
    table = cost_module.summarise(data, cfg)
    print(table.round(2).to_string(index=False))
    print()
    for name, params in cfg.strategies.items():
        mult = params.get("stop_atr_mult")
        if mult is None:
            continue
        first = table[table["symbol"] == table["symbol"].iloc[0]]
        print(f"{name:<16} {cost_module.verdict(first, float(mult))}")
    return 0


def cmd_regimes(args, cfg) -> int:
    """Test each strategy against market conditions built to order.

    Needs no exchange data: a trend strategy that loses on a series which
    trends by construction is broken, and that verdict is available offline.
    """
    from .backtest import regimes

    strategies = available() if args.strategy in (None, "all") else args.strategy.split(",")
    matrix = regimes.run(cfg, strategies, bars=args.bars)

    claims = regimes.check_claims(cfg, matrix)
    damage = regimes.cost_damage(matrix)

    print("\n=== Does each strategy do what it claims? (frictionless) ===")
    print(claims.to_string(index=False))
    frequency = regimes.signal_frequency(cfg, strategies, bars=args.bars)
    calib = regimes.calibration(cfg, matrix, frequency)

    print("\n=== Where does each strategy fire, and is that where it works? ===")
    print(calib.round(1).to_string(index=False))

    print("\n=== What costs take, per unit of risk ===")
    print(damage.round(3).to_string(index=False))

    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(cfg.out_dir / "regime_matrix.csv", index=False)
    frequency.to_csv(cfg.out_dir / "regime_signal_frequency.csv", index=False)
    claims.to_csv(cfg.out_dir / "regime_claims.csv", index=False)
    path = regimes.write_report(cfg, matrix, claims, calib, damage, cfg.out_dir)
    print(f"\nreport: {path}")

    failures = (claims["status"] == "FAIL").sum()
    if failures:
        print(f"\n{failures} strategy/regime claim(s) failed -- those strategies are "
              "broken independently of any real market.")
    return 0


def cmd_selftest(args, cfg) -> int:
    cfg.data.source = "synthetic"
    cfg.data.symbols = ["BTCUSDT"]
    cfg.data.synthetic_bars = args.bars
    args.symbols, args.strategy, args.source = "BTCUSDT", "all", "synthetic"
    return cmd_backtest(args, cfg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="daytrader", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-c", "--config", default="config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch", help="download candles into the local cache")
    p_fetch.add_argument("--symbols", help="comma separated, defaults to config")
    p_fetch.add_argument("--interval", help="defaults to config")
    p_fetch.add_argument("--days", type=int, help="defaults to config")
    p_fetch.set_defaults(func=cmd_fetch)

    p_bt = sub.add_parser("backtest", help="compare strategies and write a report")
    p_bt.add_argument("--symbols", help="comma separated, defaults to config")
    p_bt.add_argument("--strategy", default="all", help=f"one of: all, {', '.join(available())}")
    p_bt.add_argument("--source", choices=["cache", "synthetic"], help="defaults to config")
    p_bt.set_defaults(func=cmd_backtest)

    p_cost = sub.add_parser("costs", help="fees and slippage per unit of risk")
    p_cost.add_argument("--symbols", help="comma separated, defaults to config")
    p_cost.add_argument("--source", choices=["cache", "synthetic"])
    p_cost.set_defaults(func=cmd_costs)

    p_reg = sub.add_parser("regimes", help="test strategies against constructed market conditions")
    p_reg.add_argument("--strategy", default="all")
    p_reg.add_argument("--bars", type=int, default=20_000)
    p_reg.set_defaults(func=cmd_regimes)

    p_self = sub.add_parser("selftest", help="end-to-end run on synthetic data")
    p_self.add_argument("--bars", type=int, default=30_000)
    p_self.set_defaults(func=cmd_selftest)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    cfg = load_config(args.config)
    return args.func(args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
