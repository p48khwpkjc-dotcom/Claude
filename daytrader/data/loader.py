"""Candle loading with a local parquet cache.

Downloads are incremental: an existing cache is extended from its last bar
rather than refetched, so a daily update costs one request instead of a year
of history.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from ..core.timeframe import bar_minutes
from . import binance, synthetic

log = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]


def cache_path(cache_dir: Path, symbol: str, interval: str) -> Path:
    return Path(cache_dir) / f"{symbol.upper()}_{interval}.parquet"


def read_cache(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if df.empty:
        return None
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df.sort_index()


def write_cache(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)


def update(
    symbol: str,
    interval: str,
    days: int,
    cache_dir: Path,
    end: datetime | None = None,
) -> pd.DataFrame:
    """Fetch missing candles for `symbol` and merge them into the cache."""
    end = end or datetime.now(timezone.utc)
    wanted_start = end - timedelta(days=days)
    path = cache_path(cache_dir, symbol, interval)
    cached = read_cache(path)

    if cached is not None and not cached.empty:
        start = max(cached.index[-1].to_pydatetime(), wanted_start)
        if cached.index[0] > wanted_start + timedelta(minutes=bar_minutes(interval)):
            log.info("%s: cache starts late, refetching from %s", symbol, wanted_start.date())
            start = wanted_start
    else:
        start = wanted_start

    fresh = binance.fetch_klines(symbol, interval, start, end)
    merged = fresh if cached is None else pd.concat([cached, fresh])
    merged = merged[~merged.index.duplicated(keep="last")].sort_index()
    write_cache(path, merged)
    log.info("%s %s: %d bars cached (%s .. %s)", symbol, interval, len(merged),
             merged.index[0], merged.index[-1])
    return merged


def load(
    symbol: str,
    interval: str,
    cache_dir: Path,
    start: datetime | None = None,
    end: datetime | None = None,
    source: str = "cache",
    synthetic_bars: int = 20_000,
) -> pd.DataFrame:
    """Load candles for a backtest.

    source="cache"     -- read the parquet cache, error if it is missing
    source="synthetic" -- generate deterministic candles, no network needed
    """
    if source == "synthetic":
        df = synthetic.generate(symbol=symbol, interval=interval, bars=synthetic_bars)
    else:
        df = read_cache(cache_path(cache_dir, symbol, interval))
        if df is None:
            raise FileNotFoundError(
                f"no cached candles for {symbol} {interval}. "
                f"Run: python -m daytrader fetch --symbols {symbol} --interval {interval}"
            )

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"candles for {symbol} missing columns: {missing}")

    if start is not None:
        df = df[df.index >= pd.Timestamp(start, tz="UTC")]
    if end is not None:
        df = df[df.index < pd.Timestamp(end, tz="UTC")]
    return validate(df, symbol, interval)


def validate(df: pd.DataFrame, symbol: str, interval: str) -> pd.DataFrame:
    """Reject candle sets a backtest cannot be trusted on."""
    if df.empty:
        raise ValueError(f"{symbol} {interval}: no candles in range")
    if not df.index.is_monotonic_increasing:
        raise ValueError(f"{symbol} {interval}: index is not sorted")
    if df.index.has_duplicates:
        raise ValueError(f"{symbol} {interval}: duplicate timestamps")

    bad = df[(df["high"] < df[["open", "close"]].max(axis=1) - 1e-9)
             | (df["low"] > df[["open", "close"]].min(axis=1) + 1e-9)]
    if not bad.empty:
        raise ValueError(f"{symbol} {interval}: {len(bad)} candles with impossible OHLC")

    expected = pd.Timedelta(minutes=bar_minutes(interval))
    gaps = df.index.to_series().diff().dropna()
    big = gaps[gaps > expected]
    if len(big) > 0:
        worst = big.max()
        log.warning("%s %s: %d gaps in history, largest %s -- exchange downtime "
                    "or a stale cache", symbol, interval, len(big), worst)
    return df
