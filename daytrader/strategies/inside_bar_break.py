"""Break out of a contraction, not out of a range.

Squeeze_breakout looks for compressed Bollinger bands; this looks for the same
idea in its plainest form -- a bar whose whole range sits inside the previous
one, meaning the market just declined to go anywhere. The break of that small
bar gives an unusually tight invalidation, which is the only way to earn a
decent multiple of risk without a wide target the market never reaches.
"""

from __future__ import annotations

import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.types import Side, Signal
from .base import Strategy, clean, entry, register


@register
class InsideBarBreak(Strategy):
    name = "inside_bar_break"
    expects_edge_in = ("trending",)
    expects_no_edge_in = ("choppy",)
    default_params = {
        "contraction_bars": 1,   # consecutive inside bars required
        "atr_window": 14,
        "max_range_atr": 1.2,    # the coil has to be genuinely small
        "stop_buffer_atr": 0.25,
        "target_r": 3.0,
        "trail_atr_mult": 2.5,
        "htf_ema": 50,
    }

    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        out = self.with_atr(df, self.p["atr_window"])
        out = self.with_htf_trend(out, cfg, self.p["htf_ema"])
        inside = (out["high"] <= out["high"].shift(1)) & (out["low"] >= out["low"].shift(1))
        n = self.p["contraction_bars"]
        out["coiled"] = inside.rolling(n, min_periods=n).sum() == n
        out["coil_high"] = out["high"].rolling(n + 1, min_periods=n + 1).max()
        out["coil_low"] = out["low"].rolling(n + 1, min_periods=n + 1).min()
        return out

    def signal(self, df: pd.DataFrame, i: int) -> Signal | None:
        a = self.a
        close, atr = a["close"][i], a["atr"][i]
        coiled = a["coiled"][i - 1] if i > 0 else False
        hi, lo = a["coil_high"][i - 1] if i > 0 else float("nan"), \
                 a["coil_low"][i - 1] if i > 0 else float("nan")
        htf_ema, htf_close = a["htf_ema"][i], a["htf_close"][i]
        if not clean(close, atr, hi, lo, htf_ema, htf_close) or atr <= 0 or not coiled:
            return None
        if (hi - lo) > self.p["max_range_atr"] * atr:
            return None

        buf = self.p["stop_buffer_atr"] * atr
        # Trade the break only in the direction the higher timeframe allows.
        if close > hi and htf_close > htf_ema:
            stop = lo - buf
            risk = close - stop
            if risk <= 0:
                return None
            return entry(Side.LONG, close, stop, close + self.p["target_r"] * risk,
                         trail_atr_mult=self.p["trail_atr_mult"],
                         reason=f"break above a {self.p['contraction_bars']}-bar coil")
        if close < lo and htf_close < htf_ema:
            stop = hi + buf
            risk = stop - close
            if risk <= 0:
                return None
            return entry(Side.SHORT, close, stop, close - self.p["target_r"] * risk,
                         trail_atr_mult=self.p["trail_atr_mult"],
                         reason=f"break below a {self.p['contraction_bars']}-bar coil")
        return None
