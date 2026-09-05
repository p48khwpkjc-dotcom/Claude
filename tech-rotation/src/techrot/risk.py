"""Risikopruefung auf zwei Ebenen.

1. Eignung je Titel  -- wer darf ueberhaupt ins Ranking?
2. Portfolio-Exposure -- wie viel Kapital darf insgesamt investiert sein?

Jede Pruefung liefert eine begruendete Entscheidung, damit der Report zeigt,
warum ein Titel fehlt oder warum die Exposure gedrosselt wurde.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import EligibilityConfig, PortfolioRiskConfig
from .data import DataQuality, PriceData
from .ranking import TRADING_DAYS_PER_YEAR, moving_average


@dataclass(frozen=True)
class Eligibility:
    """Ergebnis der Eignungspruefung fuer einen Titel."""

    ticker: str
    eligible: bool
    reasons: tuple[str, ...] = ()

    @property
    def reason_text(self) -> str:
        return "ok" if self.eligible else "; ".join(self.reasons)


@dataclass(frozen=True)
class ExposureDecision:
    """Ergebnis der Portfolio-Risikopruefung."""

    exposure: float
    regime_ok: bool
    vol_scalar: float
    drawdown_scalar: float
    realized_vol: float | None
    current_drawdown: float
    notes: tuple[str, ...] = field(default_factory=tuple)


def check_eligibility(
    prices: PriceData,
    metrics: pd.DataFrame,
    quality: dict[str, DataQuality],
    cfg: EligibilityConfig,
) -> dict[str, Eligibility]:
    """Filtert das Universum auf handelbare, trendkonforme Titel."""
    adv = prices.dollar_volume(cfg.adv_window)
    sma = (
        moving_average(prices.close, cfg.require_above_sma)
        if cfg.require_above_sma > 0
        else None
    )

    results: dict[str, Eligibility] = {}
    for ticker in metrics.index:
        reasons: list[str] = []

        q = quality.get(ticker)
        if q is not None and not q.ok:
            reasons.append(f"Datenqualitaet: {q.reason}")

        adv_value = float(adv.get(ticker, np.nan))
        if not np.isfinite(adv_value):
            reasons.append("kein Handelsvolumen verfuegbar")
        elif adv_value < cfg.min_avg_dollar_volume:
            reasons.append(
                f"Liquiditaet {adv_value / 1e6:.0f} Mio USD unter "
                f"{cfg.min_avg_dollar_volume / 1e6:.0f} Mio"
            )

        vol = float(metrics.at[ticker, "volatility"]) if "volatility" in metrics else np.nan
        if not np.isfinite(vol):
            reasons.append("Volatilitaet nicht berechenbar")
        elif vol > cfg.max_annual_vol:
            reasons.append(f"Volatilitaet {vol:.0%} ueber Limit {cfg.max_annual_vol:.0%}")

        if cfg.require_positive_absolute_momentum:
            mom = float(metrics.at[ticker, "mom_12_1"]) if "mom_12_1" in metrics else np.nan
            if not np.isfinite(mom):
                reasons.append("12-1-Momentum nicht berechenbar")
            elif mom <= 0:
                reasons.append(f"absolutes Momentum negativ ({mom:.1%})")

        if sma is not None:
            price = float(metrics.at[ticker, "price"]) if "price" in metrics else np.nan
            sma_value = float(sma.get(ticker, np.nan))
            if not np.isfinite(price) or not np.isfinite(sma_value):
                reasons.append(f"SMA{cfg.require_above_sma} nicht berechenbar")
            elif price <= sma_value:
                reasons.append(f"Kurs unter SMA{cfg.require_above_sma}")

        results[ticker] = Eligibility(ticker, not reasons, tuple(reasons))
    return results


def _portfolio_volatility(
    prices: PriceData, weights: dict[str, float], lookback: int
) -> float | None:
    """Annualisierte Vol des gewichteten Korbs auf Basis der Kovarianz."""
    held = {t: w for t, w in weights.items() if w > 0 and t in prices.close.columns}
    if not held:
        return None

    returns = prices.close[list(held)].pct_change(fill_method=None).tail(lookback).dropna(how="all")
    if len(returns) < max(20, lookback // 3):
        return None

    w = np.array([held[t] for t in returns.columns], dtype="float64")
    total = w.sum()
    if total <= 0:
        return None
    w = w / total

    cov = returns.cov().to_numpy() * TRADING_DAYS_PER_YEAR
    if not np.all(np.isfinite(cov)):
        return None

    variance = float(w @ cov @ w)
    return float(np.sqrt(variance)) if variance > 0 else None


def regime_ok(prices: PriceData, benchmark: str, sma_window: int) -> bool | None:
    """Liegt der Benchmark ueber seiner gleitenden Durchschnittslinie?

    ``None`` heisst: nicht entscheidbar (Filter aus oder Daten fehlen).
    """
    if sma_window <= 0 or benchmark not in prices.close.columns:
        return None
    series = prices.close[benchmark].dropna()
    if len(series) < sma_window:
        return None
    return bool(series.iloc[-1] > series.tail(sma_window).mean())


def current_drawdown(equity_curve: pd.Series | None) -> float:
    """Aktueller Rueckgang vom bisherigen Hoechststand, als positive Zahl."""
    if equity_curve is None or len(equity_curve) < 2:
        return 0.0
    peak = float(equity_curve.max())
    if peak <= 0:
        return 0.0
    return max(0.0, 1.0 - float(equity_curve.iloc[-1]) / peak)


def decide_exposure(
    prices: PriceData,
    candidate_weights: dict[str, float],
    cfg: PortfolioRiskConfig,
    benchmark: str,
    equity_curve: pd.Series | None = None,
) -> ExposureDecision:
    """Bestimmt, welcher Anteil des Kapitals investiert werden darf."""
    notes: list[str] = []
    exposure = cfg.max_gross_exposure

    regime = regime_ok(prices, benchmark, cfg.regime_sma)
    if regime is False:
        exposure = min(exposure, cfg.regime_exposure)
        notes.append(
            f"Regime-Filter aktiv: {benchmark} unter SMA{cfg.regime_sma}, "
            f"Exposure auf {cfg.regime_exposure:.0%} gekappt"
        )
    elif regime is None and cfg.regime_sma > 0:
        notes.append(f"Regime-Filter uebersprungen: keine {benchmark}-Historie")

    n_names = sum(1 for w in candidate_weights.values() if w > 0)
    if n_names == 0:
        notes.append("kein Titel besteht die Eignungspruefung")
        return ExposureDecision(0.0, regime is not False, 1.0, 1.0, None, 0.0, tuple(notes))

    if n_names < cfg.min_names:
        # Nicht auf null gehen, sondern proportional drosseln: bei 2 von 4
        # geforderten Titeln nur die halbe Exposure.
        scale = n_names / cfg.min_names
        exposure *= scale
        notes.append(
            f"nur {n_names} von {cfg.min_names} geforderten Titeln, "
            f"Exposure auf {scale:.0%} gedrosselt"
        )

    realized_vol = _portfolio_volatility(prices, candidate_weights, cfg.vol_lookback)
    vol_scalar = 1.0
    if cfg.vol_target > 0 and realized_vol and realized_vol > 0:
        vol_scalar = min(cfg.max_vol_scalar, cfg.vol_target / realized_vol)
        if vol_scalar < 1.0:
            notes.append(
                f"Vol-Targeting: erwartete Portfoliovol {realized_vol:.1%} ueber Ziel "
                f"{cfg.vol_target:.1%}, Skalierung {vol_scalar:.2f}"
            )
    elif cfg.vol_target > 0:
        notes.append("Vol-Targeting uebersprungen: Portfoliovol nicht schaetzbar")

    dd = current_drawdown(equity_curve)
    dd_scalar = 1.0
    if cfg.max_drawdown_brake > 0 and dd > cfg.max_drawdown_brake:
        # Linear vom vollen Einsatz an der Schwelle bis zum Boden bei doppelter
        # Schwelle. Bremsen statt abschalten, damit die Erholung mitgenommen wird.
        span = cfg.max_drawdown_brake
        overshoot = min(1.0, (dd - span) / span)
        dd_scalar = 1.0 - overshoot * (1.0 - cfg.drawdown_exposure_floor)
        notes.append(
            f"Drawdown-Bremse: aktueller Rueckgang {dd:.1%} ueber Limit "
            f"{cfg.max_drawdown_brake:.1%}, Skalierung {dd_scalar:.2f}"
        )

    exposure = max(0.0, min(exposure * vol_scalar * dd_scalar, cfg.max_gross_exposure))
    return ExposureDecision(
        exposure=exposure,
        regime_ok=regime is not False,
        vol_scalar=vol_scalar,
        drawdown_scalar=dd_scalar,
        realized_vol=realized_vol,
        current_drawdown=dd,
        notes=tuple(notes),
    )
