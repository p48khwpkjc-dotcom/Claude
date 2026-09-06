"""Session-VWAP mean reversion.

Thesis: intraday crypto spends most of its time oscillating around the volume
weighted average price of the current UTC day. Stretches far from it, made on
exhausted momentum, tend to snap back. Small, frequent winners; the way this
strategy dies is a trending day where price never comes back, so the trend
filter that suppresses it in a strong trend is not optional garnish.
"""

from __future__ import annotations

import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.types import Side, Signal
from .base import Strategy, clean, register


@register
class VwapReversion(Strategy):
    name = "vwap_reversion"
    expects_edge_in = ("choppy",)
    expects_no_edge_in = ("trending",)
    default_params = {
        "band_mult": 1.8,
        "rsi_window": 14,
        "rsi_long_max": 38,
        "rsi_short_min": 62,
        "atr_window": 14,
        "stop_atr_mult": 1.2,
        "min_target_r": 1.0,
        "htf_ema": 50,
        "max_trend_slope": 0.05,
    }

    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        out = self.with_atr(df, self.p["atr_window"])
        out = self.with_htf_trend(out, cfg, self.p["htf_ema"])
        out["vwap"] = ind.session_vwap(out)
        lower, _, upper = ind.session_vwap_bands(out, out["vwap"], self.p["band_mult"])
        out["vwap_lower"], out["vwap_upper"] = lower, upper
        out["rsi"] = ind.rsi(out["close"], self.p["rsi_window"])
        return out

    def signal(self, df: pd.DataFrame, i: int) -> Signal | None:
        a = self.a
        close, atr, vwap = a["close"][i], a["atr"][i], a["vwap"][i]
        lower, upper = a["vwap_lower"][i], a["vwap_upper"][i]
        rsi, rsi_prev = a["rsi"][i], a["rsi"][i - 1]
        slope = a["htf_slope"][i]

        if not clean(close, atr, vwap, lower, upper, rsi, rsi_prev, slope) or atr <= 0:
            return None

        # Mean reversion is a bet against continuation. Inside a strong
        # higher-timeframe trend that bet is simply wrong, so stand aside.
        if abs(slope) > self.p["max_trend_slope"]:
            return None

        if close < lower and rsi < self.p["rsi_long_max"] and rsi > rsi_prev:
            stop = close - self.p["stop_atr_mult"] * atr
            return self._build(Side.LONG, close, stop, target=vwap,
                               why=f"{(vwap/close-1)*100:.2f}% below VWAP, RSI {rsi:.0f} turning up")

        if close > upper and rsi > self.p["rsi_short_min"] and rsi < rsi_prev:
            stop = close + self.p["stop_atr_mult"] * atr
            return self._build(Side.SHORT, close, stop, target=vwap,
                               why=f"{(close/vwap-1)*100:.2f}% above VWAP, RSI {rsi:.0f} rolling over")
        return None

    def _build(self, side: Side, price: float, stop: float, target: float, why: str) -> Signal | None:
        risk = abs(price - stop)
        reward = abs(target - price)
        if risk <= 0 or reward / risk < self.p["min_target_r"]:
            return None  # the snap-back is not worth the stop it needs
        return Signal(side=side, stop_loss=stop, take_profit=target, reason=why)
