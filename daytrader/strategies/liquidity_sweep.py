"""Liquidity sweep followed by a break of structure -- the TJR/ICT entry model.

The premise: resting stop orders cluster just past an obvious swing high or
low, price reaches through to take them, and then reverses. The trade is not
the sweep itself but what confirms it -- a break of the opposing structure
afterwards, which is what separates "stops were taken and price turned" from
"the level simply broke".

Sequence, in order, all knowable at the close of each bar:
  1. a wick through a swing extreme that closes back inside it (the sweep)
  2. within `confirm_bars`, a close beyond the opposing swing (the break)
  3. entry on that close, stop past the sweep's extreme, fixed-R target

This is the same shape as failed_breakout but with the confirmation step that
the published model insists on, which is exactly the difference worth measuring.
"""

from __future__ import annotations

import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.types import Side
from .base import Strategy, clean, entry, register


@register
class LiquiditySweep(Strategy):
    name = "liquidity_sweep"
    expects_edge_in = ("choppy",)
    expects_no_edge_in = ("trending",)
    default_params = {
        "swing": 24,             # bars defining the liquidity pool
        "confirm_bars": 6,       # how long the sweep stays live awaiting the break
        "atr_window": 14,
        "stop_buffer_atr": 0.25,
        "target_r": 2.0,
        "trail_atr_mult": 0.0,
        "session_only": 0,       # 1 = London and New York opens only
    }

    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        out = self.with_atr(df, self.p["swing"])
        out["atr"] = ind.atr(out["high"], out["low"], out["close"], self.p["atr_window"])
        n = self.p["swing"]
        # Prior extremes, shifted so the current bar never sees itself.
        out["swing_high"] = out["high"].rolling(n, min_periods=n).max().shift(1)
        out["swing_low"] = out["low"].rolling(n, min_periods=n).min().shift(1)
        out["hour"] = out.index.hour
        return out

    def bind(self, prepared: pd.DataFrame) -> None:
        super().bind(prepared)
        self._swept_low: tuple[int, float] | None = None   # (bar, extreme)
        self._swept_high: tuple[int, float] | None = None

    def _in_session(self, hour: int) -> bool:
        if not self.p["session_only"]:
            return True
        return 7 <= hour < 10 or 13 <= hour < 16   # London open, New York open

    def signal(self, df: pd.DataFrame, i: int):
        a = self.a
        close, high, low, atr = a["close"][i], a["high"][i], a["low"][i], a["atr"][i]
        sh, sl = a["swing_high"][i], a["swing_low"][i]
        if not clean(close, atr, sh, sl) or atr <= 0:
            return None

        # 1. Sweep: wick through the pool, close back inside it.
        if low < sl and close > sl:
            self._swept_low = (i, low)
        if high > sh and close < sh:
            self._swept_high = (i, high)

        # Expire a sweep that never got its confirmation.
        if self._swept_low and i - self._swept_low[0] > self.p["confirm_bars"]:
            self._swept_low = None
        if self._swept_high and i - self._swept_high[0] > self.p["confirm_bars"]:
            self._swept_high = None

        if not self._in_session(int(a["hour"][i])):
            return None
        buf = self.p["stop_buffer_atr"] * atr

        # 2. Break of structure in the opposite direction confirms the sweep.
        if self._swept_low and close > sh:
            stop = self._swept_low[1] - buf
            risk = close - stop
            self._swept_low = None
            if risk > 0:
                return entry(Side.LONG, close, stop, close + self.p["target_r"] * risk,
                             trail_atr_mult=self.p["trail_atr_mult"],
                             reason=f"sell-side liquidity swept at {sl:.4f}, structure broken")
        if self._swept_high and close < sl:
            stop = self._swept_high[1] + buf
            risk = stop - close
            self._swept_high = None
            if risk > 0:
                return entry(Side.SHORT, close, stop, close - self.p["target_r"] * risk,
                             trail_atr_mult=self.p["trail_atr_mult"],
                             reason=f"buy-side liquidity swept at {sh:.4f}, structure broken")
        return None
