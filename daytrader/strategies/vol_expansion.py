"""Ride a bar that breaks out of its own recent range.

Volatility arrives in clusters: an unusually wide bar tends to be followed by
more movement, and the direction of that bar is the best guess at where. Unlike
a channel breakout this needs no level -- it compares each bar's range to the
recent median, which adapts on its own and fires far less often.
"""

from __future__ import annotations

import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.types import Side, Signal
from .base import Strategy, clean, entry, register


@register
class VolExpansion(Strategy):
    name = "vol_expansion"
    expects_edge_in = ("trending",)
    expects_no_edge_in = ("choppy",)
    default_params = {
        "range_window": 48,
        "expansion_mult": 2.5,   # how much wider than usual the bar has to be
        "close_pct": 0.65,       # and it must close in the top/bottom third
        "atr_window": 14,
        "stop_atr_mult": 2.0,
        "target_r": 3.0,
        "trail_atr_mult": 3.0,
        "min_volume_ratio": 1.5,
    }

    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        out = self.with_atr(df, self.p["atr_window"])
        rng = out["high"] - out["low"]
        out["med_range"] = rng.rolling(self.p["range_window"], min_periods=20).median()
        out["bar_range"] = rng
        # Where in its own range the bar closed: 1.0 = on the high, 0.0 = on the low.
        out["close_loc"] = (out["close"] - out["low"]) / rng.replace(0, float("nan"))
        out["vol_ratio"] = ind.volume_ratio(out["volume"], 20)
        return out

    def signal(self, df: pd.DataFrame, i: int) -> Signal | None:
        a = self.a
        close, atr = a["close"][i], a["atr"][i]
        rng, med, loc, vol = a["bar_range"][i], a["med_range"][i], a["close_loc"][i], a["vol_ratio"][i]
        if not clean(close, atr, rng, med, loc, vol) or atr <= 0 or med <= 0:
            return None
        if rng < self.p["expansion_mult"] * med:
            return None
        if vol < self.p["min_volume_ratio"]:
            return None

        offset = self.p["stop_atr_mult"] * atr
        if loc >= self.p["close_pct"]:
            return entry(Side.LONG, close, close - offset, close + self.p["target_r"] * offset,
                         trail_atr_mult=self.p["trail_atr_mult"],
                         reason=f"range {rng / med:.1f}x median, closed near the high")
        if loc <= 1.0 - self.p["close_pct"]:
            return entry(Side.SHORT, close, close + offset, close - self.p["target_r"] * offset,
                         trail_atr_mult=self.p["trail_atr_mult"],
                         reason=f"range {rng / med:.1f}x median, closed near the low")
        return None
