"""One-minute index candles from Dukascopy's public datafeed.

Used for the Nasdaq 100 and the S&P 500, because no free source of one-minute
futures history is reachable. These are the cash indices as CFDs, not the
futures: intraday they move almost tick for tick with NQ and ES, the level
differs by the basis, and for a strategy built on the first minutes of the New
York session that difference does not matter. It is stated wherever the data
is used anyway.

The feed is one LZMA-compressed file per instrument and UTC day, holding 1440
records of 24 bytes: seconds since midnight, then open, close, low and high as
integers scaled by `POINT`, then volume as a float. Note the order -- close
comes before low and high, which is easy to get wrong and would turn every
candle inside out. Months in the URL count from zero.

The server throttles hard. Requests go out one at a time with a pause, and a
429 or 503 backs off exponentially instead of retrying at once; every day that
arrives is written to disk first, so an interrupted download resumes where it
stopped rather than starting over.
"""

from __future__ import annotations

import logging
import lzma
import struct
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

log = logging.getLogger(__name__)

BASE_URL = "https://datafeed.dukascopy.com/datafeed"
RECORD = struct.Struct(">IIIIIf")
POINT = {"USATECHIDXUSD": 1000.0, "USA500IDXUSD": 1000.0}

# Friendly names used in this project.
INSTRUMENTS = {"NQ": "USATECHIDXUSD", "ES": "USA500IDXUSD"}


class DukascopyError(RuntimeError):
    pass


def url(instrument: str, day: date, side: str = "BID") -> str:
    return (f"{BASE_URL}/{instrument}/{day.year}/{day.month - 1:02d}/{day.day:02d}/"
            f"{side}_candles_min_1.bi5")


def decode(blob: bytes, day: date, point: float) -> pd.DataFrame:
    """Turn one day's file into UTC-indexed OHLCV. An empty file is an empty day."""
    if not blob:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    raw = lzma.decompress(blob)
    if len(raw) % RECORD.size:
        raise DukascopyError(f"{day}: {len(raw)} bytes is not a whole number of records")
    rec = np.array(list(RECORD.iter_unpack(raw)), dtype=float)
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    idx = pd.DatetimeIndex([start + timedelta(seconds=int(s)) for s in rec[:, 0]])
    return pd.DataFrame({
        "open": rec[:, 1] / point, "high": rec[:, 4] / point,
        "low": rec[:, 3] / point, "close": rec[:, 2] / point,
        "volume": rec[:, 5],
    }, index=idx)


def _get(session: requests.Session, u: str, pause: float, max_wait: float) -> bytes:
    wait = 15.0
    while True:
        try:
            resp = session.get(u, timeout=30)
        except requests.RequestException as exc:
            log.warning("network error %s, waiting %.0fs", exc, wait)
            resp = None
        if resp is not None and resp.status_code == 200:
            time.sleep(pause)
            return resp.content
        if resp is not None and resp.status_code == 404:
            time.sleep(pause)
            return b""                          # no file: market closed that day
        if wait > max_wait:
            code = resp.status_code if resp is not None else "no response"
            raise DukascopyError(f"giving up on {u} after backing off ({code})")
        log.info("throttled (%s), waiting %.0fs", getattr(resp, "status_code", "-"), wait)
        time.sleep(wait)
        wait *= 2


def fetch(name: str, start: date, end: date, raw_dir: Path,
          pause: float = 1.5, max_wait: float = 960.0) -> pd.DataFrame:
    """Download weekdays in [start, end], resuming from files already on disk."""
    instrument = INSTRUMENTS.get(name, name)
    point = POINT.get(instrument, 1000.0)
    raw_dir = Path(raw_dir) / instrument
    raw_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (daytrader research)"

    frames, day, done, fetched = [], start, 0, 0
    total = sum(1 for k in range((end - start).days + 1)
                if (start + timedelta(days=k)).weekday() < 5)
    while day <= end:
        if day.weekday() < 5:
            path = raw_dir / f"{day.isoformat()}.bi5"
            if path.exists():
                blob = path.read_bytes()
            else:
                blob = _get(session, url(instrument, day), pause, max_wait)
                path.write_bytes(blob)
                fetched += 1
            frames.append(decode(blob, day, point))
            done += 1
            if done % 50 == 0:
                log.info("%s: %d/%d days (%d downloaded)", name, done, total, fetched)
        day += timedelta(days=1)
    frames = [f for f in frames if not f.empty]
    if not frames:
        raise DukascopyError(f"{name}: no data between {start} and {end}")
    return pd.concat(frames).sort_index()
