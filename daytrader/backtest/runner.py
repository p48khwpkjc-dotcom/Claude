"""Runs the strategy/symbol matrix and writes the comparison report.

Selection happens on the first `train_split` of history; the remainder is held
back and never consulted while choosing. A strategy that looks good in-sample
and falls apart out-of-sample has been fitted to noise, and that gap is the
single most useful number in the whole report.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..config import Config
from ..core.types import BacktestResult
from ..strategies import build
from . import costs
from .engine import BacktestEngine
from .metrics import Metrics, compute, exit_breakdown, trades_frame

log = logging.getLogger(__name__)


@dataclass(slots=True)
class Segment:
    label: str
    result: BacktestResult
    metrics: Metrics


def split_index(df: pd.DataFrame, train_split: float) -> int:
    return int(len(df) * train_split)


def run_segment(cfg: Config, strategy_name: str, symbol: str, df: pd.DataFrame,
                label: str) -> Segment:
    strategy = build(strategy_name, cfg)
    result = BacktestEngine(cfg, strategy, symbol).run(df)
    return Segment(label=label, result=result, metrics=compute(result))


def run_walk_forward(cfg: Config, strategy_name: str, symbol: str,
                     df: pd.DataFrame) -> dict[str, Segment]:
    """Split into in-sample and out-of-sample, warming up the latter properly."""
    strategy = build(strategy_name, cfg)
    warmup = max(cfg.backtest.warmup_bars, strategy.warmup_bars)
    cut = split_index(df, cfg.backtest.train_split)

    segments = {"in_sample": run_segment(cfg, strategy_name, symbol, df.iloc[:cut], "in_sample")}
    if len(df) - cut > warmup + 50:
        # Hand the out-of-sample run enough history to warm its indicators, so
        # it starts trading exactly at the split rather than well after it.
        oos = df.iloc[max(0, cut - warmup):]
        segments["out_of_sample"] = run_segment(cfg, strategy_name, symbol, oos, "out_of_sample")
    return segments


def run_matrix(
    cfg: Config, strategies: list[str], data: dict[str, pd.DataFrame]
) -> tuple[pd.DataFrame, dict[tuple[str, str], BacktestResult]]:
    """Backtest every strategy on every symbol, in and out of sample."""
    rows: list[dict] = []
    results: dict[tuple[str, str], BacktestResult] = {}
    for strategy_name in strategies:
        for symbol, df in data.items():
            log.info("backtesting %s on %s (%d bars)", strategy_name, symbol, len(df))
            for label, seg in run_walk_forward(cfg, strategy_name, symbol, df).items():
                row = seg.metrics.as_dict()
                row["segment"] = label
                row["kill_switch_exits"] = seg.result.blocked_by_kill_switch
                rows.append(row)
                results[(f"{strategy_name} ({label})", symbol)] = seg.result
    return pd.DataFrame(rows), results


def aggregate(matrix: pd.DataFrame) -> pd.DataFrame:
    """Combine per-symbol results into one line per strategy and segment."""
    if matrix.empty:
        return matrix
    grouped = matrix.groupby(["strategy", "segment"], as_index=False).agg(
        symbols=("symbol", "nunique"),
        trades=("trades", "sum"),
        win_rate=("win_rate", "mean"),
        profit_factor=("profit_factor", "mean"),
        expectancy_r=("expectancy_r", "mean"),
        total_return_pct=("total_return_pct", "mean"),
        max_drawdown_pct=("max_drawdown_pct", "max"),
        sharpe=("sharpe", "mean"),
        trades_per_day=("trades_per_day", "mean"),
        fees_pct_of_gross=("fees_pct_of_gross", "mean"),
    )
    return grouped.sort_values(["segment", "profit_factor"], ascending=[True, False])


def _md(df: pd.DataFrame, floats: int = 2, index: bool = False) -> str:
    """Minimal markdown table, so the bot needs no extra dependency to report."""
    df = df.round(floats)
    if index:
        df = df.reset_index()
    header = [str(c) for c in df.columns]
    rows = [[("" if pd.isna(v) else str(v)) for v in row] for row in df.itertuples(index=False)]
    widths = [max(len(header[i]), *(len(r[i]) for r in rows)) if rows else len(header[i])
              for i in range(len(header))]
    def line(cells): return "| " + " | ".join(c.ljust(w) for c, w in zip(cells, widths)) + " |"
    out = [line(header), "|" + "|".join("-" * (w + 2) for w in widths) + "|"]
    out += [line(r) for r in rows]
    return "\n".join(out)


def _fmt(df: pd.DataFrame, floats: int = 2) -> str:
    return _md(df, floats)


def write_report(cfg: Config, matrix: pd.DataFrame, results: dict[tuple[str, str], BacktestResult],
                 out_dir: Path, source_note: str,
                 data: dict[str, pd.DataFrame] | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = aggregate(matrix)

    lines = [
        "# Strategy comparison",
        "",
        f"- Data: {source_note}",
        f"- Symbols: {', '.join(sorted({s for _, s in results}))}",
        f"- Timeframe: {cfg.data.interval} decisions, {cfg.data.htf_interval} trend filter",
        f"- Start equity: {cfg.account.start_equity:,.0f} {cfg.account.quote_currency}",
        f"- Risk per trade: {cfg.risk.risk_per_trade_pct}% | daily kill switch: "
        f"{cfg.risk.max_daily_loss_pct}% | leverage: {cfg.risk.max_leverage}x",
        f"- Costs: {cfg.execution.taker_fee_pct}% fee per side, "
        f"{cfg.execution.slippage_bps} bps slippage ({cfg.execution.stop_slippage_bps} on stops)",
        f"- Selection on the first {cfg.backtest.train_split:.0%} of history; "
        "the rest is held back.",
        "",
        "## Summary by strategy",
        "",
        _fmt(summary),
        "",
        "## Per symbol",
        "",
        _fmt(matrix[["strategy", "symbol", "segment", "trades", "win_rate", "profit_factor",
                     "expectancy_r", "total_return_pct", "max_drawdown_pct", "sharpe",
                     "trades_per_day"]]),
        "",
        "## What costs do before any strategy runs",
        "",
        _cost_section(cfg, data),
        "## How to read this",
        "",
        "- **Profit factor** below 1.0 loses money. Below ~1.2 it will not survive a "
        "regime change or a fee increase.",
        "- **Expectancy in R** is the average outcome per unit risked. At 0.5% risk per "
        "trade, an expectancy of 0.1R is 0.05% of equity per trade before compounding.",
        "- The gap between in-sample and out-of-sample is the honesty check. A strategy "
        "that halves out-of-sample was fitted, not discovered.",
        "- **Fees as % of gross** above roughly 30% means the edge is being eaten by "
        "trading costs; widen the targets or trade less.",
        "- **fee_r** is fees per unit of risk. At 0.30 every trade starts 30% of a stop "
        "in the hole, and the strategy has to win that back before it wins anything.",
        "",
    ]

    for (strategy_name, symbol), result in sorted(results.items()):
        breakdown = exit_breakdown(result)
        if breakdown.empty:
            continue
        lines += [f"### Exits: {strategy_name} on {symbol}", "",
                  _md(breakdown, index=True), ""]

    path = out_dir / "report.md"
    path.write_text("\n".join(lines))

    matrix.to_csv(out_dir / "metrics.csv", index=False)
    frames = [trades_frame(r).assign(strategy=k[0]) for k, r in results.items() if r.trades]
    if frames:
        pd.concat(frames).to_csv(out_dir / "trades.csv", index=False)
    return path


def _cost_section(cfg: Config, data: dict[str, pd.DataFrame] | None) -> str:
    """The arithmetic that decides which stop distances are worth testing."""
    if not data:
        return "_(no candle data supplied for the cost analysis)_\n"
    table = costs.summarise(data, cfg)
    lines = [_md(table), ""]
    for name, params in cfg.strategies.items():
        mult = params.get("stop_atr_mult")
        if mult is None:
            continue
        first = table[table["symbol"] == table["symbol"].iloc[0]]
        lines.append(f"- **{name}**: {costs.verdict(first, float(mult))}")
    lines.append("")
    lines.append("A stop measured in ATR is only as good as its size relative to the "
                 "spread and the fee. On 5m bars those are the same order of magnitude, "
                 "which is why intraday stops that look 'tight and disciplined' are "
                 "often just an expensive way to pay the exchange.")
    lines.append("")
    return "\n".join(lines)
