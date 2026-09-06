"""The limits that decide whether a bad run stays survivable."""

import datetime as dt

import pytest

from daytrader.config import RiskConfig
from daytrader.core.types import ExitReason, Side, Trade
from daytrader.risk.manager import RiskManager, SizingResult

UTC = dt.timezone.utc


def losing_trade(risk=50.0, pnl=-50.0) -> Trade:
    return Trade("BTC", Side.LONG, dt.datetime(2024, 1, 1, tzinfo=UTC),
                 dt.datetime(2024, 1, 1, 1, tzinfo=UTC), 100.0, 99.0, 1.0,
                 gross_pnl=pnl, fees=0.0, risk_amount=risk,
                 exit_reason=ExitReason.STOP_LOSS)


def test_size_risks_exactly_the_configured_fraction():
    rm = RiskManager(RiskConfig(), 10_000)
    s = rm.size(Side.LONG, 100.0, 98.0)
    assert isinstance(s, SizingResult)
    assert s.risk_amount == pytest.approx(50.0)
    assert s.qty == pytest.approx(25.0)


def test_a_tighter_stop_buys_a_bigger_position_not_more_risk():
    rm = RiskManager(RiskConfig(), 10_000)
    wide = rm.size(Side.LONG, 100.0, 96.0)
    tight = rm.size(Side.LONG, 100.0, 99.0)
    assert tight.qty > wide.qty
    assert tight.risk_amount == pytest.approx(wide.risk_amount)


def test_leverage_cap_reduces_risk_and_says_so():
    rm = RiskManager(RiskConfig(max_leverage=1.0), 10_000)
    # A 0.4% stop wants 125 units, which is 12_500 notional on a 10_000 account.
    s = rm.size(Side.LONG, 100.0, 99.6)
    assert s.capped_by_leverage
    assert s.notional == pytest.approx(10_000)
    assert s.risk_amount < 50.0, "capped size must report the risk actually taken"


def test_stops_on_the_wrong_side_are_refused():
    rm = RiskManager(RiskConfig(), 10_000)
    assert isinstance(rm.size(Side.LONG, 100.0, 101.0), str)
    assert isinstance(rm.size(Side.SHORT, 100.0, 99.0), str)


def test_stop_distance_bounds():
    rm = RiskManager(RiskConfig(min_stop_distance_pct=0.1, max_stop_distance_pct=2.0), 10_000)
    assert "too tight" in rm.size(Side.LONG, 100.0, 99.95)
    assert "too wide" in rm.size(Side.LONG, 100.0, 90.0)


def test_kill_switch_trips_on_the_daily_loss_and_resets_the_next_day():
    rm = RiskManager(RiskConfig(max_daily_loss_pct=3.0), 10_000)
    rm.on_bar(dt.datetime(2024, 1, 1, 0, tzinfo=UTC), 10_000)
    rm.on_bar(dt.datetime(2024, 1, 1, 9, tzinfo=UTC), 9_800)   # -2%
    assert rm.can_open(0, 0)[0]
    rm.on_bar(dt.datetime(2024, 1, 1, 10, tzinfo=UTC), 9_690)  # -3.1%
    assert not rm.can_open(0, 0)[0]
    assert rm.should_flatten

    rm.on_bar(dt.datetime(2024, 1, 2, 0, tzinfo=UTC), 9_690)
    assert rm.can_open(0, 0)[0], "a new day starts with a fresh budget"


def test_kill_switch_measures_from_the_day_start_not_the_all_time_peak():
    rm = RiskManager(RiskConfig(max_daily_loss_pct=3.0), 10_000)
    rm.on_bar(dt.datetime(2024, 1, 1, tzinfo=UTC), 10_000)
    rm.on_bar(dt.datetime(2024, 1, 2, tzinfo=UTC), 8_000)   # yesterday's damage
    rm.on_bar(dt.datetime(2024, 1, 2, 12, tzinfo=UTC), 7_900)
    assert rm.can_open(0, 0)[0]


def test_daily_trade_cap():
    rm = RiskManager(RiskConfig(max_trades_per_day=2), 10_000)
    rm.on_bar(dt.datetime(2024, 1, 1, tzinfo=UTC), 10_000)
    rm.on_opened(); rm.on_opened()
    ok, why = rm.can_open(0, 0)
    assert not ok and "max trades per day" in why


def test_cooldown_after_a_losing_streak():
    cfg = RiskConfig(cooldown_after_losses=3, cooldown_bars=12)
    rm = RiskManager(cfg, 10_000)
    rm.on_bar(dt.datetime(2024, 1, 1, tzinfo=UTC), 10_000)
    for bar in range(3):
        rm.on_closed(losing_trade(), bar_index=bar)
    assert not rm.can_open(5, 0)[0]
    assert rm.can_open(20, 0)[0], "the pause must expire"


def test_a_winner_resets_the_streak():
    rm = RiskManager(RiskConfig(cooldown_after_losses=3), 10_000)
    rm.on_closed(losing_trade(), 0)
    rm.on_closed(losing_trade(), 1)
    rm.on_closed(losing_trade(pnl=+80.0), 2)
    rm.on_closed(losing_trade(), 3)
    assert rm.can_open(4, 0)[0]


def test_concurrent_position_limit():
    rm = RiskManager(RiskConfig(max_concurrent_positions=1), 10_000)
    assert not rm.can_open(0, open_positions=1)[0]
