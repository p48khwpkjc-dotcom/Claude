"""Strategy package. Importing it registers every built-in strategy."""

from .base import Strategy, available, build, register  # noqa: F401
from . import (  # noqa: F401
    donchian_breakout,
    ema_momentum,
    failed_breakout,
    fair_value_gap,
    inside_bar_break,
    keltner_trend,
    liquidity_sweep,
    momentum_persistence,
    opening_range,
    order_block,
    random_entry,
    rsi_reversion,
    session_momentum,
    sigma_reversion,
    squeeze_breakout,
    trend_pullback,
    vol_expansion,
    vwap_reversion,
)
