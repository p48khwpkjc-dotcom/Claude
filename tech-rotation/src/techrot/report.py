"""Berichte fuer Konsole und CI-Artefakt."""

from __future__ import annotations

import pandas as pd

from .backtest import BacktestResult
from .execution import RebalancePlan

PERCENT_KEYS = {
    "total_return",
    "cagr",
    "volatility",
    "max_drawdown",
    "best_day",
    "worst_day",
    "positive_days",
    "avg_turnover",
    "avg_exposure",
}

METRIC_LABELS = {
    "total_return": "Gesamtrendite",
    "cagr": "CAGR",
    "volatility": "Volatilitaet p.a.",
    "sharpe": "Sharpe",
    "sortino": "Sortino",
    "max_drawdown": "Max Drawdown",
    "calmar": "Calmar",
    "best_day": "Bester Tag",
    "worst_day": "Schlechtester Tag",
    "positive_days": "Positive Tage",
    "years": "Zeitraum (Jahre)",
    "total_costs": "Handelskosten",
    "n_trades": "Trades",
    "avg_turnover": "Turnover je Rebalancing",
    "avg_exposure": "Exposure im Mittel",
    "n_rebalances": "Rebalancings",
}


def _fmt(key: str, value: float) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "n/a"
    if key in PERCENT_KEYS:
        return f"{value:.2%}"
    if key in {"n_trades", "n_rebalances"}:
        return f"{value:.0f}"
    if key in {"total_costs"}:
        return f"{value:,.2f}"
    return f"{value:.2f}"


def render_plan(plan: RebalancePlan, *, top: int = 15) -> str:
    """Menschlich lesbare Vorschau eines Rebalancing-Laufs."""
    lines: list[str] = []
    add = lines.append

    add(f"# Rebalancing-Plan  |  Stichtag {plan.asof.date()}")
    add("")
    add(f"Depotwert         {plan.equity:>14,.2f}")
    add(f"Zielexposure      {sum(plan.target_weights.values()):>14.1%}")
    add(f"Cash-Quote        {plan.cash_weight:>14.1%}")
    add(f"Geplanter Turnover{plan.turnover:>14.1%}")
    add(f"Faellig           {'ja' if plan.due else 'nein':>14}")
    add("")

    add("## Risiko")
    e = plan.exposure
    add(f"  Regime-Filter   {'bestanden' if e.regime_ok else 'REISST'}")
    add(f"  Erwartete Vol   {e.realized_vol:.1%}" if e.realized_vol else "  Erwartete Vol   n/a")
    add(f"  Vol-Skalierung  {e.vol_scalar:.2f}")
    add(f"  Drawdown        {e.current_drawdown:.1%} (Faktor {e.drawdown_scalar:.2f})")
    for note in plan.notes:
        add(f"  - {note}")
    add("")

    add(f"## Ranking (Top {top})")
    add(f"  {'#':>3} {'Ticker':<8} {'Score':>7} {'12-1':>8} {'6-1':>8} {'Vol':>7}  Status")
    shown = plan.ranking.head(top)
    for ticker, row in shown.iterrows():
        eligible = plan.eligibility.get(str(ticker))
        if str(ticker) in plan.selected:
            status = "GEWAEHLT"
        elif eligible and not eligible.eligible:
            status = eligible.reason_text[:52]
        else:
            status = "-"
        add(
            f"  {int(row['rank']):>3} {str(ticker):<8} {row['score']:>7.2f} "
            f"{row.get('mom_12_1', float('nan')):>7.1%} "
            f"{row.get('mom_6_1', float('nan')):>7.1%} "
            f"{row.get('volatility', float('nan')):>6.1%}  {status}"
        )
    add("")

    add("## Zielgewichte")
    if plan.target_weights:
        for ticker, weight in sorted(plan.target_weights.items(), key=lambda kv: -kv[1]):
            current = plan.current_weights.get(ticker, 0.0)
            add(f"  {ticker:<8} {weight:>7.2%}   (bisher {current:>6.2%})")
    else:
        add("  keine -- vollstaendig in Cash")
    add("")

    blocked = plan.blocked
    if blocked:
        add(f"## Ausgeschlossen ({len(blocked)})")
        for ticker, reason in sorted(blocked.items()):
            add(f"  {ticker:<8} {reason}")
        add("")

    add(f"## Orders ({len(plan.orders)})")
    if plan.orders:
        for order in plan.orders:
            add(
                f"  {order.side.upper():<4} {order.ticker:<8} "
                f"{abs(order.quantity):>10,.0f} Stk @ {order.reference_price:>10,.2f} "
                f"= {order.notional:>12,.2f}"
            )
    else:
        add("  keine")

    return "\n".join(lines)


def render_backtest(result: BacktestResult) -> str:
    """Kennzahlen des Backtests, Strategie gegen Benchmark."""
    lines: list[str] = []
    add = lines.append

    add("# Backtest")
    add("")
    add(f"Zeitraum   {result.equity.index[0].date()} bis {result.equity.index[-1].date()}")
    add(f"Startwert  {result.equity.iloc[0]:,.2f}")
    add(f"Endwert    {result.equity.iloc[-1]:,.2f}")
    add("")

    has_bench = result.benchmark_metrics is not None
    header = f"  {'Kennzahl':<26} {'Strategie':>14}"
    if has_bench:
        header += f" {'Benchmark':>14}"
    add(header)
    add(f"  {'-' * 26} {'-' * 14}" + (f" {'-' * 14}" if has_bench else ""))

    for key, label in METRIC_LABELS.items():
        if key not in result.metrics:
            continue
        row = f"  {label:<26} {_fmt(key, result.metrics[key]):>14}"
        if has_bench:
            bench_value = result.benchmark_metrics.get(key)  # type: ignore[union-attr]
            row += f" {_fmt(key, bench_value) if bench_value is not None else 'n/a':>14}"
        add(row)

    if not result.rebalances.empty:
        add("")
        add("## Letzte Rebalancings")
        tail = result.rebalances.tail(6)
        for _, row in tail.iterrows():
            trade_date = row["trade_date"]
            stamp = trade_date.date() if pd.notna(trade_date) else "offen"
            add(
                f"  {stamp}  Exposure {row['exposure']:>6.1%}  "
                f"Turnover {row['realized_turnover']:>6.1%}  "
                f"{int(row['n_selected'])} Titel: {row['selected']}"
            )

    return "\n".join(lines)


def plan_to_markdown(plan: RebalancePlan) -> str:
    """Kompakte Markdown-Fassung fuer den CI-Job."""
    lines = [
        f"## Tech-Rotation -- {plan.asof.date()}",
        "",
        f"- Depotwert: **{plan.equity:,.2f}**",
        f"- Zielexposure: **{sum(plan.target_weights.values()):.1%}** "
        f"(Cash {plan.cash_weight:.1%})",
        f"- Rebalancing faellig: **{'ja' if plan.due else 'nein'}**",
        f"- Orders: **{len(plan.orders)}**, geplanter Turnover {plan.turnover:.1%}",
        "",
    ]

    if plan.target_weights:
        lines += ["| Ticker | Ziel | Bisher | Score |", "| --- | ---: | ---: | ---: |"]
        for ticker, weight in sorted(plan.target_weights.items(), key=lambda kv: -kv[1]):
            score = (
                plan.ranking.at[ticker, "score"] if ticker in plan.ranking.index else float("nan")
            )
            lines.append(
                f"| {ticker} | {weight:.2%} | "
                f"{plan.current_weights.get(ticker, 0.0):.2%} | {score:.2f} |"
            )
        lines.append("")

    if plan.notes:
        lines.append("**Risikohinweise**")
        lines += [f"- {note}" for note in plan.notes]
        lines.append("")

    return "\n".join(lines)
