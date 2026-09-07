"""Core value objects shared by data, strategies, backtest and live loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"

    @property
    def sign(self) -> int:
        return 1 if self is Side.LONG else -1

    @property
    def opposite(self) -> "Side":
        return Side.SHORT if self is Side.LONG else Side.LONG


class ExitReason(str, Enum):
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TRAILING_STOP = "trailing_stop"
    SIGNAL = "signal"
    MAX_HOLD = "max_hold"
    END_OF_DATA = "end_of_data"
    KILL_SWITCH = "kill_switch"


@dataclass(frozen=True, slots=True)
class Signal:
    """A strategy's intent to open a position, expressed in price terms.

    Sizing is deliberately absent: the risk manager derives it from the
    distance between entry and stop, so a strategy can never size a trade.
    """

    side: Side
    stop_loss: float
    take_profit: float | None = None
    reason: str = ""
    trail_atr_mult: float | None = None

    def __post_init__(self) -> None:
        if self.stop_loss <= 0:
            raise ValueError("stop_loss must be positive")
        if self.take_profit is not None and self.take_profit <= 0:
            raise ValueError("take_profit must be positive")


@dataclass(slots=True)
class Position:
    symbol: str
    side: Side
    entry_time: datetime
    entry_price: float
    qty: float
    stop_loss: float
    take_profit: float | None
    trail_atr_mult: float | None = None
    entry_fee: float = 0.0
    risk_amount: float = 0.0
    reason: str = ""
    extreme_price: float = 0.0   # best price reached, drives the trailing stop
    trailing_active: bool = False
    mae: float = 0.0             # worst excursion while open, in price
    mfe: float = 0.0             # best excursion while open, in price

    # Scaling out. The position keeps its original risk_amount as the unit of
    # measure after a partial, so an R multiple stays comparable to a trade
    # that was never scaled -- otherwise every partial would silently redefine
    # what one R means.
    initial_qty: float = 0.0
    partial_price: float | None = None
    realised_pnl: float = 0.0    # banked by the partial, before the final exit
    realised_fees: float = 0.0
    # Rungs of an exit ladder not yet climbed, each (trigger price, share to
    # close, new stop or None). Kept sorted by distance from entry.
    ladder: list = field(default_factory=list)

    @property
    def notional(self) -> float:
        return self.qty * self.entry_price

    def unrealised(self, price: float) -> float:
        return (price - self.entry_price) * self.qty * self.side.sign


@dataclass(slots=True)
class Trade:
    """A closed round trip. `r_multiple` is the honest performance unit."""

    symbol: str
    side: Side
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    qty: float
    gross_pnl: float
    fees: float
    risk_amount: float
    exit_reason: ExitReason
    reason: str = ""
    mae: float = 0.0  # maximum adverse excursion, in price
    mfe: float = 0.0  # maximum favourable excursion, in price

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.fees

    @property
    def r_multiple(self) -> float:
        if self.risk_amount <= 0:
            return 0.0
        return self.net_pnl / self.risk_amount

    @property
    def holding_time(self) -> timedelta:
        return self.exit_time - self.entry_time

    @property
    def is_win(self) -> bool:
        return self.net_pnl > 0


@dataclass(slots=True)
class EquityPoint:
    time: datetime
    equity: float
    open_positions: int = 0


@dataclass(slots=True)
class BacktestResult:
    strategy: str
    symbol: str
    interval: str
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[EquityPoint] = field(default_factory=list)
    start_equity: float = 0.0
    end_equity: float = 0.0
    bars: int = 0
    blocked_by_kill_switch: int = 0
    blocked_by_limits: int = 0
    rejections: dict[str, int] = field(default_factory=dict)
