"""Carry the previous session's direction into the next one.

Crypto trades around the clock, but the participants do not: the UTC day still
splits into an Asian, a European and a US block with different flow. This tests
whether a block that closed strongly hands that direction to the block after
it. It is the only strategy here whose trigger is the clock rather than the
chart, which makes it a useful check on whether the others are really finding
structure or just re-reading the same price series.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.types import Side, Signal
from .base import Strategy, clean, register

# UTC hours at which a block begins.
BLOCK_STARTS = (0, 8, 16)


@register
class SessionMomentum(Strategy):
    name = "session_momentum"
    expects_edge_in = ("trending",)
    expects_no_edge_in = ("choppy",)
    default_params = {
        "atr_window": 14,
        "stop_atr_mult": 2.0,
        "target_r": 2.0,
        "trail_atr_mult": 3.0,
        "min_move_atr": 1.0,    # the prior block has to have actually moved
    }

    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        out = self.with_atr(df, self.p["atr_window"])
        hours = out.index.hour
        # Label each bar with the block it belongs to, then measure the move of
        # the block that closed most recently.
        block = np.searchsorted(BLOCK_STARTS, hours, side="right") - 1
        block_id = out.index.normalize().astype("int64") // 10**9 + block * 10**6
        out["block_id"] = block_id
        first = out.groupby("block_id")["open"].transform("first")
        out["block_move"] = out["close"] - first
        # The completed block's move, carried onto the bars of the next one.
        done = out.groupby("block_id")["block_move"].last()
        out["prev_move"] = pd.Series(done.shift(1).reindex(out["block_id"]).to_numpy(),
                                     index=out.index)
        out["is_block_open"] = out["block_id"] != pd.Series(block_id, index=out.index).shift(1)
        return out

    def signal(self, df: pd.DataFrame, i: int) -> Signal | None:
        a = self.a
        close, atr = a["close"][i], a["atr"][i]
        prev, is_open = a["prev_move"][i], a["is_block_open"][i]
        if not clean(close, atr, prev) or atr <= 0 or not is_open:
            return None
        if abs(prev) < self.p["min_move_atr"] * atr:
            return None

        offset = self.p["stop_atr_mult"] * atr
        if prev > 0:
            return Signal(Side.LONG, close - offset, close + self.p["target_r"] * offset,
                          trail_atr_mult=self.p["trail_atr_mult"],
                          reason=f"prior 8h block closed {prev / atr:.1f} ATR up")
        return Signal(Side.SHORT, close + offset, close - self.p["target_r"] * offset,
                      trail_atr_mult=self.p["trail_atr_mult"],
                      reason=f"prior 8h block closed {abs(prev) / atr:.1f} ATR down")
