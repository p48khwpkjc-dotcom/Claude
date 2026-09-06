import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from daytrader.config import Config  # noqa: E402
from daytrader.core.types import Signal  # noqa: E402
from daytrader.strategies.base import Strategy  # noqa: E402


@pytest.fixture
def cfg() -> Config:
    c = Config()
    c.backtest.warmup_bars = 2
    c.risk.max_trades_per_day = 100
    c.risk.cooldown_after_losses = 100
    c.risk.min_stop_distance_pct = 0.0
    return c


def frame(rows) -> pd.DataFrame:
    """rows: list of (open, high, low, close) -- volume is irrelevant here."""
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="5min", tz="UTC")
    return pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c, "volume": 100.0} for o, h, l, c in rows],
        index=idx,
    )


class ScriptedStrategy(Strategy):
    """Fires a predetermined signal on a given bar. Keeps engine tests exact."""

    name = "scripted"
    default_params = {}

    def __init__(self, at: int, signal: Signal, atr: float = 0.0):
        super().__init__({})
        self.at = at
        self._signal = signal
        self._atr = atr

    @property
    def warmup_bars(self) -> int:
        return 1

    def prepare(self, df, cfg):
        out = df.copy()
        out["atr"] = self._atr
        return out

    def signal(self, df, i):
        return self._signal if i == self.at else None
