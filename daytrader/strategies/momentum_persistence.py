"""Buy the instrument that has already been going up the longest.

Momentum is the one anomaly with decades of out-of-sample evidence behind it,
and this is its simplest single-asset form: measure the trailing return over a
long window, skip the most recent stretch because short-term momentum reverses,
require the result to be strongly positive, and hold with a wide target.

Note what the windows mean in wall-clock terms, because they are counted in
bars and therefore change meaning with the timeframe. The defaults were written
for 1h candles, where `lookback` is a week. On 4h -- where this strategy
actually earns its keep -- the same numbers are a 28-day lookback skipping the
last 2 days, with a 4-day cooldown between entries. That is textbook one-month
momentum, not an intraday signal, and it is the reason this sits at the
opposite end of the frequency spectrum from everything else here: roughly four
or five trades per symbol per year. A strategy that trades rarely pays the fee
rarely, which is the whole problem on the shorter frames.
"""

from __future__ import annotations

import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.types import Side, Signal
from .base import Strategy, clean, entry, register


@register
class MomentumPersistence(Strategy):
    name = "momentum_persistence"
    expects_edge_in = ("trending",)
    expects_no_edge_in = ("choppy",)
    default_params = {
        "lookback": 168,        # bars: a week on 1h, 28 days on 4h
        "skip": 12,             # skip the latest bars; short-term momentum reverses
        "entry_z": 1.0,
        "ret_sd_window": 336,
        "atr_window": 14,
        "stop_atr_mult": 3.0,
        "target_r": 3.0,
        "trail_atr_mult": 4.0,
        "cooldown_bars": 24,    # do not re-enter the same move every bar (4 days on 4h)
    }

    @property
    def warmup_bars(self) -> int:
        return self.p["lookback"] + self.p["ret_sd_window"]

    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        out = self.with_atr(df, self.p["atr_window"])
        c = out["close"]
        mom = c.shift(self.p["skip"]) / c.shift(self.p["lookback"]) - 1.0
        out["mom"] = mom
        out["mom_sd"] = mom.rolling(self.p["ret_sd_window"], min_periods=60).std()
        out["bar_no"] = range(len(out))
        return out

    def bind(self, prepared: pd.DataFrame) -> None:
        super().bind(prepared)
        self._last_entry = -10**9

    def signal(self, df: pd.DataFrame, i: int) -> Signal | None:
        a = self.a
        close, atr, mom, sd = a["close"][i], a["atr"][i], a["mom"][i], a["mom_sd"][i]
        if not clean(close, atr, mom, sd) or atr <= 0 or sd <= 0:
            return None
        if i - getattr(self, "_last_entry", -10**9) < self.p["cooldown_bars"]:
            return None

        z = mom / sd
        offset = self.p["stop_atr_mult"] * atr
        if z >= self.p["entry_z"]:
            self._last_entry = i
            return entry(Side.LONG, close, close - offset, close + self.p["target_r"] * offset,
                         trail_atr_mult=self.p["trail_atr_mult"],
                         reason=f"weekly momentum at {z:.1f} sigma")
        if z <= -self.p["entry_z"]:
            self._last_entry = i
            return entry(Side.SHORT, close, close + offset, close - self.p["target_r"] * offset,
                         trail_atr_mult=self.p["trail_atr_mult"],
                         reason=f"weekly momentum at {z:.1f} sigma")
        return None
