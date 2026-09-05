"""Von der Rangliste zu Zielgewichten und daraus zu Orders."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import SelectionConfig


@dataclass(frozen=True)
class Order:
    """Eine geplante Order. Positive Menge kauft, negative verkauft."""

    ticker: str
    side: str
    quantity: float
    reference_price: float

    @property
    def notional(self) -> float:
        return abs(self.quantity) * self.reference_price


def select_holdings(
    ranking: pd.DataFrame,
    eligible: set[str],
    current: set[str],
    cfg: SelectionConfig,
) -> list[str]:
    """Waehlt die Zieltitel mit Bestandsschutz.

    Ein gehaltener Titel bleibt drin, solange er unter ``buffer_rank`` steht.
    Erst wenn er darunter faellt, macht er Platz fuer den besten Kandidaten,
    der noch nicht im Depot ist. Das spart Turnover, ohne das Signal zu
    verwaessern.
    """
    ordered = [t for t in ranking.index if t in eligible and pd.notna(ranking.at[t, "score"])]
    if not ordered:
        return []

    rank_of = {ticker: i + 1 for i, ticker in enumerate(ordered)}
    top_n = ordered[: cfg.top_n]

    keepers = [
        t for t in ordered if t in current and rank_of[t] <= cfg.buffer_rank
    ][: cfg.top_n]

    selected = list(keepers)
    for ticker in top_n:
        if len(selected) >= cfg.top_n:
            break
        if ticker not in selected:
            selected.append(ticker)

    # Falls der Bestandsschutz noch Plaetze offen laesst, mit den naechstbesten
    # Kandidaten auffuellen.
    for ticker in ordered:
        if len(selected) >= cfg.top_n:
            break
        if ticker not in selected:
            selected.append(ticker)

    return sorted(selected, key=lambda t: rank_of[t])


def compute_weights(
    selected: list[str],
    ranking: pd.DataFrame,
    cfg: SelectionConfig,
    max_position_weight: float,
) -> dict[str, float]:
    """Gewichtet die Auswahl und haelt dabei das Einzelpositionslimit ein."""
    if not selected:
        return {}

    if cfg.weighting == "equal":
        raw = pd.Series(1.0, index=selected, dtype="float64")
    else:
        vol = ranking.loc[selected, "volatility"].astype("float64")
        # Fehlende Vol bekommt den Median, damit ein Titel nicht durch eine
        # Datenluecke ein Uebergewicht erbt.
        vol = vol.replace(0.0, np.nan)
        vol = vol.fillna(vol.median() if vol.notna().any() else 1.0)
        raw = 1.0 / vol

    weights = raw / raw.sum()

    # Kappen und den abgeschnittenen Teil auf die noch nicht gekappten
    # Positionen verteilen, bis alles unter dem Limit liegt.
    for _ in range(len(selected) + 1):
        over = weights > max_position_weight + 1e-12
        if not over.any():
            break
        excess = float((weights[over] - max_position_weight).sum())
        weights[over] = max_position_weight
        free = ~over
        if not free.any():
            break
        headroom = (max_position_weight - weights[free]).clip(lower=0)
        if headroom.sum() <= 1e-12:
            break
        weights[free] = weights[free] + headroom / headroom.sum() * excess

    total = float(weights.sum())
    if total > 1.0 + 1e-9:
        weights = weights / total
    return {t: float(w) for t, w in weights.items()}


def apply_exposure(weights: dict[str, float], exposure: float) -> dict[str, float]:
    """Skaliert die Zielgewichte auf die erlaubte Gesamtexposure."""
    total = sum(weights.values())
    if total <= 0 or exposure <= 0:
        return {}
    # Die Gewichte summieren sich bereits auf <= 1; hier werden sie auf genau
    # ``exposure`` normiert, damit Vol-Targeting und Regime-Filter durchgreifen.
    scale = exposure / total
    return {t: w * scale for t, w in weights.items()}


def turnover(current: dict[str, float], target: dict[str, float]) -> float:
    """Einseitiger Turnover als Summe der Gewichtsaenderungen / 2."""
    tickers = set(current) | set(target)
    return sum(abs(target.get(t, 0.0) - current.get(t, 0.0)) for t in tickers) / 2.0


def limit_turnover(
    current: dict[str, float], target: dict[str, float], cap: float
) -> tuple[dict[str, float], float]:
    """Zieht die Zielgewichte in Richtung Bestand, bis der Turnover passt.

    Gibt die gedaempften Gewichte und den angewandten Interpolationsfaktor
    zurueck. Faktor 1.0 heisst: das Limit war nicht bindend.
    """
    if cap <= 0:
        return target, 1.0

    raw = turnover(current, target)
    if raw <= cap or raw == 0:
        return target, 1.0

    alpha = cap / raw
    tickers = set(current) | set(target)
    blended = {}
    for t in tickers:
        cur = current.get(t, 0.0)
        tgt = target.get(t, 0.0)
        w = cur + alpha * (tgt - cur)
        if abs(w) > 1e-9:
            blended[t] = w
    return blended, alpha


def weights_from_positions(
    positions: dict[str, float], prices: pd.Series, equity: float
) -> dict[str, float]:
    """Rechnet gehaltene Stueckzahlen in Portfoliogewichte um."""
    if equity <= 0:
        return {}
    weights = {}
    for ticker, shares in positions.items():
        price = float(prices.get(ticker, np.nan))
        if shares and np.isfinite(price):
            weights[ticker] = shares * price / equity
    return weights


def build_orders(
    current_positions: dict[str, float],
    target_weights: dict[str, float],
    prices: pd.Series,
    equity: float,
    *,
    min_order_notional: float,
    allow_fractional: bool = False,
) -> list[Order]:
    """Bildet die Differenz zwischen Bestand und Ziel auf Orders ab.

    Verkaeufe kommen zuerst, damit die Liquiditaet fuer die Kaeufe da ist.
    Orders unterhalb ``min_order_notional`` entfallen -- sie kosten mehr
    Gebuehren und Spread als sie an Praezision bringen.
    """
    tickers = set(current_positions) | set(target_weights)
    orders: list[Order] = []

    for ticker in sorted(tickers):
        price = float(prices.get(ticker, np.nan))
        if not np.isfinite(price) or price <= 0:
            continue

        held = float(current_positions.get(ticker, 0.0))
        target_value = target_weights.get(ticker, 0.0) * equity
        target_shares = target_value / price
        if not allow_fractional:
            target_shares = math.floor(target_shares) if target_shares > 0 else 0.0

        delta = target_shares - held
        if abs(delta) * price < min_order_notional:
            continue
        if abs(delta) < (1e-9 if allow_fractional else 1.0):
            continue

        orders.append(
            Order(
                ticker=ticker,
                side="buy" if delta > 0 else "sell",
                quantity=delta,
                reference_price=price,
            )
        )

    orders.sort(key=lambda o: (o.side != "sell", o.ticker))
    return orders
