"""The Dukascopy candle format, checked on a file built by hand.

The record stores open, close, low, high -- close before the extremes. Reading
it in the obvious order would swap close with low and high with nothing in
particular, and every candle would still look plausible enough to pass a
glance. This pins the order down.
"""

import lzma
import struct
from datetime import date

import pytest

from daytrader.data.dukascopy import RECORD, decode, url


def blob(records):
    return lzma.compress(b"".join(RECORD.pack(*r) for r in records),
                         format=lzma.FORMAT_ALONE)


def test_fields_land_in_the_right_columns_and_are_scaled():
    # 14:30 UTC: open 21536.499, close 21559.543, low 21528.389, high 21572.720
    df = decode(blob([(52200, 21536499, 21559543, 21528389, 21572720, 0.049)]),
                date(2025, 1, 6), point=1000.0)
    row = df.iloc[0]
    assert df.index[0].isoformat() == "2025-01-06T14:30:00+00:00"
    assert row["open"] == pytest.approx(21536.499)
    assert row["close"] == pytest.approx(21559.543)
    assert row["low"] == pytest.approx(21528.389)
    assert row["high"] == pytest.approx(21572.720)
    assert row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]


def test_an_empty_file_is_an_empty_day():
    assert decode(b"", date(2025, 1, 1), point=1000.0).empty


def test_months_in_the_url_count_from_zero():
    assert "/2025/00/06/" in url("USATECHIDXUSD", date(2025, 1, 6))
    assert "/2025/11/31/" in url("USATECHIDXUSD", date(2025, 12, 31))
