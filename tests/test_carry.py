"""Cash-and-carry arithmetic, checked against numbers worked out by hand.

The whole value of this module is that it does not forget anything, so these
tests are mostly about the things a carry pitch leaves out: the second leg,
the four fills, the periods where funding is negative, and the short that can
be liquidated while the matching gain sits untouchable in spot.
"""

import numpy as np
import pandas as pd
import pytest

from daytrader.backtest.carry import CarryConfig, _cost_per_cycle, run


def series(rates, prices=None, start="2025-01-01"):
    idx = pd.date_range(start, periods=len(rates), freq="8h", tz="UTC")
    f = pd.Series(rates, index=idx)
    p = pd.Series(prices if prices is not None else [100.0] * len(rates), index=idx)
    return f, p


FREE = CarryConfig(fee_pct=0.0, slippage_bps=0.0)


def test_a_flat_positive_rate_pays_the_sum_of_its_periods():
    f, p = series([0.0001] * 30)
    r = run("TEST", f, p, FREE)
    # The first period is spent opening the position, so funding accrues from
    # the second onward -- 29 of 30. Margin is 50%, so the spot leg is 2/3 of
    # capital and the return scales by that.
    assert r.periods_in_market == 29
    assert r.funding_collected == pytest.approx(29 * 0.0001 * (1 / 1.5) * 100)
    assert r.net_return_pct > 0


def test_negative_funding_is_paid_not_skipped():
    f, p = series([-0.0002] * 30)
    r = run("TEST", f, p, FREE)
    assert r.net_return_pct < 0
    assert r.periods_in_market == 29      # an always-on carry stays in and pays


def test_fees_are_charged_for_four_fills_not_two():
    cfg = CarryConfig(fee_pct=0.05, slippage_bps=0.0, margin_pct=50.0)
    f, p = series([0.0] * 10)             # no funding at all: only costs remain
    r = run("TEST", f, p, cfg)
    notional = 1 / 1.5
    assert r.fees_paid == pytest.approx(4 * 0.0005 * notional * 100)


def test_a_filter_that_flips_every_period_is_eaten_by_the_cost_of_flipping():
    # Alternating rates, a filter that reacts to each one, minimum hold of one.
    rates = [0.0003, -0.0003] * 40
    f, p = series(rates)
    always = run("TEST", f, p, CarryConfig(fee_pct=0.05, min_hold_periods=1))
    picky = run("TEST", f, p, CarryConfig(fee_pct=0.05, enter_above=0.0,
                                          exit_below=0.0, min_hold_periods=1))
    assert picky.cycles > always.cycles
    # The filter sits out every negative period and still ends up behind,
    # because each round trip costs more than the period it avoided.
    assert picky.net_return_pct < always.net_return_pct


def test_a_filter_helps_when_the_regime_lasts_long_enough_to_pay_for_the_switch():
    rates = [0.0004] * 60 + [-0.0004] * 60 + [0.0004] * 60
    f, p = series(rates)
    always = run("TEST", f, p, CarryConfig(fee_pct=0.05))
    picky = run("TEST", f, p, CarryConfig(fee_pct=0.05, enter_above=0.0,
                                          exit_below=0.0))
    assert picky.net_return_pct > always.net_return_pct
    assert picky.periods_in_market < always.periods_in_market


def test_a_rising_price_can_liquidate_the_short_leg():
    # Margin is 20% of notional and 80% of it may be lost, so a 16% adverse
    # move ends the hedge.
    prices = list(np.linspace(100.0, 130.0, 40))
    f, p = series([0.0001] * 40, prices)
    r = run("TEST", f, p, CarryConfig(fee_pct=0.0, slippage_bps=0.0,
                                      margin_pct=20.0, liquidation_buffer_pct=80.0))
    assert r.liquidations >= 1


def test_more_margin_survives_the_same_move():
    prices = list(np.linspace(100.0, 130.0, 40))
    f, p = series([0.0001] * 40, prices)
    r = run("TEST", f, p, CarryConfig(fee_pct=0.0, slippage_bps=0.0,
                                      margin_pct=100.0, liquidation_buffer_pct=80.0))
    assert r.liquidations == 0


def test_the_cost_of_a_cycle_is_four_fills_of_fee_plus_slippage():
    cfg = CarryConfig(fee_pct=0.05, slippage_bps=3.0)
    assert _cost_per_cycle(cfg) == pytest.approx(4 * (0.0005 + 0.0003))


def test_return_is_measured_on_capital_not_on_margin():
    # Same funding, more margin posted -> the same funding on a smaller spot
    # leg, so the return on total capital must fall. Quoting on margin alone
    # would make the opposite happen, which is the usual sleight of hand.
    f, p = series([0.0002] * 60)
    lean = run("TEST", f, p, CarryConfig(fee_pct=0.0, slippage_bps=0.0, margin_pct=20.0))
    heavy = run("TEST", f, p, CarryConfig(fee_pct=0.0, slippage_bps=0.0, margin_pct=100.0))
    assert lean.net_return_pct > heavy.net_return_pct
