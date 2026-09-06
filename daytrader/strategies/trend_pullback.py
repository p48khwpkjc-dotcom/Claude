"""Buy the pullback inside an established higher-timeframe trend.

The breakout strategies buy strength and pay for it: they enter where everyone
sees the same level, into the worst available price. This one waits for the
trend to give something back and enters on the retracement, which is a cheaper
fill for the same directional bet. The trend filter is deliberately strict --
the whole premise is that we are only ever trading with a move that already
exists.
"""

from __future__ import annotations

import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.types import Side, Signal
from .base import Strategy, clean, register


@register
class TrendPullback(Strategy):
    name = "trend_pullback"
    expects_edge_in = ("trending",)
    expects_no_edge_in = ("choppy",)
    default_params = {
        "htf_ema": 50,
        "pull_ema": 20,        # the level price has to come back to
        "atr_window": 14,
        "stop_atr_mult": 2.0,
        "target_r": 3.0,       # wide, because cost per R is the binding constraint
        "trail_atr_mult": 3.0,
        "min_htf_slope": 0.02,  # the trend has to actually be going somewhere
        "max_dist_atr": 0.5,    # how close to the EMA counts as "pulled back"
    }

    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        out = self.with_atr(df, self.p["atr_window"])
        out = self.with_htf_trend(out, cfg, self.p["htf_ema"])
        out["pull_ema"] = ind.ema(out["close"], self.p["pull_ema"])
        return out

    def signal(self, df: pd.DataFrame, i: int) -> Signal | None:
        a = self.a
        close, atr = a["close"][i], a["atr"][i]
        pull, htf_ema, htf_close = a["pull_ema"][i], a["htf_ema"][i], a["htf_close"][i]
        slope = a["htf_slope"][i]
        low, high = a["low"][i], a["high"][i]
        if not clean(close, atr, pull, htf_ema, htf_close, slope) or atr <= 0:
            return None

        dist = abs(close - pull) / atr
        if dist > self.p["max_dist_atr"]:
            return None

        offset = self.p["stop_atr_mult"] * atr
        up = htf_close > htf_ema and slope > self.p["min_htf_slope"]
        down = htf_close < htf_ema and slope < -self.p["min_htf_slope"]

        # The bar must dip to the EMA and close back above it: a touch that
        # holds, not a break that keeps going.
        if up and low <= pull and close > pull:
            return Signal(Side.LONG, close - offset, close + self.p["target_r"] * offset,
                          trail_atr_mult=self.p["trail_atr_mult"],
                          reason=f"pullback to EMA{self.p['pull_ema']} in an uptrend")
        if down and high >= pull and close < pull:
            return Signal(Side.SHORT, close + offset, close - self.p["target_r"] * offset,
                          trail_atr_mult=self.p["trail_atr_mult"],
                          reason=f"pullback to EMA{self.p['pull_ema']} in a downtrend")
        return None
