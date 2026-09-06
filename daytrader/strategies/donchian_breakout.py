"""Donchian channel breakout -- the plainest trend follower there is.

Included as a control. It has almost no parameters and no filters, so if a
more elaborate trend strategy cannot beat it, the elaboration is decoration.
"""

from __future__ import annotations

import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.types import Side, Signal
from .base import Strategy, clean, entry, register


@register
class DonchianBreakout(Strategy):
    name = "donchian_breakout"
    expects_edge_in = ("trending",)
    expects_no_edge_in = ("choppy",)
    default_params = {
        "channel": 48,          # four hours of 5m bars
        "atr_window": 14,
        "stop_atr_mult": 2.0,
        "target_r": 2.5,
        "trail_atr_mult": 3.0,
        "min_volume_ratio": 1.0,
    }

    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        out = self.with_atr(df, self.p["atr_window"])
        upper, lower = ind.donchian(out["high"], out["low"], self.p["channel"])
        out["chan_high"], out["chan_low"] = upper, lower
        out["vol_ratio"] = ind.volume_ratio(out["volume"], 20)
        return out

    def signal(self, df: pd.DataFrame, i: int) -> Signal | None:
        a = self.a
        close, atr = a["close"][i], a["atr"][i]
        upper, lower = a["chan_high"][i], a["chan_low"][i]
        vol_ratio = a["vol_ratio"][i]
        if not clean(close, atr, upper, lower, vol_ratio) or atr <= 0:
            return None
        if vol_ratio < self.p["min_volume_ratio"]:
            return None

        offset = self.p["stop_atr_mult"] * atr
        if close > upper:
            return entry(Side.LONG, close, close - offset, close + self.p["target_r"] * offset,
                         trail_atr_mult=self.p["trail_atr_mult"],
                         reason=f"{self.p['channel']}-bar high broken at {upper:.2f}")
        if close < lower:
            return entry(Side.SHORT, close, close + offset, close - self.p["target_r"] * offset,
                         trail_atr_mult=self.p["trail_atr_mult"],
                         reason=f"{self.p['channel']}-bar low broken at {lower:.2f}")
        return None
