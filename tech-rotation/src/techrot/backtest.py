"""Backtest des monatlichen Rebalancings.

Der Backtest ruft dieselben Funktionen auf wie der Live-Lauf: Ranking,
Eignungspruefung, Exposure-Entscheidung, Ordergenerierung, Paper-Fills. Was
hier getestet wird, ist also der Code, der spaeter auch handelt.

Lookahead-Schutz: das Signal entsteht am Handelstag ``d`` aus Kursen bis
einschliesslich ``d``, gehandelt wird zum Schlusskurs von ``d+1``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .brokers import PaperBroker
from .config import Config
from .data import PriceData
from .execution import plan_rebalance
from .portfolio import build_orders, turnover, weights_from_positions
from .ranking import TRADING_DAYS_PER_YEAR
from .state import EquityPoint, PortfolioState


@dataclass(frozen=True)
class BacktestResult:
    equity: pd.Series
    benchmark: pd.Series | None
    trades: pd.DataFrame
    rebalances: pd.DataFrame
    metrics: dict[str, float]
    benchmark_metrics: dict[str, float] | None


def rebalance_dates(index: pd.DatetimeIndex, mode: str) -> list[pd.Timestamp]:
    """Erster bzw. letzter Handelstag jedes Monats im Kursindex."""
    frame = pd.Series(index, index=index)
    grouped = frame.groupby([index.year, index.month])
    picked = grouped.first() if mode == "month_start" else grouped.last()
    return sorted(pd.Timestamp(d) for d in picked.to_list())


def performance_metrics(equity: pd.Series) -> dict[str, float]:
    """Kennzahlen einer Equity-Kurve mit taeglicher Frequenz."""
    equity = equity.dropna()
    if len(equity) < 2 or float(equity.iloc[0]) <= 0:
        return {}

    returns = equity.pct_change(fill_method=None).dropna()
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    total_return = float(equity.iloc[-1] / equity.iloc[0]) - 1.0
    cagr = (1.0 + total_return) ** (1.0 / years) - 1.0 if years > 0 else float("nan")

    vol = float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)) if len(returns) > 1 else 0.0
    mean_ann = float(returns.mean() * TRADING_DAYS_PER_YEAR)
    sharpe = mean_ann / vol if vol > 0 else float("nan")

    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    max_dd = float(drawdown.min())

    downside = returns[returns < 0]
    downside_vol = (
        float(downside.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)) if len(downside) > 1 else 0.0
    )

    return {
        "total_return": total_return,
        "cagr": cagr,
        "volatility": vol,
        "sharpe": sharpe,
        "sortino": mean_ann / downside_vol if downside_vol > 0 else float("nan"),
        "max_drawdown": max_dd,
        "calmar": cagr / abs(max_dd) if max_dd < 0 else float("nan"),
        "best_day": float(returns.max()) if len(returns) else float("nan"),
        "worst_day": float(returns.min()) if len(returns) else float("nan"),
        "positive_days": float((returns > 0).mean()) if len(returns) else float("nan"),
        "years": years,
    }


def run_backtest(cfg: Config, prices: PriceData) -> BacktestResult:
    """Simuliert die Strategie ueber den konfigurierten Zeitraum."""
    close = prices.close
    start = pd.Timestamp(cfg.backtest.start)
    end = pd.Timestamp(cfg.backtest.end) if cfg.backtest.end else close.index[-1]

    all_dates = close.index
    schedule = [d for d in rebalance_dates(all_dates, cfg.backtest.rebalance) if start <= d <= end]
    if not schedule:
        raise ValueError(
            f"Kein Rebalancing-Termin zwischen {start.date()} und {end.date()} gefunden"
        )

    # Vorlauf: erst rebalancieren, wenn genug Historie fuer die Signale da ist.
    warmup = cfg.data.min_history_days
    schedule = [d for d in schedule if int(all_dates.get_indexer([d])[0]) >= warmup]
    if not schedule:
        raise ValueError(
            f"Zu wenig Historie: {len(all_dates)} Tage reichen nicht fuer "
            f"{warmup} Tage Vorlauf plus mindestens einen Rebalancing-Termin"
        )

    state = PortfolioState(cash=cfg.execution.starting_cash)
    broker = PaperBroker(state, cfg.execution)

    sim_start = schedule[0]
    sim_dates = all_dates[(all_dates >= sim_start) & (all_dates <= end)]

    equity_points: list[EquityPoint] = []
    equity_values: list[float] = []
    trades: list[dict[str, object]] = []
    rebalance_rows: list[dict[str, object]] = []

    schedule_set = set(schedule)
    pending: dict[str, float] | None = None  # am Vortag beschlossene Zielgewichte

    for position, day in enumerate(sim_dates):
        day_prices = close.loc[day]

        # (a) Zuerst handeln, was am Vortag beschlossen wurde.
        if pending is not None:
            equity_before = state.equity(day_prices)
            before_weights = weights_from_positions(state.positions, day_prices, equity_before)
            orders = build_orders(
                state.positions,
                pending,
                day_prices,
                equity_before,
                min_order_notional=cfg.execution.min_order_notional,
            )
            for order in orders:
                fill = broker.submit(order)
                trades.append(
                    {
                        "date": day,
                        "ticker": fill.ticker,
                        "side": fill.side,
                        "quantity": fill.quantity,
                        "price": fill.price,
                        "notional": fill.notional,
                        "cost": fill.cost,
                    }
                )
            after_weights = weights_from_positions(
                state.positions, day_prices, state.equity(day_prices)
            )
            if rebalance_rows:
                rebalance_rows[-1]["trade_date"] = day
                rebalance_rows[-1]["realized_turnover"] = turnover(before_weights, after_weights)
                rebalance_rows[-1]["n_orders"] = len(orders)
            state.last_rebalance = str(day.date())
            pending = None

        # (b) Tagesbewertung fuer Equity-Kurve und Drawdown-Bremse.
        equity = state.equity(day_prices)
        equity_points.append(EquityPoint(date=day.date().isoformat(), equity=equity))
        equity_values.append(equity)
        state.equity_history = equity_points  # direkt zuweisen: O(1) statt O(n)

        # (c) Signal am Rebalancing-Tag, Ausfuehrung am naechsten Handelstag.
        if day in schedule_set and position + 1 < len(sim_dates):
            plan = plan_rebalance(cfg, prices, state, asof=day, force=True)
            pending = plan.target_weights
            rebalance_rows.append(
                {
                    "signal_date": day,
                    "trade_date": pd.NaT,
                    "equity": equity,
                    "n_selected": len(plan.selected),
                    "selected": ",".join(plan.selected),
                    "exposure": plan.exposure.exposure,
                    "regime_ok": plan.exposure.regime_ok,
                    "vol_scalar": plan.exposure.vol_scalar,
                    "drawdown_scalar": plan.exposure.drawdown_scalar,
                    "planned_turnover": plan.turnover,
                    "realized_turnover": float("nan"),
                    "n_orders": 0,
                    "n_eligible": len(plan.eligible_tickers),
                }
            )

    equity_series = pd.Series(equity_values, index=sim_dates, dtype="float64")

    benchmark_series = None
    benchmark_metrics = None
    if cfg.benchmark in close.columns:
        bench = close[cfg.benchmark].reindex(sim_dates).ffill().dropna()
        if len(bench) > 1 and float(bench.iloc[0]) > 0:
            benchmark_series = bench / float(bench.iloc[0]) * cfg.execution.starting_cash
            benchmark_metrics = performance_metrics(benchmark_series)

    metrics = performance_metrics(equity_series)
    trades_frame = pd.DataFrame(trades)
    rebalance_frame = pd.DataFrame(rebalance_rows)

    if not trades_frame.empty:
        metrics["total_costs"] = float(trades_frame["cost"].sum())
        metrics["n_trades"] = float(len(trades_frame))
    if not rebalance_frame.empty:
        metrics["avg_turnover"] = float(rebalance_frame["realized_turnover"].mean(skipna=True))
        metrics["avg_exposure"] = float(rebalance_frame["exposure"].mean())
        metrics["n_rebalances"] = float(len(rebalance_frame))

    return BacktestResult(
        equity=equity_series,
        benchmark=benchmark_series,
        trades=trades_frame,
        rebalances=rebalance_frame,
        metrics=metrics,
        benchmark_metrics=benchmark_metrics,
    )
