"""Scaling out, checked against numbers worked out by hand.

The whole point of a partial is that it changes the shape of an outcome
without changing the entry, so these tests pin down exactly what it banks,
what it leaves running, and what it does to the R multiple. If they drift,
every comparison between a scaled and an unscaled strategy is fiction.
"""

import pytest

from conftest import ScriptedStrategy, frame
from daytrader.backtest.engine import BacktestEngine
from daytrader.core.types import ExitReason, Side, Signal

FLAT = (100.0, 100.0, 100.0, 100.0)


def run(cfg, rows, signal, at=2, atr=0.0):
    return BacktestEngine(cfg, ScriptedStrategy(at=at, signal=signal, atr=atr),
                          "TEST").run(frame(rows))


def clean_cfg(cfg):
    """No fees or slippage, so the arithmetic below is readable by eye."""
    cfg.execution.taker_fee_pct = 0.0
    cfg.execution.slippage_bps = 0.0
    cfg.execution.stop_slippage_bps = 0.0
    return cfg


# Entry at 100, stop at 99 -> one R is 1.00. Target 102 is 2R, partial at 1.5R
# is 101.50.
SIG = Signal(Side.LONG, stop_loss=99.0, take_profit=102.0)


def test_without_a_partial_a_winner_is_worth_the_full_target(cfg):
    cfg = clean_cfg(cfg)
    res = run(cfg, [FLAT] * 3 + [FLAT, (100.0, 102.5, 100.0, 102.0)], SIG)
    assert res.trades[0].r_multiple == pytest.approx(2.0)


def test_a_partial_caps_part_of_the_winner_at_the_scale_out_level(cfg):
    cfg = clean_cfg(cfg)
    cfg.execution.partial_at_r = 1.5
    cfg.execution.partial_fraction = 0.5
    res = run(cfg, [FLAT] * 3 + [FLAT, (100.0, 102.5, 100.0, 102.0)], SIG)
    # Half banked at +1.5R, half carried to +2R.
    assert res.trades[0].r_multiple == pytest.approx(0.5 * 1.5 + 0.5 * 2.0)


def test_a_partial_does_not_rescue_a_trade_that_never_reaches_it(cfg):
    cfg = clean_cfg(cfg)
    cfg.execution.partial_at_r = 1.5
    res = run(cfg, [FLAT] * 3 + [FLAT, (100.0, 100.2, 98.5, 99.0)], SIG)
    assert res.trades[0].exit_reason is ExitReason.STOP_LOSS
    assert res.trades[0].r_multiple == pytest.approx(-1.0)


def test_a_partial_softens_a_loser_that_got_there_first(cfg):
    cfg = clean_cfg(cfg)
    cfg.execution.partial_at_r = 1.5
    cfg.execution.partial_fraction = 0.5
    # Reaches 101.5 on one bar, then collapses through the stop on the next.
    res = run(cfg, [FLAT] * 3 + [FLAT,
                                 (100.0, 101.6, 100.0, 101.0),
                                 (101.0, 101.0, 98.0, 98.5)], SIG)
    t = res.trades[0]
    assert t.exit_reason is ExitReason.STOP_LOSS
    # Half banked at +1.5R, half stopped at -1R: a loss, but a smaller one.
    assert t.r_multiple == pytest.approx(0.5 * 1.5 + 0.5 * -1.0)


def test_breakeven_after_partial_turns_that_loser_into_a_profit(cfg):
    cfg = clean_cfg(cfg)
    cfg.execution.partial_at_r = 1.5
    cfg.execution.partial_fraction = 0.5
    cfg.execution.breakeven_after_partial = True
    res = run(cfg, [FLAT] * 3 + [FLAT,
                                 (100.0, 101.6, 100.0, 101.0),
                                 (101.0, 101.0, 98.0, 98.5)], SIG)
    t = res.trades[0]
    # The remainder now stops at entry, not at 99: +0.75R instead of +0.25R.
    assert t.r_multiple == pytest.approx(0.5 * 1.5 + 0.5 * 0.0)
    assert t.net_pnl > 0        # and it is recorded as a winning trade


def test_the_partial_fires_only_once(cfg):
    cfg = clean_cfg(cfg)
    cfg.execution.partial_at_r = 1.5
    cfg.execution.partial_fraction = 0.5
    # Touches the partial level on three separate bars before the target.
    res = run(cfg, [FLAT] * 3 + [FLAT,
                                 (100.0, 101.6, 100.5, 101.0),
                                 (101.0, 101.7, 100.5, 101.0),
                                 (101.0, 102.5, 100.5, 102.0)], SIG)
    assert res.trades[0].r_multiple == pytest.approx(0.5 * 1.5 + 0.5 * 2.0)


def test_a_full_partial_closes_the_whole_position_at_the_level(cfg):
    cfg = clean_cfg(cfg)
    cfg.execution.partial_at_r = 1.5
    cfg.execution.partial_fraction = 1.0
    res = run(cfg, [FLAT] * 3 + [FLAT, (100.0, 102.5, 100.0, 102.0)], SIG)
    # Everything came off at 1.5R, so the 2R target earns nothing extra.
    assert res.trades[0].r_multiple == pytest.approx(1.5)


def test_the_stop_still_wins_a_tie_inside_one_bar(cfg):
    cfg = clean_cfg(cfg)
    cfg.execution.partial_at_r = 1.5
    # One bar spans both the partial and the stop. Without tick data the stop
    # is assumed first, so nothing is banked.
    res = run(cfg, [FLAT] * 3 + [FLAT, (100.0, 101.6, 98.5, 99.0)], SIG)
    assert res.trades[0].r_multiple == pytest.approx(-1.0)
