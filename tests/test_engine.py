"""Fill mechanics, checked against numbers worked out by hand.

If these drift, every performance figure the bot produces is fiction.
"""

import pytest

from conftest import ScriptedStrategy, frame
from daytrader.backtest.engine import BacktestEngine
from daytrader.core.types import ExitReason, Side, Signal

FLAT = (100.0, 100.0, 100.0, 100.0)


def run(cfg, rows, signal, at=2, atr=0.0):
    strat = ScriptedStrategy(at=at, signal=signal, atr=atr)
    return BacktestEngine(cfg, strat, "TEST").run(frame(rows))


def test_entry_fills_on_the_next_bar_open_with_slippage(cfg):
    res = run(cfg, [FLAT, FLAT, FLAT,
                    (100.0, 100.5, 99.8, 100.2),
                    (100.2, 102.5, 100.0, 102.3)],
              Signal(Side.LONG, stop_loss=99.0, take_profit=102.0))
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.entry_price == pytest.approx(100.0 * 1.0003)      # 3 bps against us
    assert t.entry_time == frame([FLAT] * 5).index[3]          # bar 3, not bar 2
    assert t.exit_reason is ExitReason.TAKE_PROFIT
    assert t.exit_price == pytest.approx(102.0)


def test_pnl_fees_and_r_multiple_match_hand_calculation(cfg):
    res = run(cfg, [FLAT, FLAT, FLAT,
                    (100.0, 100.5, 99.8, 100.2),
                    (100.2, 102.5, 100.0, 102.3)],
              Signal(Side.LONG, stop_loss=99.0, take_profit=102.0))
    t = res.trades[0]

    entry = 100.0 * 1.0003
    qty = 50.0 / (entry - 99.0)            # 0.5% of 10_000, over the stop distance
    fees = (entry * qty + 102.0 * qty) * 0.0005
    gross = (102.0 - entry) * qty

    assert t.qty == pytest.approx(qty)
    assert t.gross_pnl == pytest.approx(gross)
    assert t.fees == pytest.approx(fees)
    assert t.net_pnl == pytest.approx(gross - fees)
    assert t.risk_amount == pytest.approx(50.0)
    assert t.r_multiple == pytest.approx((gross - fees) / 50.0)


def test_stop_wins_when_one_bar_contains_both_levels(cfg):
    res = run(cfg, [FLAT, FLAT, FLAT,
                    (100.0, 100.2, 99.9, 100.1),
                    (100.0, 103.0, 98.0, 101.0)],   # touches stop 99 and target 102
              Signal(Side.LONG, stop_loss=99.0, take_profit=102.0))
    t = res.trades[0]
    assert t.exit_reason is ExitReason.STOP_LOSS
    assert t.exit_price == pytest.approx(99.0 * 0.9995)
    assert t.net_pnl < 0


def test_a_gap_through_the_stop_fills_at_the_open(cfg):
    res = run(cfg, [FLAT, FLAT, FLAT,
                    (100.0, 100.2, 99.9, 100.1),
                    (97.0, 97.5, 96.0, 96.5)],      # opens well below the stop
              Signal(Side.LONG, stop_loss=99.0, take_profit=102.0))
    t = res.trades[0]
    assert t.exit_reason is ExitReason.STOP_LOSS
    assert t.exit_price == pytest.approx(97.0 * 0.9995), "a gap must not fill at the stop level"
    assert t.r_multiple < -1.0, "gap risk means losses larger than 1R are possible"


def test_short_side_is_symmetric(cfg):
    res = run(cfg, [FLAT, FLAT, FLAT,
                    (100.0, 100.2, 99.8, 100.0),
                    (100.0, 100.1, 97.5, 97.6)],
              Signal(Side.SHORT, stop_loss=101.0, take_profit=98.0))
    t = res.trades[0]
    assert t.side is Side.SHORT
    assert t.entry_price == pytest.approx(100.0 * 0.9997)   # sold 3 bps lower
    assert t.exit_reason is ExitReason.TAKE_PROFIT
    assert t.net_pnl > 0


def test_position_times_out(cfg):
    cfg.risk.max_hold_hours = 0.25   # three 5m bars
    rows = [FLAT, FLAT, FLAT] + [(100.0, 100.2, 99.8, 100.1)] * 6
    res = run(cfg, rows, Signal(Side.LONG, stop_loss=99.0, take_profit=110.0))
    t = res.trades[0]
    assert t.exit_reason is ExitReason.MAX_HOLD
    assert t.holding_time.total_seconds() == pytest.approx(15 * 60)


def test_trailing_stop_never_loosens_and_cannot_use_its_own_bar(cfg):
    rows = [FLAT, FLAT, FLAT,
            (100.0, 100.2, 99.9, 100.1),
            (100.1, 105.0, 100.0, 104.9),   # big up bar: trail moves up after it
            (104.9, 105.0, 101.0, 101.5)]   # trailed stop at 105-2*1 = 103 gets hit
    res = run(cfg, rows, Signal(Side.LONG, stop_loss=99.0, trail_atr_mult=2.0), atr=1.0)
    t = res.trades[0]
    assert t.exit_reason is ExitReason.TRAILING_STOP
    assert t.exit_price == pytest.approx(103.0 * 0.9995)
    assert t.net_pnl > 0, "the trail should lock in part of the move"


def test_invalid_stop_is_refused_not_traded(cfg):
    res = run(cfg, [FLAT] * 6, Signal(Side.LONG, stop_loss=101.0))  # stop above entry
    assert res.trades == []
    assert any("not below entry" in k for k in res.rejections)


def test_equity_curve_matches_the_sum_of_trades(cfg):
    rows = [FLAT, FLAT, FLAT,
            (100.0, 100.5, 99.8, 100.2),
            (100.2, 102.5, 100.0, 102.3),
            FLAT, FLAT]
    res = run(cfg, rows, Signal(Side.LONG, stop_loss=99.0, take_profit=102.0))
    expected = cfg.account.start_equity + sum(t.net_pnl for t in res.trades)
    assert res.end_equity == pytest.approx(expected)


def test_kill_switch_flattens_the_open_position(cfg):
    cfg.risk.max_daily_loss_pct = 0.2      # 20 USD on a 10k account
    cfg.risk.risk_per_trade_pct = 0.5
    rows = [FLAT, FLAT, FLAT,
            (100.0, 100.2, 99.9, 100.1),
            (100.0, 100.0, 99.4, 99.4),    # unrealised loss trips the limit
            (99.4, 99.5, 99.3, 99.35)]
    res = run(cfg, rows, Signal(Side.LONG, stop_loss=99.0, take_profit=110.0))
    assert res.trades, "the position should have been closed by the kill switch"
    assert res.trades[0].exit_reason is ExitReason.KILL_SWITCH
    assert res.blocked_by_kill_switch == 1
