"""Historical candles from Binance's public market-data endpoint.

No API key, no account, no signature -- this is the read-only data mirror.
Trading credentials never touch this module.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from ..core.timeframe import bar_minutes

log = logging.getLogger(__name__)

# The .vision host is Binance's dedicated market-data mirror: same payload,
# no geo restrictions, and it keeps data traffic off the trading endpoint.
BASE_URL = "https://data-api.binance.vision"
FALLBACK_URL = "https://api.binance.com"
MAX_LIMIT = 1000  # hard cap per klines request

_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore",
]


class BinanceDataError(RuntimeError):
    pass


def _request(session: requests.Session, path: str, params: dict, timeout: float) -> list:
    last_error: Exception | None = None
    for base in (BASE_URL, FALLBACK_URL):
        for attempt in range(4):
            try:
                resp = session.get(f"{base}{path}", params=params, timeout=timeout)
                if resp.status_code == 429 or resp.status_code >= 500:
                    wait = 2.0 * (2**attempt)
                    log.warning("binance %s, retrying in %.0fs", resp.status_code, wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(2.0 * (2**attempt))
        log.warning("host %s unusable, trying fallback", base)
    raise BinanceDataError(f"could not reach Binance market data: {last_error}")


def fetch_klines(
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime | None = None,
    timeout: float = 20.0,
) -> pd.DataFrame:
    """Download closed candles in [start, end), paging through the 1000-bar cap."""
    end = end or datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    step = timedelta(minutes=bar_minutes(interval))
    session = requests.Session()
    session.headers["User-Agent"] = "daytrader/1.0"

    frames: list[pd.DataFrame] = []
    cursor = start
    while cursor < end:
        raw = _request(
            session,
            "/api/v3/klines",
            {
                "symbol": symbol.upper(),
                "interval": interval,
                "startTime": int(cursor.timestamp() * 1000),
                "endTime": int(end.timestamp() * 1000),
                "limit": MAX_LIMIT,
            },
            timeout,
        )
        if not raw:
            break
        frames.append(pd.DataFrame(raw, columns=_COLUMNS))
        last_open = pd.to_datetime(raw[-1][0], unit="ms", utc=True).to_pydatetime()
        cursor = last_open + step
        if len(raw) < MAX_LIMIT:
            break
        time.sleep(0.12)  # stay well inside the public rate limit

    if not frames:
        raise BinanceDataError(f"no candles returned for {symbol} {interval}")

    return _normalise(pd.concat(frames, ignore_index=True), end)


def _normalise(df: pd.DataFrame, end: datetime) -> pd.DataFrame:
    numeric = ["open", "high", "low", "close", "volume", "quote_volume", "trades"]
    df[numeric] = df[numeric].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)

    # Only fully closed bars may enter a backtest: the bar in progress will
    # still change, and trading it is pure hindsight.
    df = df[df["close_time"] <= pd.Timestamp(end)]

    df = df.set_index("open_time").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df[["open", "high", "low", "close", "volume", "quote_volume", "trades"]]
