"""Fade a breakout that immediately fails.

The mirror image of donchian_breakout, and included for the same reason it was:
as a control that costs nothing to run. If breakouts on this timeframe lose
money, the trade on the other side of them deserves a look. A break of the
channel that closes back inside within a bar or two is the signature of a move
with nobody behind it -- the stop sits just past the extreme, which makes the
invalidation unusually tight and the risk-reward unusually clean.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.types import Side, Signal
from .base import Strategy, clean, entry, register


@register
class FailedBreakout(Strategy):
    name = "failed_breakout"
    expects_edge_in = ("choppy",)
    expects_no_edge_in = ("trending",)
    default_params = {
        "channel": 48,
        "recover_bars": 2,      # how quickly price has to close back inside
        "atr_window": 14,
        "stop_atr_mult": 1.5,
        "target_r": 2.5,
        "trail_atr_mult": 3.0,
    }

    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        out = self.with_atr(df, self.p["atr_window"])
        upper, lower = ind.donchian(out["high"], out["low"], self.p["channel"])
        out["chan_high"], out["chan_low"] = upper, lower
        n = self.p["recover_bars"]
        # Did any of the last n bars poke through the channel?
        out["poked_up"] = (out["high"] > upper.shift(1)).rolling(n, min_periods=1).max()
        out["poked_down"] = (out["low"] < lower.shift(1)).rolling(n, min_periods=1).max()
        out["prev_high"] = out["high"].rolling(n, min_periods=1).max()
        out["prev_low"] = out["low"].rolling(n, min_periods=1).min()
        return out

    def signal(self, df: pd.DataFrame, i: int) -> Signal | None:
        a = self.a
        close, atr = a["close"][i], a["atr"][i]
        upper, lower = a["chan_high"][i], a["chan_low"][i]
        up, down = a["poked_up"][i], a["poked_down"][i]
        ph, pl = a["prev_high"][i], a["prev_low"][i]
        if not clean(close, atr, upper, lower, ph, pl) or atr <= 0:
            return None

        offset = self.p["stop_atr_mult"] * atr
        # Broke the high, closed back inside -> fade it, stop above the failure.
        if up == 1 and close < upper:
            stop = max(ph + 0.25 * atr, close + offset)
            risk = stop - close
            return entry(Side.SHORT, close, stop, close - self.p["target_r"] * risk,
                         trail_atr_mult=self.p["trail_atr_mult"],
                         reason=f"break above {upper:.4f} closed back inside")
        if down == 1 and close > lower:
            stop = min(pl - 0.25 * atr, close - offset)
            risk = close - stop
            return entry(Side.LONG, close, stop, close + self.p["target_r"] * risk,
                         trail_atr_mult=self.p["trail_atr_mult"],
                         reason=f"break below {lower:.4f} closed back inside")
        return None
