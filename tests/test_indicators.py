"""Causality: an indicator must not change when future bars are removed."""

import numpy as np
import pandas as pd
import pytest

from daytrader.core import indicators as ind
from daytrader.data.synthetic import generate


@pytest.fixture(scope="module")
def df():
    return generate(bars=1200, seed=3)


def _series(name, d):
    return {
        "ema": lambda: ind.ema(d["close"], 21),
        "sma": lambda: ind.sma(d["close"], 20),
        "atr": lambda: ind.atr(d["high"], d["low"], d["close"], 14),
        "rsi": lambda: ind.rsi(d["close"], 14),
        "vwap": lambda: ind.session_vwap(d),
        "rolling_vwap": lambda: ind.rolling_vwap(d, 20),
        "volume_ratio": lambda: ind.volume_ratio(d["volume"], 20),
        "slope": lambda: ind.slope(d["close"], 12),
        "donchian_up": lambda: ind.donchian(d["high"], d["low"], 20)[0],
        "or_high": lambda: ind.opening_range(d, 60, 5)[0],
    }[name]()


NAMES = ["ema", "sma", "atr", "rsi", "vwap", "rolling_vwap", "volume_ratio",
         "slope", "donchian_up", "or_high"]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("cut", [400, 700, 1100])
def test_truncating_the_future_changes_nothing(df, name, cut):
    full = _series(name, df)
    truncated = _series(name, df.iloc[:cut])
    a, b = full.iloc[cut - 1], truncated.iloc[-1]
    if np.isnan(a) and np.isnan(b):
        return
    assert a == pytest.approx(b, rel=1e-12, abs=1e-9), f"{name} peeks at future bars"


def test_donchian_excludes_the_current_bar(df):
    upper, _ = ind.donchian(df["high"], df["low"], 20)
    i = 500
    assert upper.iloc[i] == pytest.approx(df["high"].iloc[i - 20:i].max())


def test_opening_range_is_hidden_until_the_window_closes(df):
    or_high, or_low, complete = ind.opening_range(df, 60, 5)
    first_day = df.index.floor("D") == df.index[0].floor("D")
    early = or_high[first_day].iloc[:12]
    assert early.isna().all(), "range leaked before the opening hour finished"
    assert not np.isnan(or_high[first_day].iloc[12])


def test_rsi_bounds(df):
    r = ind.rsi(df["close"], 14).dropna()
    assert r.between(0, 100).all()


def test_atr_is_positive(df):
    a = ind.atr(df["high"], df["low"], df["close"], 14).dropna()
    assert (a > 0).all()
