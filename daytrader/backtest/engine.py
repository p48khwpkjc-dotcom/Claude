"""Bar-by-bar backtest engine.

Four rules keep the results honest:

1. A signal formed on bar i is filled at the **open of bar i+1**. Filling at
   the close of the bar that produced the signal is the single most common way
   a backtest invents an edge that does not exist.
2. When a bar's range contains both the stop and the target, the **stop** is
   assumed to have been hit first. Without tick data you cannot know, and the
   pessimistic reading is the only one that does not flatter you.
3. A trailing stop is tightened only after the bar has been resolved, so the
   new level can protect the next bar but never the one that created it.
4. Every fill pays a fee and pays slippage against its own direction. Stops
   pay more, because a stop is a market order placed in a hurry, and a gap
   through the level fills at the open rather than at the level.

The engine trades one symbol with at most one open position. Running several
symbols means several engines; portfolio-level netting is deliberately out of
scope until a strategy earns it.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..config import Config
from ..core.types import (
    BacktestResult,
    EquityPoint,
    ExitReason,
    Position,
    Side,
    Signal,
    Trade,
)
from ..risk.manager import RiskManager, SizingResult
from ..strategies.base import Strategy

log = logging.getLogger(__name__)


class BacktestEngine:
    def __init__(self, cfg: Config, strategy: Strategy, symbol: str) -> None:
        self.cfg = cfg
        self.strategy = strategy
        self.symbol = symbol
        self.fee_rate = cfg.execution.taker_fee_pct / 100.0
        self.slip = cfg.execution.slippage_bps / 10_000.0
        self.stop_slip = cfg.execution.stop_slippage_bps / 10_000.0

    # ------------------------------------------------------------------ fills

    def _entry_fill(self, side: Side, open_price: float) -> float:
        return open_price * (1 + self.slip * side.sign)

    def _market_exit_fill(self, side: Side, price: float) -> float:
        return price * (1 - self.slip * side.sign)

    def _stop_fill(self, side: Side, stop: float, bar_open: float) -> float:
        """A gap through the stop fills at the open, not at the wished-for level."""
        if side is Side.LONG:
            return min(stop, bar_open) * (1 - self.stop_slip)
        return max(stop, bar_open) * (1 + self.stop_slip)

    def _fee(self, price: float, qty: float) -> float:
        return abs(price * qty) * self.fee_rate

    # ------------------------------------------------------------------- loop

    def run(self, df: pd.DataFrame) -> BacktestResult:
        prepared = self.strategy.prepare(df, self.cfg)
        self.strategy.bind(prepared)
        atr = prepared["atr"].to_numpy() if "atr" in prepared.columns else np.zeros(len(prepared))
        risk = RiskManager(self.cfg.risk, self.cfg.account.start_equity)

        result = BacktestResult(
            strategy=self.strategy.name,
            symbol=self.symbol,
            interval=self.cfg.data.interval,
            start_equity=self.cfg.account.start_equity,
            bars=len(prepared),
        )

        cash = self.cfg.account.start_equity
        position: Position | None = None
        pending: Signal | None = None
        max_hold = pd.Timedelta(hours=self.cfg.risk.max_hold_hours)

        times = prepared.index
        o = prepared["open"].to_numpy()
        h = prepared["high"].to_numpy()
        l = prepared["low"].to_numpy()
        c = prepared["close"].to_numpy()

        warmup = min(max(self.cfg.backtest.warmup_bars, self.strategy.warmup_bars), len(prepared))

        for i in range(warmup, len(prepared)):
            now = times[i]

            # 1. Fill the entry decided on the previous bar, at this bar's open.
            if pending is not None:
                position = self._open(pending, o[i], now, risk)
                if position is not None:
                    cash -= position.entry_fee
                    risk.on_opened()
                pending = None

            # 2. Resolve an open position against this bar's range.
            if position is not None:
                trade = self._check_exit(position, i, o, h, l, c, now, max_hold, atr)
                if trade is not None:
                    cash += trade.gross_pnl - (trade.fees - position.entry_fee)
                    result.trades.append(trade)
                    risk.on_closed(trade, i)
                    position = None

            # 3. Mark to market, then show the risk manager the day's damage.
            equity = cash + (position.unrealised(c[i]) if position else 0.0)
            risk.on_bar(now.to_pydatetime(), equity)
            result.equity_curve.append(
                EquityPoint(now.to_pydatetime(), equity, 1 if position else 0)
            )

            # 4. A tripped kill switch flattens; it does not merely block new trades.
            if position is not None and risk.should_flatten:
                trade = self._close(position, self._market_exit_fill(position.side, c[i]),
                                    now, ExitReason.KILL_SWITCH, h[i], l[i])
                cash += trade.gross_pnl - (trade.fees - position.entry_fee)
                result.trades.append(trade)
                risk.on_closed(trade, i)
                result.blocked_by_kill_switch += 1
                position = None
                continue

            # 5. Look for a new entry, to be filled on the next bar's open.
            if position is None:
                allowed, _ = risk.can_open(i, 0)
                if not allowed:
                    result.blocked_by_limits += 1
                    continue
                pending = self.strategy.signal(prepared, i)

        # 6. Close whatever is still open at the last known price.
        if position is not None:
            last = len(prepared) - 1
            trade = self._close(position, self._market_exit_fill(position.side, c[last]),
                                times[last], ExitReason.END_OF_DATA, h[last], l[last])
            cash += trade.gross_pnl - (trade.fees - position.entry_fee)
            result.trades.append(trade)
            if result.equity_curve:
                result.equity_curve[-1].equity = cash

        result.end_equity = result.equity_curve[-1].equity if result.equity_curve else cash
        result.rejections = dict(risk.rejections)
        return result

    # -------------------------------------------------------------- open/close

    def _open(self, signal: Signal, bar_open: float, now, risk: RiskManager) -> Position | None:
        entry = self._entry_fill(signal.side, bar_open)
        sized = risk.size(signal.side, entry, signal.stop_loss)
        if isinstance(sized, str):
            risk.rejections[sized] = risk.rejections.get(sized, 0) + 1
            return None
        assert isinstance(sized, SizingResult)
        return Position(
            symbol=self.symbol,
            side=signal.side,
            entry_time=now.to_pydatetime(),
            entry_price=entry,
            qty=sized.qty,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            trail_atr_mult=signal.trail_atr_mult,
            entry_fee=self._fee(entry, sized.qty),
            risk_amount=sized.risk_amount,
            reason=signal.reason,
            extreme_price=entry,
            initial_qty=sized.qty,
            partial_price=self._partial_level(signal.side, entry, signal.stop_loss),
            ladder=self._build_ladder(signal, entry),
        )

    def _build_ladder(self, signal: Signal, entry: float) -> list:
        """Turn the configured rungs into price levels for this trade.

        Everything is expressed as a fraction of the entry-to-target distance,
        so a plan reads the same whatever the target happens to be. Without a
        target there is no such distance and the ladder cannot exist.
        """
        rungs = self.cfg.execution.exit_ladder
        if not rungs or signal.take_profit is None:
            return []
        span = (signal.take_profit - entry) * signal.side.sign
        if span <= 0:
            return []
        out = []
        for rung in rungs:
            at = float(rung["at_tp_frac"])
            trigger = entry + signal.side.sign * at * span
            stop_frac = rung.get("stop_to_tp_frac")
            new_stop = None if stop_frac is None else \
                entry + signal.side.sign * float(stop_frac) * span
            out.append((at, trigger, float(rung.get("close_frac", 0.0)), new_stop))
        out.sort(key=lambda r: r[0])
        return out

    def _partial_level(self, side: Side, entry: float, stop: float) -> float | None:
        """Price at which part of the position comes off, or None if disabled."""
        at_r = self.cfg.execution.partial_at_r
        if at_r <= 0:
            return None
        risk = abs(entry - stop)
        if risk <= 0:
            return None
        return entry + side.sign * at_r * risk

    def _check_exit(self, pos: Position, i, o, h, l, c, now, max_hold, atr) -> Trade | None:
        high, low, bar_open = h[i], l[i], o[i]

        if pos.side is Side.LONG:
            hit_stop = low <= pos.stop_loss
            hit_target = pos.take_profit is not None and high >= pos.take_profit
        else:
            hit_stop = high >= pos.stop_loss
            hit_target = pos.take_profit is not None and low <= pos.take_profit

        if hit_stop:  # ties go to the stop
            reason = ExitReason.TRAILING_STOP if pos.trailing_active else ExitReason.STOP_LOSS
            return self._close(pos, self._stop_fill(pos.side, pos.stop_loss, bar_open),
                               now, reason, high, low)

        # The partial sits nearer than the target, so within a bar that reaches
        # both it fills first. It is checked after the stop for the same reason
        # the target is: without tick data the pessimistic order is the only one
        # that cannot flatter the result.
        if pos.partial_price is not None:
            reached = high >= pos.partial_price if pos.side is Side.LONG \
                else low <= pos.partial_price
            if reached:
                self._take_partial(pos)

        # Rungs are climbed in order within the bar: a bar that reaches the
        # second rung has passed the first, so the first still fires and its
        # stop still moves, exactly as it would have live.
        while pos.ladder:
            _, trigger, close_frac, new_stop = pos.ladder[0]
            reached = high >= trigger if pos.side is Side.LONG else low <= trigger
            if not reached:
                break
            pos.ladder.pop(0)
            if close_frac > 0:
                self._sell_part(pos, trigger, close_frac)
            if new_stop is not None:
                pos.stop_loss = new_stop
            if pos.qty <= 0:
                return self._close(pos, trigger, now, ExitReason.TAKE_PROFIT, high, low)

        if hit_target:
            return self._close(pos, pos.take_profit, now, ExitReason.TAKE_PROFIT, high, low)

        if now.to_pydatetime() - pos.entry_time >= max_hold:
            return self._close(pos, self._market_exit_fill(pos.side, c[i]),
                               now, ExitReason.MAX_HOLD, high, low)

        # Bar survived: record the excursion and only now tighten the trail.
        pos.extreme_price = max(pos.extreme_price, high) if pos.side is Side.LONG \
            else min(pos.extreme_price, low)
        pos.mae = min(pos.mae, (low - pos.entry_price) * pos.side.sign)
        pos.mfe = max(pos.mfe, (high - pos.entry_price) * pos.side.sign)

        if pos.trail_atr_mult is not None and atr[i] > 0:
            offset = pos.trail_atr_mult * atr[i]
            if pos.side is Side.LONG:
                new_stop = pos.extreme_price - offset
                if new_stop > pos.stop_loss:
                    pos.stop_loss, pos.trailing_active = new_stop, True
            else:
                new_stop = pos.extreme_price + offset
                if new_stop < pos.stop_loss:
                    pos.stop_loss, pos.trailing_active = new_stop, True
        return None

    def _sell_part(self, pos: Position, level: float, frac: float) -> None:
        """Bank `frac` of what is still open at `level`, paying its own costs."""
        qty = pos.qty * min(max(frac, 0.0), 1.0)
        if qty <= 0:
            return
        fill = self._market_exit_fill(pos.side, level)
        pos.realised_pnl += (fill - pos.entry_price) * qty * pos.side.sign
        pos.realised_fees += self._fee(fill, qty)
        pos.qty -= qty

    def _take_partial(self, pos: Position) -> None:
        """Bank part of the position at the scale-out level and shrink the rest.

        The banked leg pays its own exit fee and slippage. Total exited notional
        is unchanged by splitting the exit in two, so this costs no more in fees
        than a single exit would -- what it changes is the shape of the outcome,
        not the cost of it.
        """
        self._sell_part(pos, pos.partial_price, self.cfg.execution.partial_fraction)
        pos.partial_price = None            # it only fires once
        if self.cfg.execution.breakeven_after_partial:
            # The classic follow-up: the remainder can no longer lose. It also
            # can no longer survive a normal retracement, which is the trade-off
            # the win rate hides.
            pos.stop_loss = pos.entry_price

    def _close(self, pos: Position, exit_price: float, now, reason: ExitReason,
               high: float, low: float) -> Trade:
        gross = (exit_price - pos.entry_price) * pos.qty * pos.side.sign + pos.realised_pnl
        fees = pos.entry_fee + self._fee(exit_price, pos.qty) + pos.realised_fees
        mae = min(pos.mae, (low - pos.entry_price) * pos.side.sign)
        mfe = max(pos.mfe, (high - pos.entry_price) * pos.side.sign)
        return Trade(
            symbol=pos.symbol,
            side=pos.side,
            entry_time=pos.entry_time,
            exit_time=now.to_pydatetime() if hasattr(now, "to_pydatetime") else now,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            qty=pos.initial_qty or pos.qty,
            gross_pnl=gross,
            fees=fees,
            risk_amount=pos.risk_amount,
            exit_reason=reason,
            reason=pos.reason,
            mae=mae,
            mfe=mfe,
        )
