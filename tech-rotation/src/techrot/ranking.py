"""Momentum-Ranking des Universums.

Der Score ist eine gewichtete Summe querschnittlicher z-Scores mehrerer
Momentum-Horizonte. Alle Kennzahlen werden ausschliesslich aus Kursen bis
zum Signaldatum berechnet.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Lookback, RankingConfig
from .data import PriceData

TRADING_DAYS_PER_YEAR = 252


def horizon_return(close: pd.DataFrame, lookback: Lookback) -> pd.Series:
    """Rendite zwischen zwei Ruecklagen, gemessen vom Ende des Panels.

    ``Lookback(start=252, end=21)`` ist die klassische 12-1-Momentum-Messung:
    Rendite von vor 252 Tagen bis vor 21 Tagen, der letzte Monat bleibt aussen
    vor, weil er kurzfristig zur Umkehr neigt.
    """
    if len(close) <= lookback.start:
        return pd.Series(np.nan, index=close.columns, dtype="float64")

    start_row = close.iloc[-(lookback.start + 1)]
    end_row = close.iloc[-1] if lookback.end == 0 else close.iloc[-(lookback.end + 1)]

    with np.errstate(divide="ignore", invalid="ignore"):
        result = (end_row / start_row) - 1.0
    return result.replace([np.inf, -np.inf], np.nan).astype("float64")


def annualized_volatility(close: pd.DataFrame, window: int) -> pd.Series:
    """Annualisierte Standardabweichung der Tagesrenditen."""
    returns = close.pct_change(fill_method=None).tail(window)
    # Mindestens die Haelfte des Fensters muss belegt sein, sonst NaN.
    vol = returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)
    too_few = returns.count() < max(2, window // 2)
    return vol.mask(too_few).astype("float64")


def moving_average(close: pd.DataFrame, window: int) -> pd.Series:
    """Letzter Wert des gleitenden Durchschnitts je Ticker."""
    if window <= 0 or len(close) < window:
        return pd.Series(np.nan, index=close.columns, dtype="float64")
    return close.tail(window).mean().astype("float64")


def zscore(series: pd.Series, winsorize: float) -> pd.Series:
    """Querschnittlicher z-Score, an +/- winsorize gekappt."""
    values = series.astype("float64")
    mean = values.mean(skipna=True)
    std = values.std(ddof=1, skipna=True)
    if not np.isfinite(std) or std == 0:
        return pd.Series(0.0, index=series.index, dtype="float64").mask(values.isna())
    return ((values - mean) / std).clip(-winsorize, winsorize)


def compute_metrics(prices: PriceData, cfg: RankingConfig) -> pd.DataFrame:
    """Rohkennzahlen je Ticker: Momentum-Horizonte, Vol, SMA, Preis."""
    close = prices.close
    metrics = pd.DataFrame(index=close.columns)

    for name, lookback in cfg.lookbacks.items():
        metrics[name] = horizon_return(close, lookback)

    metrics["volatility"] = annualized_volatility(close, cfg.vol_window)
    metrics["price"] = close.iloc[-1] if len(close) else np.nan

    if "mom_12_1" in metrics.columns:
        vol = metrics["volatility"].replace(0.0, np.nan)
        metrics["risk_adj_mom"] = metrics["mom_12_1"] / vol

    return metrics


def rank_universe(
    prices: PriceData,
    cfg: RankingConfig,
    *,
    eligible: list[str] | None = None,
) -> pd.DataFrame:
    """Berechnet Kennzahlen und Gesamtscore, absteigend sortiert.

    ``eligible`` schraenkt die Menge ein, ueber die die z-Scores gebildet
    werden. Das ist wichtig: ein Ticker, der die Datenpruefung nicht besteht,
    darf den Querschnitt der anderen nicht verzerren.
    """
    metrics = compute_metrics(prices, cfg)
    if eligible is not None:
        metrics = metrics.loc[[t for t in eligible if t in metrics.index]]

    weights = cfg.normalized_weights()
    score = pd.Series(0.0, index=metrics.index, dtype="float64")
    contributions = pd.DataFrame(index=metrics.index)

    for signal, weight in weights.items():
        if signal not in metrics.columns:
            continue
        z = zscore(metrics[signal], cfg.winsorize_z)
        contributions[f"z_{signal}"] = z
        score = score.add(z.fillna(0.0) * weight, fill_value=0.0)

    # Ein Ticker ohne jedes gueltige Signal bekommt keinen Score.
    signal_cols = [c for c in contributions.columns]
    if signal_cols:
        all_missing = contributions[signal_cols].isna().all(axis=1)
        score = score.mask(all_missing)

    result = metrics.join(contributions)
    result["score"] = score
    result = result.sort_values("score", ascending=False, na_position="last")
    result.insert(0, "rank", range(1, len(result) + 1))
    return result
