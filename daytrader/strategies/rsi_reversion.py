"""Plain RSI mean reversion, with no VWAP and no trend filter.

The control for the reversion family, mirroring what donchian_breakout does
for the trend family: if vwap_reversion cannot beat this, its extra machinery
is not earning its keep.
"""

from __future__ import annotations

import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.types import Side, Signal
from .base import Strategy, clean, register


@register
class RsiReversion(Strategy):
    name = "rsi_reversion"
    expects_edge_in = ("choppy",)
    expects_no_edge_in = ("trending",)
    default_params = {
        "rsi_window": 14,
        "oversold": 30,
        "overbought": 70,
        "atr_window": 14,
        "stop_atr_mult": 2.0,
        "target_atr_mult": 2.0,
        "exit_rsi": 50,
    }

    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        out = self.with_atr(df, self.p["atr_window"])
        out["rsi"] = ind.rsi(out["close"], self.p["rsi_window"])
        return out

    def signal(self, df: pd.DataFrame, i: int) -> Signal | None:
        a = self.a
        close, atr = a["close"][i], a["atr"][i]
        rsi, rsi_prev = a["rsi"][i], a["rsi"][i - 1]
        if not clean(close, atr, rsi, rsi_prev) or atr <= 0:
            return None

        stop = self.p["stop_atr_mult"] * atr
        target = self.p["target_atr_mult"] * atr

        # Wait for the turn: an oversold reading that is still falling is a
        # falling knife, not a signal.
        if rsi < self.p["oversold"] and rsi > rsi_prev:
            return Signal(Side.LONG, close - stop, close + target,
                          reason=f"RSI {rsi:.0f} turning up from oversold")
        if rsi > self.p["overbought"] and rsi < rsi_prev:
            return Signal(Side.SHORT, close + stop, close - target,
                          reason=f"RSI {rsi:.0f} rolling over from overbought")
        return None
