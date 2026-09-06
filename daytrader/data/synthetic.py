"""Deterministic synthetic candles for offline testing.

This exists to exercise the engine where no exchange is reachable -- CI, a
locked-down container, a laptop on a plane. It reproduces the *statistical
texture* of intraday crypto (volatility clustering, regime switches, a volume
smile across the day) but it is not a market. Never read a strategy edge out
of synthetic results; use it to prove the plumbing, then backtest on real
candles.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ..core.timeframe import bar_minutes

SUBSTEPS = 12  # intra-bar ticks, so OHLC comes out internally consistent


def generate(
    symbol: str = "BTCUSDT",
    interval: str = "5m",
    bars: int = 20_000,
    start: datetime | None = None,
    start_price: float = 60_000.0,
    annual_vol: float = 0.65,
    seed: int = 7,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed + abs(hash(symbol)) % 10_000)
    minutes = bar_minutes(interval)
    start = start or datetime(2024, 1, 1, tzinfo=timezone.utc)
    index = pd.date_range(start, periods=bars, freq=f"{minutes}min", tz="UTC")

    n = bars * SUBSTEPS
    per_step_minutes = minutes / SUBSTEPS
    steps_per_year = 365 * 24 * 60 / per_step_minutes
    base_sigma = annual_vol / np.sqrt(steps_per_year)

    # Volatility clustering: an AR(1) in log-variance, the cheap GARCH stand-in.
    log_var = np.zeros(n)
    shocks = rng.normal(0.0, 0.35, n)
    for i in range(1, n):
        log_var[i] = 0.985 * log_var[i - 1] + shocks[i] * 0.08
    sigma = base_sigma * np.exp(log_var)

    # Regime switching between trending and mean-reverting stretches, which is
    # what makes strategy selection a real question rather than a formality.
    regime = np.zeros(n)
    state, remaining, drift = 0, 0, 0.0
    for i in range(n):
        if remaining <= 0:
            state = rng.integers(0, 3)  # 0 chop, 1 trend up, 2 trend down
            remaining = int(rng.integers(200, 3000))
            drift = 0.0 if state == 0 else (1 if state == 1 else -1) * base_sigma * rng.uniform(0.01, 0.06)
        regime[i] = drift
        remaining -= 1

    # Mild mean reversion inside chop keeps prices from random-walking away.
    returns = np.empty(n)
    log_price = np.log(start_price)
    anchor = log_price
    for i in range(n):
        anchor = 0.9995 * anchor + 0.0005 * log_price
        pull = 0.002 * (anchor - log_price) if regime[i] == 0 else 0.0
        step = regime[i] + pull + sigma[i] * rng.normal()
        log_price += step
        returns[i] = log_price

    prices = np.exp(returns).reshape(bars, SUBSTEPS)
    opens = prices[:, 0]
    closes = prices[:, -1]
    highs = prices.max(axis=1)
    lows = prices.min(axis=1)

    # Volume: a daily smile plus a surge on large moves, never negative.
    minute_of_day = index.hour * 60 + index.minute
    smile = 1.0 + 0.45 * np.cos(2 * np.pi * (minute_of_day - 840) / 1440.0)
    move = np.abs(closes / opens - 1.0)
    volume = (
        smile
        * rng.lognormal(0.0, 0.35, bars)
        * (1.0 + 60.0 * move)
        * 50.0
    )

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
    return df
