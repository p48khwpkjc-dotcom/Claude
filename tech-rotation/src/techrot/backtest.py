"""Backtest des monatlichen Rebalancings.

Der Backtest ruft dieselben Funktionen auf wie der Live-Lauf: Ranking,
Eignungspruefung, Exposure-Entscheidung, Ordergenerierung, Paper-Fills. Was
hier getestet wird, ist also der Code, der spaeter auch handelt.

Lookahead-Schutz: das Signal entsteht am Handelstag ``d`` aus Kursen bis
einschliesslich ``d``, gehandelt wird zum Schlusskurs von ``d+1``.

Survivorship-Schutz: mit ``universe_at`` bestimmt eine Funktion das Universum
an jedem Signaltag -- etwa die damalige Indexzusammensetzung. Titel, deren
Kursreihe endet (Uebernahme, Delisting), werden am ersten Tag danach zum
letzten Kurs in Cash umgewandelt. Ohne diesen Schritt bewertete das Depot sie
mit null: ein fiktiver Totalverlust, genau wie am 22. September im Live-Lauf.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

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
    # Zwangsweise in Cash umgewandelte Positionen, deren Kursreihe endete.
    delistings: pd.DataFrame = field(default_factory=pd.DataFrame)


def fill_inner_gaps(close: pd.DataFrame) -> pd.DataFrame:
    """Schliesst Luecken innerhalb einer Kursreihe, nie ueber ihr Ende hinaus.

    Ein fehlender Tag mitten in der Historie wuerde einen gehaltenen Titel an
    diesem Tag mit null bewerten. Nach dem letzten echten Kurs bleibt die Reihe
    dagegen leer: dort ist der Titel nicht mehr handelbar, und die
    Aktualitaetspruefung soll das sehen.
    """
    last_valid = close.apply(lambda s: s.last_valid_index())
    ende = pd.to_datetime(last_valid.reindex(close.columns)).to_numpy(dtype="datetime64[ns]")
    nach_ende = close.index.to_numpy(dtype="datetime64[ns]")[:, None] > ende[None, :]
    return close.ffill().mask(pd.DataFrame(nach_ende, index=close.index, columns=close.columns))


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


def run_backtest(
    cfg: Config,
    prices: PriceData,
    *,
    universe_at: Callable[[pd.Timestamp], Sequence[str]] | None = None,
    cash_return: pd.Series | None = None,
) -> BacktestResult:
    """Simuliert die Strategie ueber den konfigurierten Zeitraum.

    ``universe_at`` liefert zu einem Signaltag die Ticker, aus denen der Plan
    waehlen darf. Ohne sie gilt die Liste aus der Konfiguration -- fuer jeden
    Tag dieselbe, und damit mit dem Wissen von heute ausgewaehlt.

    ``cash_return`` ist die Tagesrendite, die nicht investiertes Geld
    verdient (etwa aus einem T-Bill-ETF). Ohne sie liegt Cash zinslos -- das
    benachteiligt eine Strategie, die oft zur Haelfte in Cash steht,
    gegenueber einer, die immer voll investiert ist.
    """
    tageszins = (
        cash_return.reindex(prices.close.index).fillna(0.0)
        if cash_return is not None
        else None
    )
    raw_close = prices.close
    close = fill_inner_gaps(raw_close)
    last_valid = raw_close.apply(lambda s: s.last_valid_index())
    # Planung auf den geglaetteten Reihen: ein einzelner fehlender Tag soll
    # weder den Depotwert noch die Gewichte verfaelschen.
    planning = PriceData(close=close, volume=prices.volume)
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
    delisting_rows: list[dict[str, object]] = []

    schedule_set = set(schedule)
    pending: dict[str, float] | None = None  # am Vortag beschlossene Zielgewichte

    for position, day in enumerate(sim_dates):
        day_prices = close.loc[day]

        # Zinsen auf das Cash, das ueber Nacht lag -- vor allem anderen, denn
        # sie gehoeren zum Vortagesbestand.
        if tageszins is not None and position > 0:
            state.cash *= 1.0 + float(tageszins.loc[day])

        # (0) Endete die Kursreihe eines gehaltenen Titels, wird er zum letzten
        #     Kurs zu Cash. Bei einer Uebernahme ist das ziemlich genau der
        #     Abfindungspreis; ohne Kosten, weil nicht am Markt gehandelt wird.
        for ticker in list(state.positions):
            ende = last_valid.get(ticker)
            if ende is None or pd.isna(ende) or day <= ende:
                continue
            shares = state.positions.pop(ticker)
            price = float(raw_close.at[ende, ticker])
            state.cash += shares * price
            delisting_rows.append(
                {
                    "date": day,
                    "ticker": ticker,
                    "shares": shares,
                    "last_date": ende,
                    "price": price,
                    "value": shares * price,
                }
            )

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
            universe = list(universe_at(day)) if universe_at is not None else None
            plan = plan_rebalance(
                cfg, planning, state, asof=day, force=True, universe=universe
            )
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
                    "n_universe": len(universe) if universe is not None else len(cfg.tickers),
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

    delisting_frame = pd.DataFrame(delisting_rows)
    metrics["n_delistings"] = float(len(delisting_frame))

    return BacktestResult(
        equity=equity_series,
        benchmark=benchmark_series,
        trades=trades_frame,
        rebalances=rebalance_frame,
        metrics=metrics,
        benchmark_metrics=benchmark_metrics,
        delistings=delisting_frame,
    )
