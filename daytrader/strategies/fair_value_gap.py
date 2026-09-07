"""Fair value gap: enter on the retracement into a three-candle imbalance.

The pattern is defined mechanically and without discretion: three candles where
the first candle's high and the third candle's low do not overlap leave a band
of price through which the market moved without trading both sides. The claim
is that price returns to that band and continues in the direction that made it.

Rules taken from the published definition rather than from any one teacher:
entry on the retrace into the gap, stop beyond the displacement candle that
created it, target a fixed multiple of that risk. The displacement filter is
the one place where the published versions differ -- some require the middle
candle to be unusually large, some do not -- so it is a parameter.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.types import Side
from .base import Strategy, clean, entry, register


@register
class FairValueGap(Strategy):
    name = "fair_value_gap"
    expects_edge_in = ("trending",)
    expects_no_edge_in = ("choppy",)
    default_params = {
        "atr_window": 14,
        "min_gap_atr": 0.10,     # ignore gaps too small to be anything but noise
        "min_displacement_atr": 1.0,   # the middle candle has to actually displace
        "valid_bars": 12,        # how long a gap stays tradeable
        "target_r": 2.0,
        "trail_atr_mult": 0.0,   # 0 disables trailing: test the clean 2R claim
        "stop_buffer_atr": 0.1,
    }

    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        out = self.with_atr(df, self.p["atr_window"])
        h, l, c, o = out["high"], out["low"], out["close"], out["open"]
        body = (c - o).abs()

        # A gap is knowable only once the third candle has closed, so everything
        # is indexed to that bar and read on later bars only.
        bull = l - h.shift(2)                     # third low above first high
        bear = l.shift(2) - h                     # third high below first low
        displaced = body.shift(1) >= self.p["min_displacement_atr"] * out["atr"]

        out["bull_gap"] = bull.where((bull > 0) & displaced)
        out["bear_gap"] = bear.where((bear > 0) & displaced)
        out["bull_top"] = l.where(out["bull_gap"].notna())        # gap upper edge
        out["bull_bot"] = h.shift(2).where(out["bull_gap"].notna())
        out["bear_bot"] = h.where(out["bear_gap"].notna())
        out["bear_top"] = l.shift(2).where(out["bear_gap"].notna())
        # The displacement candle's extreme is where the idea is wrong.
        out["bull_inval"] = l.shift(1).where(out["bull_gap"].notna())
        out["bear_inval"] = h.shift(1).where(out["bear_gap"].notna())
        return out

    def bind(self, prepared: pd.DataFrame) -> None:
        super().bind(prepared)
        self._open: list[tuple[int, str, float, float, float]] = []

    def signal(self, df: pd.DataFrame, i: int):
        a = self.a
        close, low, high, atr = a["close"][i], a["low"][i], a["high"][i], a["atr"][i]
        if not clean(close, atr) or atr <= 0:
            return None

        # Register a gap that completed on the previous bar.
        j = i - 1
        if j >= 0:
            if a["bull_gap"][j] == a["bull_gap"][j] and a["bull_gap"][j] >= self.p["min_gap_atr"] * atr:
                self._open.append((j, "bull", a["bull_bot"][j], a["bull_top"][j], a["bull_inval"][j]))
            if a["bear_gap"][j] == a["bear_gap"][j] and a["bear_gap"][j] >= self.p["min_gap_atr"] * atr:
                self._open.append((j, "bear", a["bear_bot"][j], a["bear_top"][j], a["bear_inval"][j]))
        self._open = [g for g in self._open if i - g[0] <= self.p["valid_bars"]]

        buf = self.p["stop_buffer_atr"] * atr
        for k, (born, kind, bot, top, inval) in enumerate(self._open):
            if born >= i or not clean(bot, top, inval):
                continue
            if kind == "bull" and low <= top and close > bot:
                stop = min(inval, bot) - buf
                risk = close - stop
                if risk <= 0:
                    continue
                del self._open[k]
                return entry(Side.LONG, close, stop, close + self.p["target_r"] * risk,
                             trail_atr_mult=self.p["trail_atr_mult"],
                             reason=f"retrace into a bullish FVG {bot:.4f}-{top:.4f}")
            if kind == "bear" and high >= bot and close < top:
                stop = max(inval, top) + buf
                risk = stop - close
                if risk <= 0:
                    continue
                del self._open[k]
                return entry(Side.SHORT, close, stop, close - self.p["target_r"] * risk,
                             trail_atr_mult=self.p["trail_atr_mult"],
                             reason=f"retrace into a bearish FVG {top:.4f}-{bot:.4f}")
        return None
