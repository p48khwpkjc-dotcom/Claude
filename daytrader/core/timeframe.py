"""Multi-timeframe alignment.

A higher-timeframe bar is only knowable once it has closed. Attaching an
unfinished 1h bar to a 5m decision is the second-most common way a backtest
lies to you (after peeking at the current bar's close for the fill price), so
the alignment here is deliberately explicit about close times.
"""

from __future__ import annotations

import pandas as pd

OHLCV_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}


def bar_minutes(interval: str) -> int:
    """Minutes per bar for the Binance-style interval strings we use."""
    unit = interval[-1]
    value = int(interval[:-1])
    factor = {"m": 1, "h": 60, "d": 1440, "w": 10080}
    if unit not in factor:
        raise ValueError(f"unsupported interval: {interval}")
    return value * factor[unit]


def to_offset(interval: str) -> pd.Timedelta:
    return pd.Timedelta(minutes=bar_minutes(interval))


def resample_ohlcv(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Aggregate to a higher timeframe, bars labelled by their open time."""
    agg = {k: v for k, v in OHLCV_AGG.items() if k in df.columns}
    out = df.resample(to_offset(interval), label="left", closed="left").agg(agg)
    return out.dropna(subset=["open"])


def align_to(htf: pd.DataFrame | pd.Series, ltf_index: pd.DatetimeIndex, htf_interval: str):
    """Project closed higher-timeframe values onto a lower-timeframe index.

    The value carried at a low-timeframe bar is the most recent
    higher-timeframe bar that had already *closed* when that bar opened.
    """
    period = to_offset(htf_interval)
    shifted = htf.copy()
    shifted.index = htf.index + period  # index by close time, not open time
    return shifted.reindex(ltf_index, method="ffill")
