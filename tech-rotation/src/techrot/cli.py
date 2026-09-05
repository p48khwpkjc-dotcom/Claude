"""Kommandozeile der Strategie.

    techrot rank        Rangliste des Universums
    techrot rebalance   Rebalancing planen (Standard: Trockenlauf)
    techrot backtest    Historische Simulation
    techrot status      Depot, Cash, letzter Lauf
    techrot check-data  Datenqualitaet je Ticker
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from .backtest import run_backtest
from .brokers import BrokerError, build_broker
from .config import Config, ConfigError, load_config
from .data import DataError, check_data_quality, load_prices
from .execution import execute_plan, mark_to_market, plan_rebalance
from .report import plan_to_markdown, render_backtest, render_plan
from .state import PortfolioState

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config.yaml"


def _load(args: argparse.Namespace) -> tuple[Config, PortfolioState]:
    cfg = load_config(args.config)
    state = PortfolioState.load(cfg.path(cfg.execution.state_file), cfg.execution.starting_cash)
    return cfg, state


def cmd_rank(args: argparse.Namespace) -> int:
    cfg, state = _load(args)
    prices = load_prices(cfg, refresh=args.refresh)
    plan = plan_rebalance(cfg, prices, state, force=True)
    print(render_plan(plan, top=args.top))
    return 0


def cmd_rebalance(args: argparse.Namespace) -> int:
    cfg, state = _load(args)
    prices = load_prices(cfg, refresh=args.refresh)

    # Bei echter Ausfuehrung zuerst den Broker fragen: der Plan muss auf dem
    # tatsaechlichen Depotstand rechnen, nicht auf der lokalen Buchhaltung.
    broker = None
    if args.execute:
        try:
            broker = build_broker(cfg.execution, state)
            broker.sync(state)
        except BrokerError as exc:
            print(f"FEHLER Broker: {exc}", file=sys.stderr)
            return 2

    plan = plan_rebalance(cfg, prices, state, force=args.force)

    print(render_plan(plan, top=args.top))

    if args.markdown:
        Path(args.markdown).write_text(plan_to_markdown(plan), encoding="utf-8")
        print(f"\nMarkdown-Report geschrieben: {args.markdown}")

    if not args.execute:
        print("\n[Trockenlauf] Keine Orders gesendet. Mit --execute ausfuehren.")
        return 0

    if not plan.due:
        print("\nKein Rebalancing faellig -- nichts zu tun.")
        return 0

    assert broker is not None  # oben zusammen mit args.execute gebaut
    mode = "LIVE" if cfg.execution.mode == "live" else "Papier"
    print(f"\nSende {len(plan.orders)} Orders an {broker.name} ({mode}) ...")
    fills = execute_plan(cfg, plan, state, broker)
    for fill in fills:
        print(
            f"  {fill.status:<10} {fill.side.upper():<4} {fill.ticker:<8} "
            f"{abs(fill.quantity):>10,.0f} @ {fill.price:>10,.2f}"
        )

    failed = len(plan.orders) - len(fills)
    if failed:
        print(
            f"\nWARNUNG: {failed} Order(s) nicht ausgefuehrt -- Details im Journal "
            f"{cfg.path(cfg.execution.journal_file)}",
            file=sys.stderr,
        )

    mark_to_market(state, prices)
    state_path = cfg.path(cfg.execution.state_file)
    state.save(state_path)
    print(f"\nZustand gespeichert: {state_path}")
    return 1 if failed else 0


def cmd_backtest(args: argparse.Namespace) -> int:
    cfg, _ = _load(args)
    prices = load_prices(cfg, refresh=args.refresh)
    result = run_backtest(cfg, prices)
    print(render_backtest(result))

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        result.equity.to_csv(out / "equity.csv", header=["equity"])
        result.trades.to_csv(out / "trades.csv", index=False)
        result.rebalances.to_csv(out / "rebalances.csv", index=False)
        print(f"\nErgebnisse geschrieben nach {out}/")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg, state = _load(args)
    print(f"Strategie      {cfg.name}")
    print(f"Broker         {cfg.execution.broker} ({cfg.execution.mode})")
    print(f"Letztes Rebal. {state.last_rebalance or 'nie'}")
    print(f"Cash           {state.cash:,.2f}")

    if not state.positions:
        print("Positionen     keine")
        return 0

    try:
        prices = load_prices(cfg, refresh=False)
    except DataError as exc:
        print(f"\nKurse nicht verfuegbar ({exc}); zeige nur Stueckzahlen.")
        for ticker, shares in sorted(state.positions.items()):
            print(f"  {ticker:<8} {shares:>10,.0f}")
        return 0

    last = prices.close.iloc[-1]
    equity = state.equity(last)
    print(f"Depotwert      {equity:,.2f}  (Kurse per {prices.last_date.date()})")
    print("\nPositionen")
    for ticker, shares in sorted(state.positions.items()):
        price = float(last.get(ticker, float("nan")))
        value = shares * price
        print(
            f"  {ticker:<8} {shares:>10,.0f} Stk @ {price:>10,.2f} "
            f"= {value:>13,.2f}  ({value / equity:>6.2%})"
        )

    curve = state.equity_curve()
    if curve is not None and len(curve) > 1:
        peak = float(curve.max())
        print(f"\nDrawdown       {1 - equity / peak:.2%} (Hoch {peak:,.2f})")
    return 0


def cmd_check_data(args: argparse.Namespace) -> int:
    cfg, _ = _load(args)
    prices = load_prices(cfg, refresh=args.refresh)
    quality = check_data_quality(prices, list(cfg.tickers), cfg.data, prices.last_date)

    print(f"Kursstand per {prices.last_date.date()}  ({len(prices.close)} Handelstage)\n")
    print(f"  {'Ticker':<8} {'Status':<6} {'Tage':>6} {'Alter':>6} {'Luecken':>8}  Hinweis")
    problems = 0
    for ticker in sorted(quality):
        q = quality[ticker]
        problems += 0 if q.ok else 1
        print(
            f"  {q.ticker:<8} {'ok' if q.ok else 'FEHLER':<6} {q.history_days:>6} "
            f"{q.staleness_days:>6} {q.missing_ratio:>7.1%}  "
            f"{'' if q.ok else q.reason}"
        )
    print(f"\n{len(quality) - problems} von {len(quality)} Tickern in Ordnung.")
    return 1 if problems else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="techrot",
        description="Monatliche Rotation in die staerksten Tech-Aktien.",
    )
    parser.add_argument(
        "--config", default=str(DEFAULT_CONFIG), help="Pfad zur config.yaml"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--refresh", action="store_true", help="Cache umgehen")

    p_rank = sub.add_parser("rank", help="Rangliste anzeigen")
    add_common(p_rank)
    p_rank.add_argument("--top", type=int, default=15)
    p_rank.set_defaults(func=cmd_rank)

    p_reb = sub.add_parser("rebalance", help="Rebalancing planen und optional ausfuehren")
    add_common(p_reb)
    p_reb.add_argument("--top", type=int, default=15)
    p_reb.add_argument(
        "--execute", action="store_true", help="Orders tatsaechlich senden"
    )
    p_reb.add_argument(
        "--force", action="store_true", help="Auch ausserhalb des Monatstermins"
    )
    p_reb.add_argument("--markdown", help="Report zusaetzlich als Markdown speichern")
    p_reb.set_defaults(func=cmd_rebalance)

    p_bt = sub.add_parser("backtest", help="Historische Simulation")
    add_common(p_bt)
    p_bt.add_argument("--out", help="Verzeichnis fuer CSV-Ergebnisse")
    p_bt.set_defaults(func=cmd_backtest)

    p_st = sub.add_parser("status", help="Depotstand anzeigen")
    p_st.set_defaults(func=cmd_status)

    p_cd = sub.add_parser("check-data", help="Datenqualitaet pruefen")
    add_common(p_cd)
    p_cd.set_defaults(func=cmd_check_data)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pd.set_option("display.width", 140)
    try:
        return int(args.func(args))
    except (ConfigError, DataError, BrokerError, ValueError) as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
