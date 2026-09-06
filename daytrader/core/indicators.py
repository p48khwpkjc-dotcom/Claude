"""Causal technical indicators.

Every function here reads only past and present bars. Nothing shifts data
backwards in time, so an indicator value at bar i is identical whether it was
computed on the full history or on history truncated at i. `tests/
test_indicators.py` asserts exactly that -- it is the cheapest defence against
the lookahead bias that silently flatters most backtests.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _session_grouper(index: pd.DatetimeIndex, session: str) -> pd.Index:
    """Group key for a trading session, preserving the timezone.

    `to_period` would drop the tz and warn; flooring keeps the index tz-aware
    and gives the same UTC-day buckets.
    """
    try:
        return index.floor(session)
    except ValueError:
        return index.tz_localize(None).to_period(session)


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=window).mean()


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    ranges = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    )
    return ranges.max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's ATR (an EMA with alpha = 1/window)."""
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # A window with no losses is a maximally overbought reading, not a gap.
    return out.where(avg_loss.notna(), np.nan).fillna(
        pd.Series(np.where(avg_loss.eq(0.0) & avg_gain.gt(0.0), 100.0, np.nan), index=close.index)
    )


def session_vwap(df: pd.DataFrame, session: str = "D") -> pd.Series:
    """Volume weighted average price, reset at each session boundary.

    Crypto has no exchange open, so the session is the UTC day -- the boundary
    most desks and most liquidity actually anchor to.
    """
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    grouper = _session_grouper(df.index, session)
    pv = (typical * df["volume"]).groupby(grouper).cumsum()
    vol = df["volume"].groupby(grouper).cumsum()
    return pv / vol.replace(0.0, np.nan)


def session_vwap_bands(
    df: pd.DataFrame, vwap: pd.Series, mult: float = 2.0, session: str = "D"
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Standard deviation of price around the running session VWAP."""
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    grouper = _session_grouper(df.index, session)
    dev_sq = ((typical - vwap) ** 2) * df["volume"]
    cum_dev = dev_sq.groupby(grouper).cumsum()
    cum_vol = df["volume"].groupby(grouper).cumsum().replace(0.0, np.nan)
    sd = np.sqrt(cum_dev / cum_vol)
    return vwap - mult * sd, sd, vwap + mult * sd


def rolling_vwap(df: pd.DataFrame, window: int) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = (typical * df["volume"]).rolling(window, min_periods=window).sum()
    vol = df["volume"].rolling(window, min_periods=window).sum()
    return pv / vol.replace(0.0, np.nan)


def volume_ratio(volume: pd.Series, window: int = 20) -> pd.Series:
    """Current volume relative to its recent average. 1.0 means average."""
    avg = volume.rolling(window, min_periods=window).mean()
    return volume / avg.replace(0.0, np.nan)


def donchian(high: pd.Series, low: pd.Series, window: int) -> tuple[pd.Series, pd.Series]:
    """Channel over the last `window` *completed* bars, excluding the current one.

    Excluding the current bar is what makes a breakout test meaningful: a bar
    can never break out of a channel it helped define.
    """
    upper = high.shift(1).rolling(window, min_periods=window).max()
    lower = low.shift(1).rolling(window, min_periods=window).min()
    return upper, lower


def slope(series: pd.Series, window: int) -> pd.Series:
    """Relative change over `window` bars -- a scale-free trend reading."""
    past = series.shift(window)
    return (series - past) / past.abs().replace(0.0, np.nan)


def opening_range(
    df: pd.DataFrame, minutes: int, bar_minutes: int, session: str = "D"
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """High/low of the first `minutes` of each session, and a completion flag.

    The range is only usable once it is closed, so both levels are held back
    until the opening window has fully elapsed.
    """
    bars = max(1, minutes // bar_minutes)
    grouper = _session_grouper(df.index, session)
    bar_no = df.groupby(grouper).cumcount()
    in_window = bar_no < bars

    hi = df["high"].where(in_window)
    lo = df["low"].where(in_window)
    or_high = hi.groupby(grouper).cummax().groupby(grouper).ffill()
    or_low = lo.groupby(grouper).cummin().groupby(grouper).ffill()

    complete = bar_no >= bars
    return or_high.where(complete), or_low.where(complete), complete
