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
    # Size of the candle whose close is the signal. 1 checks every minute; 5 or
    # 15 waits for a 5- or 15-minute candle on the grid from the end of the
    # range to close beyond it. Stops and targets are still checked minute by
    # minute after entry, so the order of stop and target inside a large
    # candle never has to be guessed.
    signal_minutes: int = 1
    open_time: time = time(9, 30)
    close_time: time = time(16, 0)
    # Where the stop goes: "range" = opposite side of the range, "today" =
    # today's extreme from 00:00 New York up to the entry, "prev_day" =
    # yesterday's extreme (00:00-24:00 New York), "none" = no stop.
    stop: str = "range"
    target_r: float | None = None
    # Where the target goes: "r" = target_r times risk, "today" = today's
    # opposite extreme before the entry, "prev_day" = yesterday's. A level on
    # the wrong side of the entry means no target: held to the session end.
    target_mode: str = "r"
    weekdays: tuple[int, ...] | None = None   # 0 = Monday; None = every day
    fee_pct: float = 0.05        # per side
    slippage_bps: float = 3.0    # on entry and on market exits
    stop_slippage_bps: float = 5.0
    direction: str = "breakout"  # "breakout", or "coin" for the null model
    seed: int = 7                # only used by the coin flip


TRADE_COLUMNS = ["day", "side", "entry_time", "exit_time", "entry", "exit",
                 "risk", "r_gross", "cost_r", "r", "exit_reason", "range_pct",
                 # diagnostics
                 "signal_time", "weekday", "prev_range_pct", "has_target",
                 "mfe_r", "mae_r", "mfe_session_r", "mae_session_r",
                 "after_stop_back_to_entry", "after_stop_reached_2r",
                 "after_stop_minutes_to_entry"]


def _daily_levels(df: pd.DataFrame, open_time: time) -> dict:
    """Per New York date: the full day's high/low and the part before the open."""
    local = df.tz_convert(NY)
    dates = local.index.date
    day = local[["high", "low"]].groupby(dates).agg({"high": "max", "low": "min"})
    pre = local[local.index.time < open_time]
    before = pre[["high", "low"]].groupby(pre.index.date).agg({"high": "max", "low": "min"})
    return {"day": day, "pre": before}


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
    levels = _daily_levels(df, cfg.open_time)
    day_hl, pre_hl = levels["day"], levels["pre"]
    one_day = pd.Timedelta(days=1)

    for day, bars in _session_days(df, cfg):
        if cfg.weekdays is not None and day.weekday() not in cfg.weekdays:
            continue
        prev = (pd.Timestamp(day) - one_day).date()
        prev_hi = float(day_hl["high"].get(prev, np.nan))
        prev_lo = float(day_hl["low"].get(prev, np.nan))
        pre_hi = float(pre_hl["high"].get(day, np.nan))
        pre_lo = float(pre_hl["low"].get(day, np.nan))
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

        # Candle boundaries on the grid that starts where the range ends. A
        # candle's close is only known at its last minute, so only those
        # minutes can carry a signal.
        start = range_end.hour * 60 + range_end.minute
        mins = np.array([t.hour * 60 + t.minute for t in after.index.time]) - start
        block = mins // cfg.signal_minutes
        closes_candle = np.r_[block[1:] != block[:-1], True]

        signal = None
        for i in range(n - 1):            # the last bar has no next minute
            if not closes_candle[i]:
                continue
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
        entry = o[k] * (1 + side * slip)

        # Today's extremes up to the entry: before the open, the range itself,
        # and everything from the end of the range through the signal candle.
        today_hi = np.nanmax([pre_hi, hi, h[:k].max()])
        today_lo = np.nanmin([pre_lo, lo, l[:k].min()])

        if cfg.stop in ("range", "none"):
            stop_level = o[k] - side * dist             # == anchor for a breakout
        elif cfg.stop == "today":
            stop_level = today_lo if side == 1 else today_hi
        elif cfg.stop == "prev_day":
            stop_level = prev_lo if side == 1 else prev_hi
        else:
            raise ValueError(f"unknown stop {cfg.stop!r}")
        if not np.isfinite(stop_level):
            continue
        risk = (entry - stop_level) * side
        if risk <= 0:
            continue                    # the level is already on the wrong side
        stop = None if cfg.stop == "none" else stop_level

        if cfg.target_mode == "r":
            target = entry + side * cfg.target_r * risk if cfg.target_r else None
        else:
            # A target is a level that existed before the breakout: the high or
            # low from before the open, or the range. Counting the breakout
            # candle itself would put the target on its own wick, a hair above
            # the entry, and measure nothing.
            before_hi, before_lo = np.nanmax([pre_hi, hi]), np.nanmin([pre_lo, lo])
            level = {("today", 1): before_hi, ("today", -1): before_lo,
                     ("prev_day", 1): prev_hi, ("prev_day", -1): prev_lo}[(cfg.target_mode, side)]
            target = level if np.isfinite(level) and (level - entry) * side > 0 else None

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

        # How far the trade ran either way while it was open, and over the whole
        # rest of the session regardless of the exit.
        fav, adv = (h, l) if side == 1 else (l, h)
        def excursion(a, b):
            best = (fav[a:b + 1].max() if side == 1 else fav[a:b + 1].min())
            worst = (adv[a:b + 1].min() if side == 1 else adv[a:b + 1].max())
            return (best - entry) * side / risk, (worst - entry) * side / risk
        mfe, mae = excursion(k, j)
        mfe_s, mae_s = excursion(k, n - 1)

        # After a stop: does price come back to the entry, or on to where a 2R
        # target would have been, before the session ends?
        back = reach2 = minutes_back = np.nan
        if reason == "stop" and j < n - 1:
            rest = fav[j + 1:]
            hits = (rest >= entry) if side == 1 else (rest <= entry)
            back = bool(hits.any())
            minutes_back = float(np.argmax(hits) + 1) if back else np.nan
            two_r = entry + side * 2 * risk
            reach2 = bool(((rest >= two_r) if side == 1 else (rest <= two_r)).any())

        rows.append({
            "day": pd.Timestamp(day), "side": "long" if side == 1 else "short",
            "entry_time": after.index[k], "exit_time": after.index[j],
            "entry": entry, "exit": exit_px, "risk": risk,
            "r_gross": r_gross, "cost_r": cost_r, "r": r_gross - cost_r,
            "exit_reason": reason, "range_pct": (hi - lo) / lo * 100,
            "signal_time": after.index[i].strftime("%H:%M"),
            "weekday": day.weekday(),
            "prev_range_pct": (prev_hi - prev_lo) / prev_lo * 100 if np.isfinite(prev_lo) else np.nan,
            "has_target": target is not None,
            "mfe_r": mfe, "mae_r": mae, "mfe_session_r": mfe_s, "mae_session_r": mae_s,
            "after_stop_back_to_entry": back, "after_stop_reached_2r": reach2,
            "after_stop_minutes_to_entry": minutes_back,
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
