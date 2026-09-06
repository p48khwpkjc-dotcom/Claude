"""Strategy interface and registry.

A strategy answers one question per bar: given everything up to and including
this closed bar, is there a trade, in which direction, and where is it wrong?
It states an invalidation level (the stop) and optionally a target. It never
decides size -- that belongs to the risk manager, which is the only place that
knows the account.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

import pandas as pd

from ..config import Config
from ..core import indicators as ind
from ..core.timeframe import align_to, resample_ohlcv
from ..core.types import Signal

_REGISTRY: dict[str, type["Strategy"]] = {}


def register(cls: type["Strategy"]) -> type["Strategy"]:
    _REGISTRY[cls.name] = cls
    return cls


def available() -> list[str]:
    return sorted(_REGISTRY)


def build(name: str, cfg: Config) -> "Strategy":
    if name not in _REGISTRY:
        raise KeyError(f"unknown strategy '{name}'. Available: {', '.join(available())}")
    return _REGISTRY[name](cfg.strategies.get(name, {}))


class Strategy(ABC):
    name: str = "base"
    default_params: dict[str, Any] = {}

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        unknown = set(params or {}) - set(self.default_params)
        if unknown:
            raise ValueError(f"{self.name}: unknown parameters {sorted(unknown)}")
        self.p = {**self.default_params, **(params or {})}

    @property
    def warmup_bars(self) -> int:
        """Bars discarded before trading, so no signal fires on a half-formed indicator."""
        return 200

    @abstractmethod
    def prepare(self, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
        """Return a copy of `df` with the indicator columns this strategy reads."""

    @abstractmethod
    def signal(self, df: pd.DataFrame, i: int) -> Signal | None:
        """Decide on bar `i`. Reading any row beyond `i` is a bug, not a shortcut."""

    # ------------------------------------------------------------- shared prep

    @staticmethod
    def with_atr(df: pd.DataFrame, window: int) -> pd.DataFrame:
        out = df.copy()
        out["atr"] = ind.atr(out["high"], out["low"], out["close"], window)
        return out

    @staticmethod
    def with_htf_trend(df: pd.DataFrame, cfg: Config, ema_span: int) -> pd.DataFrame:
        """Attach a higher-timeframe EMA and its slope, using closed HTF bars only."""
        out = df.copy()
        htf = resample_ohlcv(df, cfg.data.htf_interval)
        htf_ema = ind.ema(htf["close"], ema_span)
        out["htf_ema"] = align_to(htf_ema, out.index, cfg.data.htf_interval)
        out["htf_close"] = align_to(htf["close"], out.index, cfg.data.htf_interval)
        out["htf_slope"] = align_to(ind.slope(htf_ema, 6), out.index, cfg.data.htf_interval)
        return out


def clean(*values: float) -> bool:
    """True when every input is a usable number -- the warmup guard for signals."""
    return all(v == v and v not in (float("inf"), float("-inf")) for v in values)
