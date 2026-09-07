"""A coin flip with the same stop and target as everyone else.

This exists to make win rates readable. Win rate is mostly geometry: a target
close to entry is reached often, a far one rarely, and that is true of a
strategy with no information at all. Quoting "70% winners" without saying at
what reward-to-risk is therefore quoting nothing -- a coin flip taking 0.3R
against a 1R stop wins about three quarters of the time and still loses money.

So this is the null model. Whatever win rate it produces at a given target is
the part that came free from the geometry; only the distance a real strategy
puts between itself and this line is information.

Direction comes from a hash of the bar's timestamp, which makes it arbitrary
with respect to the market but identical on every run -- a seeded generator
would drift between processes and make results irreproducible.
"""

from __future__ import annotations

import zlib

import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.types import Side
from .base import Strategy, clean, entry, register


@register
class RandomEntry(Strategy):
    name = "random_entry"
    # It claims no edge anywhere, and the regime harness should agree.
    expects_edge_in = ()
    expects_no_edge_in = ()
    default_params = {
        "atr_window": 14,
        "stop_atr_mult": 2.0,
        "target_r": 2.0,
        "trail_atr_mult": 0.0,
        "every_n_bars": 8,      # thin it out so the risk limits do not bind
    }

    @property
    def warmup_bars(self) -> int:
        return 60

    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        out = self.with_atr(df, self.p["atr_window"])
        stamps = out.index.view("int64") // 10**9
        out["coin"] = [zlib.crc32(str(int(t)).encode()) & 1 for t in stamps]
        return out

    def signal(self, df: pd.DataFrame, i: int):
        if i % self.p["every_n_bars"]:
            return None
        a = self.a
        close, atr = a["close"][i], a["atr"][i]
        if not clean(close, atr) or atr <= 0:
            return None
        offset = self.p["stop_atr_mult"] * atr
        if a["coin"][i]:
            return entry(Side.LONG, close, close - offset,
                         close + self.p["target_r"] * offset,
                         trail_atr_mult=self.p["trail_atr_mult"],
                         reason="coin flip long")
        return entry(Side.SHORT, close, close + offset,
                     close - self.p["target_r"] * offset,
                     trail_atr_mult=self.p["trail_atr_mult"],
                     reason="coin flip short")
