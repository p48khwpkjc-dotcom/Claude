"""Opening range breakout at the New York open, on one-minute candles.

The rules are fixed in research/ORB_ANMELDUNG.md and implemented here exactly:

1. The opening range is the high and low of the first `range_minutes` after
   09:30 New York time. The session clock runs in `America/New_York`, so the
   switch between summer and winter time is the timezone database's problem
   rather than a hard-coded UTC offset that is wrong for half the year.
2. The first one-minute bar from the end of the range onward that *closes*
   above the range high is a long, below the range low a short. One trade per
   day; the first signal is the only one.
3. Entry is at the open of the following minute. A rule that reacts to a close
   cannot trade before that close has happened.
4. The position is closed at the end of the session unless the stop or the
   target is reached first.

One R is the distance from entry to the opposite side of the range. It is
reported in that unit even when no stop is used, so every variant reads in the
same currency.

Within a bar the stop beats the target, and a bar that opens beyond the stop
fills at its open, not at the stop -- the same pessimistic rules the main
engine follows, for the same reason: without tick data the order of events
inside a bar is unknown, and the only reading that cannot flatter a result is
the unfavourable one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import zlib

import numpy as np
import pandas as pd

NY = "America/New_York"


@dataclass(frozen=True, slots=True)
class OrbConfig:
    range_minutes: int = 5
    open_time: time = time(9, 30)
    close_time: time = time(16, 0)
    stop: str = "range"          # "range" = opposite side, "none" = no stop
    target_r: float | None = None
    fee_pct: float = 0.05        # per side
    slippage_bps: float = 3.0    # on entry and on market exits
    stop_slippage_bps: float = 5.0
    direction: str = "breakout"  # "breakout", or "coin" for the null model
    seed: int = 7                # only used by the coin flip


TRADE_COLUMNS = ["day", "side", "entry_time", "exit_time", "entry", "exit",
                 "risk", "r_gross", "cost_r", "r", "exit_reason", "range_pct"]


def _session_days(df: pd.DataFrame, cfg: OrbConfig):
    """Yield (date, bars) for each New York session, bars inside open..close."""
    local = df.tz_convert(NY)
    clock = local.index.time
    inside = (clock >= cfg.open_time) & (clock < cfg.close_time)
    local = local[inside]
    for day, bars in local.groupby(local.index.date):
        yield day, bars


def _coin(day, seed: int) -> int:
    """A direction that is arbitrary but identical on every run.

    crc32, not hash(): Python salts string hashes per process, so a hash-based
    coin would land differently every run and no result could be reproduced.
    """
    return 1 if zlib.crc32(f"{day}:{seed}".encode()) & 1 else -1


def run(df: pd.DataFrame, cfg: OrbConfig) -> pd.DataFrame:
    """One row per trade. `df` holds UTC-indexed one-minute OHLC bars."""
    fee = cfg.fee_pct / 100
    slip = cfg.slippage_bps / 10_000
    stop_slip = cfg.stop_slippage_bps / 10_000
    range_end = (pd.Timestamp.combine(pd.Timestamp("2000-01-01").date(), cfg.open_time)
                 + pd.Timedelta(minutes=cfg.range_minutes)).time()
    rows = []

    for day, bars in _session_days(df, cfg):
        clock = bars.index.time
        opening = bars[clock < range_end]
        # A range needs its first minute and nearly all the rest; a session
        # that starts late or has holes in its first five minutes is skipped
        # rather than measured on a range it never had.
        if len(opening) < cfg.range_minutes - 1 or opening.index[0].time() != cfg.open_time:
            continue
        hi, lo = float(opening["high"].max()), float(opening["low"].min())
        if not hi > lo:
            continue

        after = bars[clock >= range_end]
        o = after["open"].to_numpy()
        h = after["high"].to_numpy()
        l = after["low"].to_numpy()
        c = after["close"].to_numpy()
        n = len(after)

        signal = None
        for i in range(n - 1):            # the last bar has no next minute
            if c[i] > hi:
                signal = (i, 1)
                break
            if c[i] < lo:
                signal = (i, -1)
                break
        if signal is None:
            continue

        i, brk = signal
        k = i + 1
        anchor = lo if brk == 1 else hi             # opposite side of the range
        dist = (o[k] - anchor) * brk
        if dist <= 0:
            continue                                # entry already beyond it
        # The null model keeps the day, the minute and the distance and only
        # draws the direction, so whatever it earns came from the geometry.
        side = _coin(day, cfg.seed) if cfg.direction == "coin" else brk
        stop_level = o[k] - side * dist             # == anchor for a breakout
        entry = o[k] * (1 + side * slip)
        risk = (entry - stop_level) * side
        stop = stop_level if cfg.stop == "range" else None
        target = entry + side * cfg.target_r * risk if cfg.target_r else None

        exit_px, reason, j = None, "session_end", n - 1
        for j in range(k, n):
            if stop is not None:
                hit = l[j] <= stop if side == 1 else h[j] >= stop
                if hit:
                    base = min(o[j], stop) if side == 1 else max(o[j], stop)
                    exit_px = base * (1 - side * stop_slip)
                    reason = "stop"
                    break
            if target is not None:
                hit = h[j] >= target if side == 1 else l[j] <= target
                if hit:
                    exit_px, reason = target, "target"
                    break
        if exit_px is None:
            j = n - 1
            exit_px = c[j] * (1 - side * slip)

        r_gross = (exit_px - entry) * side / risk
        cost_r = fee * (entry + exit_px) / risk
        rows.append({
            "day": pd.Timestamp(day), "side": "long" if side == 1 else "short",
            "entry_time": after.index[k], "exit_time": after.index[j],
            "entry": entry, "exit": exit_px, "risk": risk,
            "r_gross": r_gross, "cost_r": cost_r, "r": r_gross - cost_r,
            "exit_reason": reason, "range_pct": (hi - lo) / lo * 100,
        })

    return pd.DataFrame(rows, columns=TRADE_COLUMNS)


def summarise(trades: pd.DataFrame) -> dict:
    """The numbers that decide whether a variant carries."""
    if trades.empty:
        return {"trades": 0}
    r = trades["r"].to_numpy()
    n = len(r)
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    sd = r.std(ddof=1) if n > 1 else 0.0
    se = sd / np.sqrt(n) if n > 1 else np.nan
    curve = np.cumsum(r)
    dd = (curve - np.maximum.accumulate(np.concatenate([[0.0], curve]))[1:]).min()
    return {
        "trades": n,
        "win_rate": round(float((r > 0).mean() * 100), 2),
        "exp_r": round(float(r.mean()), 4),
        "ci_low": round(float(r.mean() - 1.96 * se), 4),
        "ci_high": round(float(r.mean() + 1.96 * se), 4),
        "t": round(float(r.mean() / se), 2) if se and se > 0 else np.nan,
        "pf": round(float(wins / losses), 3) if losses > 0 else np.inf,
        "total_r": round(float(r.sum()), 1),
        "max_dd_r": round(float(dd), 1),
        "cost_r": round(float(trades["cost_r"].mean()), 4),
        "range_pct": round(float(trades["range_pct"].median()), 3),
    }
