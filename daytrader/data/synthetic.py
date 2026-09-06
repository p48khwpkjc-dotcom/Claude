"""Deterministic synthetic candles, generated under a named market regime.

Two distinct jobs:

1. Offline plumbing: exercise the engine where no exchange is reachable.
2. Falsification: a trend strategy that loses money on a series which trends
   *by construction*, or a mean-reversion strategy that loses on a series which
   reverts by construction, is broken -- and that verdict does not need real
   market data. It is the one form of strategy testing that stays valid
   offline.

What it cannot tell you is whether a strategy has an edge in the real market.
Regimes here are hand-built; real markets do not announce which one they are in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ..core.timeframe import bar_minutes

SUBSTEPS = 12  # intra-bar ticks, so OHLC comes out internally consistent


@dataclass(frozen=True, slots=True)
class Regime:
    """How a synthetic series behaves. Drift and reversion are per sub-step."""

    name: str
    annual_vol: float
    drift_strength: float      # size of trending pushes, in units of base sigma
    reversion: float           # pull back towards the slow anchor, 0 = none
    trend_share: float         # fraction of time spent trending rather than chopping
    min_run: int = 200         # shortest regime stretch, in sub-steps
    max_run: int = 3000
    description: str = ""


REGIMES: dict[str, Regime] = {
    "trending": Regime(
        "trending", annual_vol=0.65, drift_strength=0.10, reversion=0.0,
        trend_share=1.0, min_run=1500, max_run=6000,
        description="persistent directional pushes, no pull back to a mean",
    ),
    "choppy": Regime(
        "choppy", annual_vol=0.55, drift_strength=0.0, reversion=0.02,
        trend_share=0.0, min_run=200, max_run=800,
        description="range bound, prices pulled back towards a slow anchor",
    ),
    "volatile": Regime(
        "volatile", annual_vol=1.20, drift_strength=0.08, reversion=0.004,
        trend_share=0.5, min_run=150, max_run=1200,
        description="large moves in both directions, frequent regime flips",
    ),
    "quiet": Regime(
        "quiet", annual_vol=0.25, drift_strength=0.03, reversion=0.01,
        trend_share=0.35, min_run=500, max_run=3000,
        description="low volatility drift, where trading costs bite hardest",
    ),
    "mixed": Regime(
        "mixed", annual_vol=0.65, drift_strength=0.05, reversion=0.002,
        trend_share=0.55, min_run=200, max_run=3000,
        description="trends and ranges alternating, the closest to a real tape",
    ),
}


def generate(
    symbol: str = "BTCUSDT",
    interval: str = "5m",
    bars: int = 20_000,
    start: datetime | None = None,
    start_price: float = 60_000.0,
    regime: str | Regime = "mixed",
    annual_vol: float | None = None,
    seed: int = 7,
) -> pd.DataFrame:
    spec = REGIMES[regime] if isinstance(regime, str) else regime
    vol = annual_vol if annual_vol is not None else spec.annual_vol

    rng = np.random.default_rng(seed + abs(hash(symbol)) % 10_000)
    minutes = bar_minutes(interval)
    start = start or datetime(2024, 1, 1, tzinfo=timezone.utc)
    index = pd.date_range(start, periods=bars, freq=f"{minutes}min", tz="UTC")

    n = bars * SUBSTEPS
    per_step_minutes = minutes / SUBSTEPS
    base_sigma = vol / np.sqrt(365 * 24 * 60 / per_step_minutes)

    # Volatility clustering: an AR(1) in log-variance, the cheap GARCH stand-in.
    log_var = np.zeros(n)
    shocks = rng.normal(0.0, 0.35, n)
    for i in range(1, n):
        log_var[i] = 0.985 * log_var[i - 1] + shocks[i] * 0.08
    sigma = base_sigma * np.exp(log_var)

    drift = _drift_path(rng, n, spec, base_sigma)

    log_price = np.log(start_price)
    anchor = log_price
    path = np.empty(n)
    for i in range(n):
        anchor = 0.9995 * anchor + 0.0005 * log_price
        pull = spec.reversion * (anchor - log_price) if drift[i] == 0.0 else 0.0
        log_price += drift[i] + pull + sigma[i] * rng.normal()
        path[i] = log_price

    prices = np.exp(path).reshape(bars, SUBSTEPS)
    opens, closes = prices[:, 0], prices[:, -1]
    highs, lows = prices.max(axis=1), prices.min(axis=1)

    minute_of_day = index.hour * 60 + index.minute
    smile = 1.0 + 0.45 * np.cos(2 * np.pi * (minute_of_day - 840) / 1440.0)
    move = np.abs(closes / opens - 1.0)
    volume = smile * rng.lognormal(0.0, 0.35, bars) * (1.0 + 60.0 * move) * 50.0

    df = pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(highs, np.maximum(opens, closes)),
            "low": np.minimum(lows, np.minimum(opens, closes)),
            "close": closes,
            "volume": volume,
            "quote_volume": volume * closes,
            "trades": np.maximum(1, (volume * 3).astype(int)),
        },
        index=index,
    )
    df.index.name = "open_time"
    df.attrs["regime"] = spec.name
    return df


def _drift_path(rng, n: int, spec: Regime, base_sigma: float) -> np.ndarray:
    """Alternate trending stretches with flat ones, per the regime's trend share."""
    drift = np.zeros(n)
    i = 0
    while i < n:
        run = int(rng.integers(spec.min_run, spec.max_run + 1))
        trending = spec.drift_strength > 0 and rng.random() < spec.trend_share
        if trending:
            direction = 1.0 if rng.random() < 0.5 else -1.0
            drift[i:i + run] = direction * base_sigma * spec.drift_strength
        i += run
    return drift
