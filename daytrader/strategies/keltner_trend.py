"""Trend continuation while price walks the outside of a Keltner channel.

A single close beyond a band is noise; several in a row is a market that has
stopped two-way trading. This waits for persistence rather than the first
touch, which is the difference between catching a trend and catching every
spike. The channel is ATR-based, so it widens with volatility instead of
firing more often when the market gets loud.
"""

from __future__ import annotations

import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.types import Side, Signal
from .base import Strategy, clean, register


@register
class KeltnerTrend(Strategy):
    name = "keltner_trend"
    expects_edge_in = ("trending",)
    expects_no_edge_in = ("choppy",)
    default_params = {
        "ema_window": 20,
        "atr_window": 14,
        "band_mult": 1.5,
        "persist_bars": 3,      # closes outside the band before we act
        "stop_atr_mult": 2.0,
        "target_r": 3.0,
        "trail_atr_mult": 2.5,
    }

    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        out = self.with_atr(df, self.p["atr_window"])
        mid = ind.ema(out["close"], self.p["ema_window"])
        out["mid"] = mid
        out["upper"] = mid + self.p["band_mult"] * out["atr"]
        out["lower"] = mid - self.p["band_mult"] * out["atr"]
        n = self.p["persist_bars"]
        out["above"] = (out["close"] > out["upper"]).rolling(n, min_periods=n).sum()
        out["below"] = (out["close"] < out["lower"]).rolling(n, min_periods=n).sum()
        return out

    def signal(self, df: pd.DataFrame, i: int) -> Signal | None:
        a = self.a
        close, atr, mid = a["close"][i], a["atr"][i], a["mid"][i]
        above, below = a["above"][i], a["below"][i]
        if not clean(close, atr, mid, above, below) or atr <= 0:
            return None
        n = self.p["persist_bars"]
        offset = self.p["stop_atr_mult"] * atr

        # Exactly n means the run just completed on this bar; more means we
        # already acted on it and would be adding to a move we are late for.
        if above == n:
            return Signal(Side.LONG, close - offset, close + self.p["target_r"] * offset,
                          trail_atr_mult=self.p["trail_atr_mult"],
                          reason=f"{n} closes above the Keltner band")
        if below == n:
            return Signal(Side.SHORT, close + offset, close - self.p["target_r"] * offset,
                          trail_atr_mult=self.p["trail_atr_mult"],
                          reason=f"{n} closes below the Keltner band")
        return None
