"""Bollinger squeeze into volatility expansion.

Thesis: volatility is mean reverting even where price is not. A band width in
the lowest part of its own recent range is a coiled market, and the first
decisive close outside the bands is the release. This is the setup BTC was
sitting in on 2026-09-06 -- 0.42% band width on 5m -- which is what prompted
adding it to the candidate field.
"""

from __future__ import annotations

import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.types import Side, Signal
from .base import Strategy, clean, register


@register
class SqueezeBreakout(Strategy):
    name = "squeeze_breakout"
    expects_edge_in = ("trending",)
    expects_no_edge_in = ()
    default_params = {
        "bb_window": 20,
        "bb_mult": 2.0,
        "squeeze_lookback": 96,     # eight hours of 5m bars
        "squeeze_percentile": 0.25,  # band width in its own lowest quarter
        "atr_window": 14,
        "stop_atr_mult": 1.5,
        "target_r": 2.0,
        "trail_atr_mult": 2.5,
        "min_volume_ratio": 1.2,
    }

    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        out = self.with_atr(df, self.p["atr_window"])
        mid = ind.sma(out["close"], self.p["bb_window"])
        sd = out["close"].rolling(self.p["bb_window"], min_periods=self.p["bb_window"]).std()
        out["bb_upper"] = mid + self.p["bb_mult"] * sd
        out["bb_lower"] = mid - self.p["bb_mult"] * sd
        width = (out["bb_upper"] - out["bb_lower"]) / mid

        # Rank today's width against its own recent history, using only
        # completed bars so the ranking cannot see its own future.
        out["width_rank"] = width.shift(1).rolling(
            self.p["squeeze_lookback"], min_periods=self.p["squeeze_lookback"]
        ).rank(pct=True)
        out["vol_ratio"] = ind.volume_ratio(out["volume"], 20)
        return out

    @property
    def warmup_bars(self) -> int:
        return max(200, self.p["squeeze_lookback"] + self.p["bb_window"] + 5)

    def signal(self, df: pd.DataFrame, i: int) -> Signal | None:
        a = self.a
        close, atr = a["close"][i], a["atr"][i]
        upper, lower = a["bb_upper"][i], a["bb_lower"][i]
        rank, vol_ratio = a["width_rank"][i], a["vol_ratio"][i]
        if not clean(close, atr, upper, lower, rank, vol_ratio) or atr <= 0:
            return None
        if rank > self.p["squeeze_percentile"] or vol_ratio < self.p["min_volume_ratio"]:
            return None

        offset = self.p["stop_atr_mult"] * atr
        if close > upper:
            return Signal(Side.LONG, close - offset, close + self.p["target_r"] * offset,
                          trail_atr_mult=self.p["trail_atr_mult"],
                          reason=f"squeeze released upward, width in lowest {rank:.0%}")
        if close < lower:
            return Signal(Side.SHORT, close + offset, close - self.p["target_r"] * offset,
                          trail_atr_mult=self.p["trail_atr_mult"],
                          reason=f"squeeze released downward, width in lowest {rank:.0%}")
        return None
