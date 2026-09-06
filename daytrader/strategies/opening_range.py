"""Opening-range breakout on the UTC day.

Crypto has no bell, but the UTC rollover is where funding, futures settlement
and most desk reporting cluster, so the first hour of the UTC day carries a
genuine range that the rest of the day either respects or breaks. This takes
the break, once per direction per day, and only with volume behind it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.timeframe import bar_minutes
from ..core.types import Side, Signal
from .base import Strategy, clean, entry, register


@register
class OpeningRangeBreakout(Strategy):
    name = "opening_range"
    expects_edge_in = ("trending",)
    expects_no_edge_in = ("choppy",)
    default_params = {
        "range_minutes": 60,
        "atr_window": 14,
        "stop_atr_mult": 1.0,
        "target_r": 2.0,
        "min_volume_ratio": 1.3,
        "max_entry_hour": 20,
        "trail_atr_mult": 2.0,
    }

    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        out = self.with_atr(df, self.p["atr_window"])
        or_high, or_low, _ = ind.opening_range(
            out, self.p["range_minutes"], bar_minutes(cfg.data.interval)
        )
        out["or_high"], out["or_low"] = or_high, or_low
        out["vol_ratio"] = ind.volume_ratio(out["volume"], 20)

        # One shot per direction per session: a day that breaks out, fails and
        # breaks out again is chop, and chasing it is how this strategy bleeds.
        day = out.index.floor("D")
        broke_up = (out["close"] > or_high).fillna(False)
        broke_dn = (out["close"] < or_low).fillna(False)
        out["first_break_up"] = broke_up & (broke_up.groupby(day).cumsum() == 1)
        out["first_break_dn"] = broke_dn & (broke_dn.groupby(day).cumsum() == 1)
        return out

    def signal(self, df: pd.DataFrame, i: int) -> Signal | None:
        a = self.a
        close, atr, vol_ratio = a["close"][i], a["atr"][i], a["vol_ratio"][i]
        if not clean(close, atr, vol_ratio) or atr <= 0:
            return None
        if vol_ratio < self.p["min_volume_ratio"]:
            return None
        if self.index[i].hour >= self.p["max_entry_hour"]:
            return None  # a breakout with two hours of session left rarely runs

        stop_offset = self.p["stop_atr_mult"] * atr
        if a["first_break_up"][i]:
            stop = close - stop_offset
            return entry(
                Side.LONG, close,
                stop,
                close + self.p["target_r"] * stop_offset,
                trail_atr_mult=self.p["trail_atr_mult"],
                reason=f"break above {a['or_high'][i]:.2f} on {vol_ratio:.1f}x volume",
            )
        if a["first_break_dn"][i]:
            stop = close + stop_offset
            return entry(
                Side.SHORT, close,
                stop,
                close - self.p["target_r"] * stop_offset,
                trail_atr_mult=self.p["trail_atr_mult"],
                reason=f"break below {a['or_low'][i]:.2f} on {vol_ratio:.1f}x volume",
            )
        return None
