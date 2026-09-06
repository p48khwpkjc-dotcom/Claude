"""Position sizing and the hard limits that stop a bad day becoming a bad year.

The rules here are deliberately not overridable by a strategy. A strategy says
"long, stop here"; this module decides whether that trade happens at all and
how large it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from ..config import RiskConfig
from ..core.types import Side, Trade


@dataclass(slots=True)
class SizingResult:
    qty: float
    risk_amount: float
    notional: float
    capped_by_leverage: bool


class RiskRejection(str):
    """Why an entry was refused -- kept as text so reports can group them."""


class RiskManager:
    def __init__(self, cfg: RiskConfig, start_equity: float) -> None:
        self.cfg = cfg
        self.equity = start_equity
        self.day_start_equity = start_equity
        self.current_day: date | None = None
        self.trades_today = 0
        self.consecutive_losses = 0
        self.cooldown_until_bar = -1
        self.kill_switch_tripped = False
        self.rejections: dict[str, int] = {}

    # ---------------------------------------------------------------- day roll

    def on_bar(self, when: datetime, equity: float) -> None:
        """Advance daily state. Called once per bar, before any decision."""
        self.equity = equity
        day = when.date()
        if self.current_day != day:
            self.current_day = day
            self.day_start_equity = equity
            self.trades_today = 0
            self.kill_switch_tripped = False

        if not self.kill_switch_tripped and self.daily_loss_pct >= self.cfg.max_daily_loss_pct:
            self.kill_switch_tripped = True

    @property
    def daily_loss_pct(self) -> float:
        if self.day_start_equity <= 0:
            return 0.0
        return max(0.0, (self.day_start_equity - self.equity) / self.day_start_equity * 100.0)

    @property
    def should_flatten(self) -> bool:
        """A tripped kill switch closes what is open, it does not just stop new trades."""
        return self.kill_switch_tripped

    # ------------------------------------------------------------- entry gates

    def can_open(self, bar_index: int, open_positions: int) -> tuple[bool, str]:
        if self.kill_switch_tripped:
            return self._reject(f"daily loss limit {self.cfg.max_daily_loss_pct}% reached")
        if open_positions >= self.cfg.max_concurrent_positions:
            return self._reject("max concurrent positions")
        if self.trades_today >= self.cfg.max_trades_per_day:
            return self._reject("max trades per day")
        if bar_index < self.cooldown_until_bar:
            return self._reject(f"cooldown after {self.cfg.cooldown_after_losses} losses")
        return True, ""

    def _reject(self, reason: str) -> tuple[bool, str]:
        self.rejections[reason] = self.rejections.get(reason, 0) + 1
        return False, reason

    # ----------------------------------------------------------------- sizing

    def size(self, side: Side, entry_price: float, stop_price: float) -> SizingResult | str:
        """Convert a stop distance into a quantity, or return the reason not to trade."""
        if entry_price <= 0:
            return "invalid entry price"

        stop_distance = abs(entry_price - stop_price)
        stop_pct = stop_distance / entry_price * 100.0

        if side is Side.LONG and stop_price >= entry_price:
            return "long stop is not below entry"
        if side is Side.SHORT and stop_price <= entry_price:
            return "short stop is not above entry"
        if stop_pct < self.cfg.min_stop_distance_pct:
            return f"stop too tight ({stop_pct:.3f}%)"
        if stop_pct > self.cfg.max_stop_distance_pct:
            return f"stop too wide ({stop_pct:.2f}%)"

        intended_risk = self.equity * self.cfg.risk_per_trade_pct / 100.0
        qty = intended_risk / stop_distance

        # Never borrow beyond the configured leverage, even if that means
        # risking less than intended on a wide stop.
        max_notional = self.equity * self.cfg.max_leverage
        capped = qty * entry_price > max_notional
        if capped:
            qty = max_notional / entry_price

        if qty <= 0:
            return "computed size is zero"

        # Report the risk actually taken, not the risk intended -- otherwise
        # every R-multiple downstream is a fiction.
        return SizingResult(
            qty=qty,
            risk_amount=qty * stop_distance,
            notional=qty * entry_price,
            capped_by_leverage=capped,
        )

    # ---------------------------------------------------------------- feedback

    def on_opened(self) -> None:
        self.trades_today += 1

    def on_closed(self, trade: Trade, bar_index: int) -> None:
        if trade.is_win:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            if self.consecutive_losses >= self.cfg.cooldown_after_losses:
                self.cooldown_until_bar = bar_index + self.cfg.cooldown_bars
                self.consecutive_losses = 0
