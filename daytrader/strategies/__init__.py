"""Strategy package. Importing it registers every built-in strategy."""

from .base import Strategy, available, build, register  # noqa: F401
from . import ema_momentum, opening_range, vwap_reversion  # noqa: F401
