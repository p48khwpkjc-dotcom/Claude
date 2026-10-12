"""Opening range breakout, checked against numbers worked out by hand.

Most of what can go wrong with a New York open strategy is the clock: a range
taken an hour early for half the year because the offset to UTC was hard-coded,
or an entry on the bar that produced the signal. These tests pin the clock
down first and the arithmetic second.
"""

import pandas as pd
import pytest

from daytrader.backtest.orb import OrbConfig, run, summarise

FREE = dict(fee_pct=0.0, slippage_bps=0.0, stop_slippage_bps=0.0)


def day(date: str, overrides: dict[int, tuple], base: float = 100.0,
        later: float | None = None) -> pd.DataFrame:
    """One New York session of flat one-minute bars, 09:30 to 15:59.

    `overrides` maps minutes after 09:30 to (open, high, low, close). Bars not
    overridden sit at `base` -- inside the range -- and from 09:38 onward at
    `later` if given, so a fixture can put price where a breakout left it
    without the flat bars inventing a signal of their own.
    """
    idx = pd.date_range(f"{date} 09:30", f"{date} 15:59", freq="1min",
                        tz="America/New_York")
    def flat(m):
        px = later if later is not None and m >= 8 else base
        return (px, px, px, px)
    rows = [overrides.get(m, flat(m)) for m in range(len(idx))]
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    df["volume"] = 1.0
    return df.tz_convert("UTC")


# Opening range 99..101, every one of the first five minutes spelled out.
RANGE = {0: (100.0, 101.0, 100.0, 100.5),
         1: (100.5, 100.8, 99.8, 100.2),
         2: (100.2, 100.5, 99.0, 99.5),
         3: (99.5, 100.0, 99.4, 99.8),
         4: (99.8, 100.2, 99.6, 100.0)}


def test_the_range_starts_at_0930_new_york_in_winter_and_in_summer():
    for date, utc_hour in [("2025-01-15", 14), ("2025-07-15", 13)]:
        bars = day(date, {**RANGE, 7: (100, 101.6, 100, 101.5)})
        assert bars.index[0].hour == utc_hour          # the clock really moved
        t = run(bars, OrbConfig(**FREE))
        assert len(t) == 1
        assert t.iloc[0]["entry_time"].tz_convert("America/New_York").strftime("%H:%M") == "09:38"


def test_a_close_above_the_range_goes_long_on_the_next_minute_open():
    bars = day("2025-03-03", {**RANGE,
                              7: (100, 101.6, 100, 101.5),     # signal
                              8: (101.5, 101.8, 101.4, 101.6)})
    t = run(bars, OrbConfig(**FREE)).iloc[0]
    assert t["side"] == "long"
    assert t["entry"] == pytest.approx(101.5)           # open of 09:38
    assert t["risk"] == pytest.approx(101.5 - 99.0)     # to the range low


def test_a_wick_through_the_range_is_not_a_signal():
    bars = day("2025-03-03", {**RANGE, 7: (100, 102.0, 98.0, 100.0)})
    assert run(bars, OrbConfig(**FREE)).empty


def test_a_close_below_the_range_goes_short():
    bars = day("2025-03-03", {**RANGE, 9: (100, 100, 98.5, 98.6)})
    t = run(bars, OrbConfig(**FREE)).iloc[0]
    assert t["side"] == "short"
    assert t["risk"] == pytest.approx(101.0 - 100.0)    # next open 100, range high 101


def test_the_target_pays_its_multiple_of_risk():
    # Entry 101.5, stop 99, risk 2.5 -> 2R target at 106.5.
    bars = day("2025-03-03", {**RANGE,
                              7: (100, 101.6, 100, 101.5),
                              8: (101.5, 101.5, 101.5, 101.5),
                              30: (104, 107.0, 104, 106)}, later=101.5)
    t = run(bars, OrbConfig(target_r=2.0, **FREE)).iloc[0]
    assert t["exit_reason"] == "target"
    assert t["r"] == pytest.approx(2.0)


def test_the_stop_wins_when_one_bar_reaches_both():
    bars = day("2025-03-03", {**RANGE,
                              7: (100, 101.6, 100, 101.5),
                              30: (101.5, 107.0, 98.0, 100)}, later=101.5)
    t = run(bars, OrbConfig(target_r=2.0, **FREE)).iloc[0]
    assert t["exit_reason"] == "stop"
    assert t["r"] == pytest.approx(-1.0)


def test_a_gap_through_the_stop_fills_at_the_open():
    bars = day("2025-03-03", {**RANGE,
                              7: (100, 101.6, 100, 101.5),
                              30: (97.0, 97.5, 96.5, 97.0)}, later=101.5)
    t = run(bars, OrbConfig(**FREE)).iloc[0]
    assert t["exit"] == pytest.approx(97.0)              # not 99
    assert t["r"] == pytest.approx((97.0 - 101.5) / 2.5)


def test_without_a_stop_the_trade_is_held_to_the_session_close():
    bars = day("2025-03-03", {**RANGE,
                              7: (100, 101.6, 100, 101.5),
                              30: (97.0, 97.5, 96.5, 97.0),      # would stop out
                              389: (103, 103, 103, 103.0)}, later=101.5)
    t = run(bars, OrbConfig(stop="none", **FREE)).iloc[0]
    assert t["exit_reason"] == "session_end"
    assert t["exit"] == pytest.approx(103.0)              # close of 15:59
    assert t["r"] == pytest.approx((103.0 - 101.5) / 2.5)


def test_only_the_first_signal_of_the_day_is_traded():
    bars = day("2025-03-03", {**RANGE,
                              7: (100, 101.6, 100, 101.5),
                              20: (100, 100, 98, 98.5)}, later=101.5)
    assert len(run(bars, OrbConfig(**FREE))) == 1


def test_costs_are_charged_on_both_fills_and_expressed_in_r():
    bars = day("2025-03-03", {**RANGE, 7: (100, 101.6, 100, 101.5)}, later=101.5)
    t = run(bars, OrbConfig(stop="none", fee_pct=0.05, slippage_bps=0.0,
                            stop_slippage_bps=0.0)).iloc[0]
    assert t["cost_r"] == pytest.approx(0.0005 * (101.5 + 101.5) / 2.5)


def test_the_coin_flip_keeps_the_distance_and_draws_only_the_direction():
    frames = [day(f"2025-03-{d:02d}", {**RANGE, 7: (100, 101.6, 100, 101.5)}, later=101.5)
              for d in range(3, 28)]
    bars = pd.concat(frames)
    real = run(bars, OrbConfig(**FREE))
    coin = run(bars, OrbConfig(direction="coin", **FREE))
    assert len(coin) == len(real)                        # no day is dropped
    assert coin["risk"].tolist() == pytest.approx(real["risk"].tolist())
    assert set(coin["side"]) == {"long", "short"}
    again = run(bars, OrbConfig(direction="coin", **FREE))
    assert coin["side"].tolist() == again["side"].tolist()   # reproducible


def test_summary_reports_an_interval_that_contains_the_mean():
    frames = [day(f"2025-03-{d:02d}", {**RANGE, 7: (100, 101.6, 100, 101.5),
                                       60 + d: (101.5, 101.5 + d / 10, 101.5, 101.5)},
                  later=101.5) for d in range(3, 28)]
    s = summarise(run(pd.concat(frames), OrbConfig(stop="none", **FREE)))
    assert s["ci_low"] <= s["exp_r"] <= s["ci_high"]


def test_a_five_minute_signal_waits_for_the_five_minute_close():
    # 09:37 closes above the range, but the 09:35-09:39 candle closes back
    # inside at 09:39, so it is no signal. The 09:40-09:44 candle closes above
    # at 09:44, and the entry is the 09:45 open.
    bars = day("2025-03-03", {**RANGE,
                              7: (100, 101.6, 100, 101.5),
                              9: (101.0, 101.0, 100.4, 100.5),
                              14: (100.5, 101.7, 100.5, 101.6),
                              15: (101.6, 101.8, 101.5, 101.6)})
    t = run(bars, OrbConfig(signal_minutes=5, **FREE)).iloc[0]
    assert t["entry_time"].strftime("%H:%M") == "09:45"
    assert t["side"] == "long"


def test_a_fifteen_minute_range_spans_the_first_fifteen_minutes():
    # The low at 09:40 belongs to a 15-minute range but not to a 5-minute one.
    bars = day("2025-03-03", {**RANGE,
                              10: (100, 100, 98.0, 99.8),
                              29: (100, 101.5, 100, 101.2),      # closes 09:59 candle above
                              30: (101.2, 101.3, 101.1, 101.2)})
    t = run(bars, OrbConfig(range_minutes=15, signal_minutes=15, **FREE)).iloc[0]
    assert t["entry_time"].strftime("%H:%M") == "10:00"
    assert t["risk"] == pytest.approx(101.2 - 98.0)     # down to the 15-minute low


def test_one_minute_signals_are_unchanged_by_the_candle_grid():
    bars = day("2025-03-03", {**RANGE, 7: (100, 101.6, 100, 101.5)}, later=101.5)
    a = run(bars, OrbConfig(**FREE))
    b = run(bars, OrbConfig(signal_minutes=1, **FREE))
    assert a.equals(b)
