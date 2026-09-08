"""Funding rate history for perpetual futures.

Funding is what a carry position actually earns, so it is data in exactly the
same sense candles are: it needs the same caching, the same validation and the
same refusal to silently invent values it does not have.

Binance pays funding every eight hours. The endpoint lives on the futures host
(`fapi.binance.com`), which is a different host from the spot market data used
elsewhere in this package -- and one that some networks block. When it cannot
be reached, `load` falls back to a CSV under `data/exchange/funding/`, which is
how the rates reach a container that cannot call the exchange itself. See
FUNDING-HOLEN.md.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)

BASE_URL = "https://fapi.binance.com"
MAX_LIMIT = 1000              # hard cap per request
FUNDING_HOURS = 8
PERIODS_PER_YEAR = 365 * 24 / FUNDING_HOURS      # 1095


class FundingDataError(RuntimeError):
    pass


def cache_path(cache_dir: Path, symbol: str) -> Path:
    return Path(cache_dir) / f"{symbol.upper()}_funding.parquet"


def exchange_path(symbol: str) -> Path:
    """Where a manually transported CSV is expected to sit."""
    return Path("data/exchange/funding") / f"{symbol.upper()}_funding.csv"


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    """One shape regardless of source: UTC index, one float column."""
    out = df.copy()
    if "fundingTime" in out.columns:
        out["time"] = pd.to_datetime(out["fundingTime"], unit="ms", utc=True)
    elif "time" in out.columns:
        out["time"] = pd.to_datetime(out["time"], utc=True)
    else:
        raise FundingDataError("funding data needs a fundingTime or time column")
    col = "fundingRate" if "fundingRate" in out.columns else "funding_rate"
    if col not in out.columns:
        raise FundingDataError("funding data needs a fundingRate column")
    out["funding_rate"] = out[col].astype(float)
    out = out[["time", "funding_rate"]].dropna()
    return out.set_index("time").sort_index()[~out.set_index("time").index.duplicated()]


def fetch(symbol: str, start: datetime, end: datetime | None = None,
          timeout: float = 20.0) -> pd.DataFrame:
    """Page through funding history. Raises rather than returning a short frame."""
    end = end or datetime.now(timezone.utc)
    session = requests.Session()
    session.headers["User-Agent"] = "daytrader/1.0"
    frames, cursor = [], start
    while cursor < end:
        params = {"symbol": symbol.upper(), "limit": MAX_LIMIT,
                  "startTime": int(cursor.timestamp() * 1000),
                  "endTime": int(end.timestamp() * 1000)}
        try:
            resp = session.get(f"{BASE_URL}/fapi/v1/fundingRate", params=params,
                               timeout=timeout)
            resp.raise_for_status()
            raw = resp.json()
        except requests.RequestException as exc:
            raise FundingDataError(
                f"could not reach {BASE_URL}: {exc}. On a blocked network, "
                f"transport the rates through the repo instead -- see FUNDING-HOLEN.md"
            ) from exc
        if not raw:
            break
        frames.append(pd.DataFrame(raw))
        last = pd.to_datetime(raw[-1]["fundingTime"], unit="ms", utc=True)
        if last <= cursor:
            break
        cursor = last.to_pydatetime() + timedelta(seconds=1)
        time.sleep(0.2)
    if not frames:
        raise FundingDataError(f"{symbol}: no funding data in the requested window")
    return _normalise(pd.concat(frames, ignore_index=True))


def load(symbol: str, days: int, cache_dir: Path,
         allow_network: bool = True) -> pd.DataFrame:
    """Cache, then a transported CSV, then the network. Never a silent empty frame."""
    path = cache_path(cache_dir, symbol)
    if path.exists():
        cached = pd.read_parquet(path)
        cached.index = pd.to_datetime(cached.index, utc=True)
        return cached.sort_index()

    csv = exchange_path(symbol)
    if csv.exists():
        log.info("%s: reading transported funding rates from %s", symbol, csv)
        df = _normalise(pd.read_csv(csv))
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path)
        return df

    if not allow_network:
        raise FundingDataError(
            f"{symbol}: no cache and no {csv}. Fetch the rates on a machine that "
            f"can reach the exchange -- see FUNDING-HOLEN.md")
    df = fetch(symbol, datetime.now(timezone.utc) - timedelta(days=days))
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return df


def annualised(rate_per_period: float) -> float:
    """A per-8h rate as a simple annual percentage, not compounded."""
    return rate_per_period * PERIODS_PER_YEAR * 100
