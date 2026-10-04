"""Vollstaendiger Lauf als JSON -- Datengrundlage fuer die interaktive Ansicht.

Der Textreport zeigt die Top 15; diese Datei zeigt alles. Fuer jeden Ticker
des Universums steht hier, wie er bewertet wurde: Rohkennzahlen, die
querschnittlichen z-Scores, der Beitrag jedes Signals zum Gesamtscore, das
Urteil der Eignungspruefung samt Begruendung und was am Ende daraus wurde.

Damit laesst sich die Entscheidung des Laufs nachvollziehen, ohne den Code
zu lesen -- und die Datei bleibt stabil genug, um sie zu versionieren und
zwei Laeufe zu vergleichen.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .config import Config
from .execution import RebalancePlan
from .state import PortfolioState

SCHEMA_VERSION = 1


def _num(value: Any) -> float | None:
    """Zahl fuer JSON: NaN und Inf werden zu ``null``.

    ``json.dumps`` schreibt sonst ``NaN``, was kein gueltiges JSON ist und
    von ``JSON.parse`` im Browser abgelehnt wird.
    """
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _row(frame: pd.DataFrame, ticker: str, column: str) -> float | None:
    if column not in frame.columns or ticker not in frame.index:
        return None
    return _num(frame.at[ticker, column])


def plan_to_dict(
    cfg: Config,
    plan: RebalancePlan,
    state: PortfolioState,
    *,
    executed: bool = False,
) -> dict[str, Any]:
    """Baut die vollstaendige Beschreibung eines Laufs als JSON-faehiges Dict."""
    ranking = plan.ranking
    weights = cfg.ranking.normalized_weights()
    signals = [s for s in weights if f"z_{s}" in ranking.columns]
    metric_names = [*cfg.ranking.lookbacks, "risk_adj_mom", "volatility", "price"]

    tickers: list[dict[str, Any]] = []
    for ticker in cfg.tickers:
        eligibility = plan.eligibility.get(ticker)
        quality = plan.quality.get(ticker)
        in_ranking = ticker in ranking.index

        beitraege = {}
        for signal in signals:
            z = _row(ranking, ticker, f"z_{signal}")
            beitraege[signal] = {
                "z": z,
                "weight": _num(weights[signal]),
                # Was dieses Signal zum Gesamtscore beigetragen hat. Die Summe
                # ueber alle Signale ist der Score -- so wird sichtbar, welche
                # Kennzahl einen Titel nach oben getragen hat.
                "contribution": None if z is None else _num(z * weights[signal]),
            }

        tickers.append(
            {
                "ticker": ticker,
                "rank": int(ranking.at[ticker, "rank"]) if in_ranking else None,
                "score": _row(ranking, ticker, "score"),
                "metrics": {name: _row(ranking, ticker, name) for name in metric_names},
                "signals": beitraege,
                "eligible": bool(eligibility.eligible) if eligibility else False,
                "reasons": list(eligibility.reasons) if eligibility else ["nicht geprueft"],
                "data_ok": bool(quality.ok) if quality else None,
                "data_reason": (None if quality is None or quality.ok else quality.reason),
                "selected": ticker in plan.selected,
                "current_weight": _num(plan.current_weights.get(ticker, 0.0)),
                "target_weight": _num(plan.target_weights.get(ticker, 0.0)),
                "shares": _num(state.positions.get(ticker, 0.0)),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "strategy": cfg.name,
        "signal_date": str(plan.asof.date()),
        "benchmark": cfg.benchmark,
        "executed": bool(executed),
        "due": bool(plan.due),
        "portfolio": {
            "equity": _num(plan.equity),
            "cash": _num(state.cash),
            "cash_weight": _num(plan.cash_weight),
            "last_rebalance": state.last_rebalance,
            "invested_weight": _num(sum(plan.target_weights.values())),
        },
        "exposure": {
            "exposure": _num(plan.exposure.exposure),
            "regime_ok": plan.exposure.regime_ok,
            "vol_scalar": _num(plan.exposure.vol_scalar),
            "drawdown_scalar": _num(plan.exposure.drawdown_scalar),
            "realized_vol": _num(plan.exposure.realized_vol),
            "current_drawdown": _num(plan.exposure.current_drawdown),
        },
        "turnover": {
            "planned": _num(plan.turnover),
            "alpha": _num(plan.turnover_alpha),
            "limit": _num(cfg.risk.portfolio.max_turnover_per_rebalance),
        },
        "rules": {
            "top_n": cfg.selection.top_n,
            "buffer_rank": cfg.selection.buffer_rank,
            "weighting": cfg.selection.weighting,
            "max_position_weight": _num(cfg.risk.portfolio.max_position_weight),
            "vol_target": _num(cfg.risk.portfolio.vol_target),
            "max_annual_vol": _num(cfg.risk.eligibility.max_annual_vol),
            "min_avg_dollar_volume": _num(cfg.risk.eligibility.min_avg_dollar_volume),
            "require_above_sma": cfg.risk.eligibility.require_above_sma,
            "regime_sma": cfg.risk.portfolio.regime_sma,
            "signal_weights": {k: _num(v) for k, v in weights.items()},
        },
        "notes": list(plan.notes),
        "orders": [
            {
                "ticker": o.ticker,
                "side": o.side,
                "quantity": _num(o.quantity),
                "price": _num(o.reference_price),
                "notional": _num(o.notional),
            }
            for o in plan.orders
        ],
        "equity_history": [
            {"date": p.date, "equity": _num(p.equity)} for p in state.equity_history
        ],
        "tickers": tickers,
    }


def write_plan_json(
    path: Path,
    cfg: Config,
    plan: RebalancePlan,
    state: PortfolioState,
    *,
    executed: bool = False,
) -> None:
    """Schreibt die Laufbeschreibung; stabil sortiert fuer lesbare Diffs."""
    payload = plan_to_dict(cfg, plan, state, executed=executed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
