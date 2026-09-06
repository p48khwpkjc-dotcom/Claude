"""Fade a move that is extreme relative to the instrument's own volatility.

RSI failed as a reversion trigger because it fires almost exclusively inside
trends (see the regime harness). This uses the size of the move in standard
deviations instead, which is scale-free and does not drift with the trend: an
n-sigma bar is rare by construction, whatever the market is doing. The trend
filter is inverted from the momentum strategies -- reversion is only taken when
the higher timeframe is *not* running.
"""

from __future__ import annotations

import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.types import Side, Signal
from .base import Strategy, clean, register


@register
class SigmaReversion(Strategy):
    name = "sigma_reversion"
    expects_edge_in = ("choppy",)
    expects_no_edge_in = ("trending",)
    default_params = {
        "ret_window": 96,
        "sigma": 2.5,           # how extreme the bar's return has to be
        "atr_window": 14,
        "stop_atr_mult": 2.0,
        "target_r": 2.0,
        "trail_atr_mult": 2.5,
        "htf_ema": 50,
        "max_htf_slope": 0.05,  # stay out of a running trend
    }

    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        out = self.with_atr(df, self.p["atr_window"])
        out = self.with_htf_trend(out, cfg, self.p["htf_ema"])
        ret = out["close"].pct_change()
        out["ret"] = ret
        out["ret_sd"] = ret.rolling(self.p["ret_window"], min_periods=30).std()
        out["mean_ref"] = ind.ema(out["close"], 20)
        return out

    def signal(self, df: pd.DataFrame, i: int) -> Signal | None:
        a = self.a
        close, atr = a["close"][i], a["atr"][i]
        ret, sd, slope = a["ret"][i], a["ret_sd"][i], a["htf_slope"][i]
        if not clean(close, atr, ret, sd, slope) or atr <= 0 or sd <= 0:
            return None
        if abs(slope) > self.p["max_htf_slope"]:
            return None

        z = ret / sd
        offset = self.p["stop_atr_mult"] * atr
        if z <= -self.p["sigma"]:
            return Signal(Side.LONG, close - offset, close + self.p["target_r"] * offset,
                          trail_atr_mult=self.p["trail_atr_mult"],
                          reason=f"{z:.1f} sigma down bar in a flat regime")
        if z >= self.p["sigma"]:
            return Signal(Side.SHORT, close + offset, close - self.p["target_r"] * offset,
                          trail_atr_mult=self.p["trail_atr_mult"],
                          reason=f"{z:.1f} sigma up bar in a flat regime")
        return None
