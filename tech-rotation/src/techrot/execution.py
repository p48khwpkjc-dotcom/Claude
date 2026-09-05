"""Der Rebalancing-Lauf: Daten -> Ranking -> Risiko -> Orders -> Ausfuehrung.

``plan_rebalance`` ist frei von Seiteneffekten und liefert einen vollstaendig
begruendeten Plan. Erst ``execute_plan`` schickt Orders los und schreibt den
Zustand fort. Diese Trennung macht den Dry-Run zur echten Vorschau: er
durchlaeuft exakt dieselbe Logik.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from .brokers import Broker, Fill
from .config import Config
from .data import DataQuality, PriceData, check_data_quality
from .portfolio import (
    Order,
    apply_exposure,
    build_orders,
    compute_weights,
    limit_turnover,
    select_holdings,
    turnover,
    weights_from_positions,
)
from .ranking import rank_universe
from .risk import Eligibility, ExposureDecision, check_eligibility, decide_exposure
from .state import PortfolioState, is_rebalance_due


@dataclass(frozen=True)
class RebalancePlan:
    """Alles, was der Lauf entschieden hat, samt Begruendung."""

    asof: pd.Timestamp
    equity: float
    ranking: pd.DataFrame
    quality: dict[str, DataQuality]
    eligibility: dict[str, Eligibility]
    selected: list[str]
    current_weights: dict[str, float]
    target_weights: dict[str, float]
    exposure: ExposureDecision
    turnover: float
    turnover_alpha: float
    orders: list[Order]
    due: bool
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def eligible_tickers(self) -> list[str]:
        return [t for t, e in self.eligibility.items() if e.eligible]

    @property
    def blocked(self) -> dict[str, str]:
        return {t: e.reason_text for t, e in self.eligibility.items() if not e.eligible}

    @property
    def cash_weight(self) -> float:
        return max(0.0, 1.0 - sum(self.target_weights.values()))


def plan_rebalance(
    cfg: Config,
    prices: PriceData,
    state: PortfolioState,
    *,
    asof: pd.Timestamp | None = None,
    force: bool = False,
) -> RebalancePlan:
    """Berechnet den Zielzustand des Portfolios ohne etwas zu veraendern."""
    panel = prices if asof is None else prices.up_to(asof)
    if len(panel.close) == 0:
        raise ValueError("Keine Kursdaten bis zum Stichtag vorhanden")

    signal_date = panel.last_date
    last_prices = panel.close.iloc[-1]
    equity = state.equity(last_prices)
    notes: list[str] = []

    due = force or is_rebalance_due(state, signal_date.date())
    if not due:
        notes.append(
            f"Kein Rebalancing faellig: letzter Lauf {state.last_rebalance}, "
            "naechster im Folgemonat"
        )

    # 1. Datenqualitaet -- vor allem anderen, damit kaputte Reihen weder ins
    #    Ranking noch in den z-Score-Querschnitt gelangen.
    quality = check_data_quality(panel, list(cfg.tickers), cfg.data, signal_date)
    healthy = [t for t, q in quality.items() if q.ok]

    # 2. Kennzahlen und Eignung auf den gesunden Reihen.
    full_ranking = rank_universe(panel, cfg.ranking, eligible=healthy)
    eligibility = check_eligibility(panel, full_ranking, quality, cfg.risk.eligibility)
    for ticker, q in quality.items():
        if not q.ok and ticker not in eligibility:
            eligibility[ticker] = Eligibility(ticker, False, (f"Datenqualitaet: {q.reason}",))

    eligible = {t for t, e in eligibility.items() if e.eligible}

    # 3. Auswahl mit Bestandsschutz.
    current_positions = dict(state.positions)
    current_weights = weights_from_positions(current_positions, last_prices, equity)
    selected = select_holdings(full_ranking, eligible, set(current_positions), cfg.selection)

    # 4. Gewichte, dann Portfolio-Risiko auf genau diesen Korb.
    raw_weights = compute_weights(
        selected, full_ranking, cfg.selection, cfg.risk.portfolio.max_position_weight
    )
    exposure = decide_exposure(
        panel,
        raw_weights,
        cfg.risk.portfolio,
        cfg.benchmark,
        state.equity_curve(),
    )
    target_weights = apply_exposure(raw_weights, exposure.exposure)

    # 5. Turnover-Bremse.
    target_weights, alpha = limit_turnover(
        current_weights, target_weights, cfg.risk.portfolio.max_turnover_per_rebalance
    )
    if alpha < 1.0:
        notes.append(
            f"Turnover-Limit greift: Zielgewichte zu {alpha:.0%} in Richtung Ziel "
            f"bewegt (Limit {cfg.risk.portfolio.max_turnover_per_rebalance:.0%})"
        )

    orders = (
        build_orders(
            current_positions,
            target_weights,
            last_prices,
            equity,
            min_order_notional=cfg.execution.min_order_notional,
        )
        if due
        else []
    )

    return RebalancePlan(
        asof=signal_date,
        equity=equity,
        ranking=full_ranking,
        quality=quality,
        eligibility=eligibility,
        selected=selected,
        current_weights=current_weights,
        target_weights=target_weights,
        exposure=exposure,
        turnover=turnover(current_weights, target_weights),
        turnover_alpha=alpha,
        orders=orders,
        due=due,
        notes=tuple(notes) + exposure.notes,
    )


def _append_journal(path: Path, entry: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def execute_plan(
    cfg: Config,
    plan: RebalancePlan,
    state: PortfolioState,
    broker: Broker,
) -> list[Fill]:
    """Schickt die Orders an den Broker und schreibt Zustand und Journal fort.

    Schlaegt eine einzelne Order fehl, laufen die uebrigen weiter: ein
    halb ausgefuehrtes Rebalancing ist besser als ein abgebrochenes, bei dem
    Verkaeufe durch sind und die Kaeufe fehlen. Der Fehler landet im Journal.
    """
    if not plan.due:
        return []

    journal = cfg.path(cfg.execution.journal_file)
    run_id = datetime.now(timezone.utc).isoformat(timespec="seconds")
    fills: list[Fill] = []

    for order in plan.orders:
        try:
            fill = broker.submit(order)
        except Exception as exc:  # noqa: BLE001 -- jede Brokerstoerung protokollieren
            _append_journal(
                journal,
                {
                    "run_id": run_id,
                    "asof": str(plan.asof.date()),
                    "broker": broker.name,
                    "ticker": order.ticker,
                    "side": order.side,
                    "quantity": order.quantity,
                    "status": "error",
                    "error": str(exc),
                },
            )
            continue

        fills.append(fill)
        _append_journal(
            journal,
            {
                "run_id": run_id,
                "asof": str(plan.asof.date()),
                "broker": broker.name,
                "ticker": fill.ticker,
                "side": fill.side,
                "quantity": fill.quantity,
                "price": fill.price,
                "cost": fill.cost,
                "notional": fill.notional,
                "status": fill.status,
                "broker_order_id": fill.broker_order_id,
            },
        )

    # Nach dem Handel gilt der Kontostand des Brokers, nicht die lokale
    # Buchhaltung. Fuer den Paper-Broker ist das ein No-op.
    try:
        broker.sync(state)
    except Exception as exc:  # noqa: BLE001
        _append_journal(
            journal,
            {"run_id": run_id, "status": "account_sync_failed", "error": str(exc)},
        )

    state.last_rebalance = str(plan.asof.date())
    return fills


def mark_to_market(state: PortfolioState, prices: PriceData, on: date | None = None) -> float:
    """Bewertet das Depot zum letzten Kurs und haengt den Punkt an die Kurve."""
    last_prices = prices.close.iloc[-1]
    equity = state.equity(last_prices)
    state.record_equity(on or prices.last_date.date(), equity)
    return equity
