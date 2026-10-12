"""Hold crypto through one part of the day only: overnight, intraday, by session.

Registered in SESSION_ANMELDUNG.md, part 3. Every holding window buys at a
fixed clock time and sells at another, every day, long only, and pays one full
round trip of costs each time -- which is the whole question, because a daily
round trip costs about 0.16% and has to be earned back every single day.

    python research/session_hold.py BTCUSDT            # exploration window
    python research/session_hold.py BTCUSDT --locked   # the locked year. Once.

Prices are the open of the one-minute bar at the clock time, in New York time
for the New York windows and in UTC for the three trading sessions, so both
move with the clock they are named after.
"""

from __future__ import annotations

import argparse
import sys
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from daytrader.data.loader import cache_path, read_cache  # noqa: E402

LOCK = pd.Timestamp("2025-10-12", tz="UTC")
COST_PCT = 2 * (0.05 + 0.03)             # fee + slippage, both sides, in percent
NY = "America/New_York"

# name: (tz, buy time, sell time, days between buy and sell, buy weekdays)
WINDOWS = {
    "über Nacht (16:00→09:30 NY)": (NY, time(16, 0), time(9, 30), 1, None),
    "tagsüber (09:30→16:00 NY)":   (NY, time(9, 30), time(16, 0), 0, None),
    "Asien (00:00→08:00 UTC)":     ("UTC", time(0, 0), time(8, 0), 0, None),
    "Europa (08:00→13:30 UTC)":    ("UTC", time(8, 0), time(13, 30), 0, None),
    "USA (13:30→20:00 UTC)":       ("UTC", time(13, 30), time(20, 0), 0, None),
    "spät (20:00→24:00 UTC)":      ("UTC", time(20, 0), time(0, 0), 1, None),
    "Wochenende (Fr 16:00→Mo 09:30 NY)": (NY, time(16, 0), time(9, 30), 3, (4,)),
}
WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def window_returns(opens: pd.Series, tz: str, buy: time, sell: time,
                   days_later: int, weekdays) -> pd.DataFrame:
    """One row per holding window: buy date, gross and net return in percent."""
    start = opens.index[0].tz_convert(tz).normalize().tz_localize(None)
    end = opens.index[-1].tz_convert(tz).normalize().tz_localize(None)
    dates = pd.date_range(start, end, freq="D")
    if weekdays is not None:
        dates = dates[dates.weekday.isin(weekdays)]
    t_buy = pd.DatetimeIndex([pd.Timestamp.combine(d, buy) for d in dates]).tz_localize(
        tz, nonexistent="shift_forward", ambiguous=False).tz_convert("UTC")
    t_sell = pd.DatetimeIndex([pd.Timestamp.combine(d + pd.Timedelta(days=days_later), sell)
                               for d in dates]).tz_localize(
        tz, nonexistent="shift_forward", ambiguous=False).tz_convert("UTC")
    tol = pd.Timedelta(minutes=5)
    p_buy = opens.reindex(t_buy, method="bfill", tolerance=tol).to_numpy()
    p_sell = opens.reindex(t_sell, method="bfill", tolerance=tol).to_numpy()
    gross = (p_sell / p_buy - 1) * 100
    out = pd.DataFrame({"buy": t_buy, "weekday": dates.weekday, "gross": gross})
    out = out.dropna()
    out["net"] = out["gross"] - COST_PCT
    return out


def stats(x: pd.Series) -> dict:
    n = len(x)
    if n < 2:
        return {"n": n}
    se = x.std(ddof=1) / np.sqrt(n)
    return {"n": n, "mean": round(x.mean(), 4), "t": round(x.mean() / se, 2),
            "ci_low": round(x.mean() - 1.96 * se, 4), "ci_high": round(x.mean() + 1.96 * se, 4),
            "win": round((x > 0).mean() * 100, 1), "sum": round(x.sum(), 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--locked", action="store_true", help="the locked year instead")
    args = ap.parse_args()

    df = read_cache(cache_path(Path("data/cache"), args.symbol, "1m"))
    df = df[df.index >= LOCK] if args.locked else df[df.index < LOCK]
    opens = df["open"]
    span = f"{df.index[0].date()} .. {df.index[-1].date()}"
    buy_hold = (df["close"].iloc[-1] / df["open"].iloc[0] - 1) * 100
    print(f"{args.symbol} {span}{'  [GESPERRTES JAHR]' if args.locked else ''}")
    print(f"Kaufen und halten über den ganzen Zeitraum: {buy_hold:+.1f} %\n")

    rows, by_day = [], []
    for name, (tz, buy, sell, later, wd) in WINDOWS.items():
        r = window_returns(opens, tz, buy, sell, later, wd)
        mid = r["buy"].iloc[0] + (r["buy"].iloc[-1] - r["buy"].iloc[0]) / 2
        g, s = stats(r["gross"]), stats(r["net"])
        h1, h2 = stats(r[r.buy < mid]["net"]), stats(r[r.buy >= mid]["net"])
        rows.append({"fenster": name, "n": s["n"], "brutto_%": g["mean"], "netto_%": s["mean"],
                     "t_netto": s["t"], "ci_low": s["ci_low"], "ci_high": s["ci_high"],
                     "gewinntage_%": s["win"], "summe_netto_%": s["sum"],
                     "1_haelfte": h1["mean"], "2_haelfte": h2["mean"]})
        for wdn, grp in r.groupby("weekday"):
            st = stats(grp["net"])
            by_day.append({"fenster": name, "tag": WEEKDAYS[wdn], "netto_%": st.get("mean"),
                           "t": st.get("t"), "n": st["n"]})

    out = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(f"Je Haltefenster, Prozent je Durchgang, Kosten {COST_PCT:.2f} % je Durchgang:")
    print(out.to_string(index=False))
    days = pd.DataFrame(by_day)
    print("\nNetto je Wochentag des Kaufs (%):")
    print(days.pivot(index="fenster", columns="tag", values="netto_%")
          .reindex(columns=[d for d in WEEKDAYS if d in set(days.tag)]).round(3).to_string())
    tag = "gesperrt" if args.locked else "explore"
    out.assign(symbol=args.symbol).to_csv(f"research/session_{args.symbol}_{tag}.csv", index=False)
    days.assign(symbol=args.symbol).to_csv(f"research/session_{args.symbol}_{tag}_tage.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
