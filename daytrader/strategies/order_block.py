"""Order block: enter on the retest of the last opposing candle before a move.

The published definition is that an impulsive move leaves behind the candle
that preceded it -- the last down candle before a rally, the last up candle
before a decline -- and that price returns to that candle's range before
continuing. Marking it requires deciding what counts as impulsive, which is
where the discretion in the discretionary version lives; here it is a
threshold in ATR so the same chart always produces the same blocks.
"""

from __future__ import annotations

import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.types import Side
from .base import Strategy, clean, entry, register


@register
class OrderBlock(Strategy):
    name = "order_block"
    expects_edge_in = ("trending",)
    expects_no_edge_in = ("choppy",)
    default_params = {
        "atr_window": 14,
        "impulse_bars": 3,
        "impulse_atr": 2.0,      # size of the move that makes a block
        "valid_bars": 24,
        "stop_buffer_atr": 0.25,
        "target_r": 2.0,
        "trail_atr_mult": 0.0,
    }

    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        out = self.with_atr(df, self.p["atr_window"])
        n = self.p["impulse_bars"]
        out["move"] = out["close"] - out["close"].shift(n)
        out["is_down"] = out["close"] < out["open"]
        out["is_up"] = out["close"] > out["open"]
        return out

    def bind(self, prepared: pd.DataFrame) -> None:
        super().bind(prepared)
        self._blocks: list[tuple[int, str, float, float]] = []

    def signal(self, df: pd.DataFrame, i: int):
        a = self.a
        close, high, low, atr = a["close"][i], a["high"][i], a["low"][i], a["atr"][i]
        move = a["move"][i]
        if not clean(close, atr, move) or atr <= 0:
            return None
        n = self.p["impulse_bars"]

        # An impulse that ended on this bar leaves the last opposing candle
        # before it as the block. Look back only, never forward.
        if move >= self.p["impulse_atr"] * atr:
            for k in range(i - n, max(-1, i - n - 6), -1):
                if k >= 0 and a["is_down"][k]:
                    self._blocks.append((i, "bull", a["low"][k], a["high"][k]))
                    break
        elif move <= -self.p["impulse_atr"] * atr:
            for k in range(i - n, max(-1, i - n - 6), -1):
                if k >= 0 and a["is_up"][k]:
                    self._blocks.append((i, "bear", a["low"][k], a["high"][k]))
                    break
        self._blocks = [b for b in self._blocks if i - b[0] <= self.p["valid_bars"]]

        buf = self.p["stop_buffer_atr"] * atr
        for k, (born, kind, lo, hi) in enumerate(self._blocks):
            if born >= i or not clean(lo, hi):
                continue
            if kind == "bull" and low <= hi and close > lo:
                stop = lo - buf
                risk = close - stop
                if risk <= 0:
                    continue
                del self._blocks[k]
                return entry(Side.LONG, close, stop, close + self.p["target_r"] * risk,
                             trail_atr_mult=self.p["trail_atr_mult"],
                             reason=f"retest of a bullish order block {lo:.4f}-{hi:.4f}")
            if kind == "bear" and high >= lo and close < hi:
                stop = hi + buf
                risk = stop - close
                if risk <= 0:
                    continue
                del self._blocks[k]
                return entry(Side.SHORT, close, stop, close - self.p["target_r"] * risk,
                             trail_atr_mult=self.p["trail_atr_mult"],
                             reason=f"retest of a bearish order block {lo:.4f}-{hi:.4f}")
        return None
