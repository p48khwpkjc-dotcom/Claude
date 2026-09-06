"""EMA-cross momentum, filtered by the higher timeframe.

Thesis: trade only in the direction the 1h chart is already going, enter when
the 5m chart agrees, hold with a trailing stop and let the occasional runner
pay for the many small losses. Low hit rate by design -- judge it on profit
factor, never on win rate.
"""

from __future__ import annotations

import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.types import Side, Signal
from .base import Strategy, clean, register


@register
class EmaMomentum(Strategy):
    name = "ema_momentum"
    expects_edge_in = ("trending",)
    expects_no_edge_in = ("choppy",)
    default_params = {
        "fast": 12,
        "slow": 34,
        "atr_window": 14,
        "stop_atr_mult": 1.5,
        "target_r": 2.0,
        "min_volume_ratio": 1.0,
        "htf_ema": 50,
        "trail_atr_mult": 2.5,
    }

    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        out = self.with_atr(df, self.p["atr_window"])
        out = self.with_htf_trend(out, cfg, self.p["htf_ema"])
        out["ema_fast"] = ind.ema(out["close"], self.p["fast"])
        out["ema_slow"] = ind.ema(out["close"], self.p["slow"])
        out["vol_ratio"] = ind.volume_ratio(out["volume"], 20)
        return out

    def signal(self, df: pd.DataFrame, i: int) -> Signal | None:
        a = self.a
        fast, slow = a["ema_fast"][i], a["ema_slow"][i]
        fast_prev, slow_prev = a["ema_fast"][i - 1], a["ema_slow"][i - 1]
        close, atr = a["close"][i], a["atr"][i]
        htf_close, htf_ema = a["htf_close"][i], a["htf_ema"][i]
        vol_ratio = a["vol_ratio"][i]

        if not clean(fast, slow, fast_prev, slow_prev, close, atr, htf_close, htf_ema, vol_ratio):
            return None
        if atr <= 0 or vol_ratio < self.p["min_volume_ratio"]:
            return None

        offset = self.p["stop_atr_mult"] * atr
        crossed_up = fast > slow and fast_prev <= slow_prev
        crossed_down = fast < slow and fast_prev >= slow_prev

        # Only with the higher timeframe, never against it.
        if crossed_up and htf_close > htf_ema:
            return Signal(
                side=Side.LONG,
                stop_loss=close - offset,
                take_profit=close + self.p["target_r"] * offset,
                trail_atr_mult=self.p["trail_atr_mult"],
                reason=f"EMA{self.p['fast']}/{self.p['slow']} cross up, 1h above EMA{self.p['htf_ema']}",
            )
        if crossed_down and htf_close < htf_ema:
            return Signal(
                side=Side.SHORT,
                stop_loss=close + offset,
                take_profit=close - self.p["target_r"] * offset,
                trail_atr_mult=self.p["trail_atr_mult"],
                reason=f"EMA{self.p['fast']}/{self.p['slow']} cross down, 1h below EMA{self.p['htf_ema']}",
            )
        return None
