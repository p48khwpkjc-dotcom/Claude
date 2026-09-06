"""Candle validation. A backtest on broken candles is worse than no backtest."""

from pathlib import Path

import pandas as pd
import pytest

from conftest import frame
from daytrader.core.timeframe import align_to, bar_minutes, resample_ohlcv
from daytrader.data import loader
from daytrader.data.synthetic import generate


def test_ohlc_consistency_is_enforced():
    bad = frame([(100, 99, 98, 100)])   # high below the open
    with pytest.raises(ValueError, match="impossible OHLC"):
        loader.validate(bad, "TEST", "5m")


def test_duplicate_timestamps_are_rejected():
    df = frame([(100, 101, 99, 100)] * 2)
    df.index = [df.index[0], df.index[0]]
    with pytest.raises(ValueError, match="duplicate"):
        loader.validate(df, "TEST", "5m")


def test_unsorted_index_is_rejected():
    df = frame([(100, 101, 99, 100)] * 3).iloc[::-1]
    with pytest.raises(ValueError, match="not sorted"):
        loader.validate(df, "TEST", "5m")


def test_empty_range_is_rejected():
    with pytest.raises(ValueError, match="no candles"):
        loader.validate(frame([]).iloc[:0], "TEST", "5m")


def test_gaps_warn_but_do_not_fail(caplog):
    df = generate(bars=200)
    df = pd.concat([df.iloc[:50], df.iloc[80:]])
    loader.validate(df, "TEST", "5m")
    assert "gaps in history" in caplog.text


def test_cache_round_trip(tmp_path: Path):
    df = generate(bars=300)
    path = loader.cache_path(tmp_path, "BTCUSDT", "5m")
    loader.write_cache(path, df)
    back = loader.read_cache(path)
    assert back is not None
    # parquet does not carry the index's inferred frequency; the values are what matter
    pd.testing.assert_frame_equal(df, back, check_freq=False)


def test_missing_cache_names_the_command_that_fixes_it(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="daytrader fetch"):
        loader.load("NOPE", "5m", tmp_path)


def test_synthetic_source_needs_no_cache(tmp_path: Path):
    df = loader.load("BTCUSDT", "5m", tmp_path, source="synthetic", synthetic_bars=500)
    assert len(df) == 500


def test_bar_minutes():
    assert bar_minutes("1m") == 1
    assert bar_minutes("15m") == 15
    assert bar_minutes("4h") == 240
    with pytest.raises(ValueError):
        bar_minutes("3y")


def test_resample_keeps_ohlc_meaning():
    df = generate(bars=240, interval="5m")
    hourly = resample_ohlcv(df, "1h")
    first = df.iloc[:12]
    assert hourly["open"].iloc[0] == first["open"].iloc[0]
    assert hourly["close"].iloc[0] == first["close"].iloc[-1]
    assert hourly["high"].iloc[0] == first["high"].max()
    assert hourly["volume"].iloc[0] == pytest.approx(first["volume"].sum())


def test_htf_values_appear_only_after_the_htf_bar_closes():
    df = generate(bars=240, interval="5m")
    hourly = resample_ohlcv(df, "1h")
    aligned = align_to(hourly["close"], df.index, "1h")

    assert aligned.iloc[:12].isna().all(), "the first hour leaked before it closed"
    assert aligned.iloc[12] == pytest.approx(hourly["close"].iloc[0])
    assert aligned.iloc[23] == pytest.approx(hourly["close"].iloc[0]), \
        "the second hour must not be visible while it is still forming"
