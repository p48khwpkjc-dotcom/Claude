"""Why does the opening range breakout lose? Part 1 of SESSION_ANMELDUNG.md.

    python research/orb_diagnose.py BTCUSDT ETHUSDT SOLUSDT XRPUSDT

Runs on the exploration window only (before 2025-10-12). Every number is shown
next to the coin flip -- the same day, the same minute, the same distance, a
random direction -- because some share of everything below happens by chance
alone, and only the gap to the coin flip is the breakout's doing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from daytrader.backtest.orb import OrbConfig, run  # noqa: E402
from daytrader.data.loader import cache_path, read_cache  # noqa: E402

LOCK = pd.Timestamp("2025-10-12", tz="UTC")
COST = dict(fee_pct=0.05, slippage_bps=3.0, stop_slippage_bps=5.0)
FRAMES = {"1m": (5, 1), "15m": (15, 15)}
WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def pct(x) -> str:
    return f"{100 * np.nanmean(x):5.1f}%" if len(x) else "   – "


def report(symbol: str) -> list[dict]:
    df = read_cache(cache_path(Path("data/cache"), symbol, "1m"))
    df = df[df.index < LOCK]
    rows = []
    print(f"\n################ {symbol}  {df.index[0].date()} .. {df.index[-1].date()} ################")
    for frame, (rng, sig) in FRAMES.items():
        base = dict(range_minutes=rng, signal_minutes=sig)
        stop = run(df, OrbConfig(**base, **COST, stop="range"))
        stop_c = run(df, OrbConfig(**base, **COST, stop="range", direction="coin"))
        free = run(df, OrbConfig(**base, **COST, stop="none"))
        free_c = run(df, OrbConfig(**base, **COST, stop="none", direction="coin"))

        print(f"\n=== {frame}-Ausbruch, Stop an der Range, kein Ziel ({len(stop)} Trades) ===")
        s, c = stop[stop.exit_reason == "stop"], stop_c[stop_c.exit_reason == "stop"]
        print(f"  ausgestoppt:                         Ausbruch {pct(stop.exit_reason == 'stop')}"
              f"   Münzwurf {pct(stop_c.exit_reason == 'stop')}")
        print(f"  davon später zurück am Einstieg:     Ausbruch {pct(s.after_stop_back_to_entry.astype(float))}"
              f"   Münzwurf {pct(c.after_stop_back_to_entry.astype(float))}")
        print(f"  davon später bis zum 2R-Ziel:        Ausbruch {pct(s.after_stop_reached_2r.astype(float))}"
              f"   Münzwurf {pct(c.after_stop_reached_2r.astype(float))}")
        if len(s):
            print(f"  Minuten bis zurück am Einstieg (Median): "
                  f"{np.nanmedian(s.after_stop_minutes_to_entry):.0f}")

        print(f"\n  Bis 16:00 gehalten, ohne Stop ({len(free)} Trades): wie weit läuft der Kurs?")
        for lvl in (1, 2, 3):
            print(f"    erreicht +{lvl}R irgendwann:            Ausbruch {pct(free.mfe_session_r >= lvl)}"
                  f"   Münzwurf {pct(free_c.mfe_session_r >= lvl)}")
        print(f"    fällt zuerst unter −1R (durch den Stop): Ausbruch {pct(free.mae_session_r <= -1)}"
              f"   Münzwurf {pct(free_c.mae_session_r <= -1)}")

        winners = free[free.r_gross > 0]
        if len(winners):
            m = winners.mae_session_r
            print(f"\n  Spätere Gewinner ({len(winners)}): wie tief gingen sie vorher ins Minus?")
            for lo, hi, lab in [(-0.5, 0.01, "weniger als 0,5R"), (-1.0, -0.5, "0,5R bis 1R"),
                                (-1.5, -1.0, "1R bis 1,5R  (Range-Stop hätte sie gekillt)"),
                                (-99, -1.5, "mehr als 1,5R")]:
                share = ((m > lo) & (m <= hi)).mean() if hi != 0.01 else (m > lo).mean()
                print(f"    {lab:45s} {100 * share:5.1f}%")

        print("\n  Nach Wochentag (Range-Stop, bis 16:00, Erwartungswert nach Kosten in R):")
        wd = stop.groupby("weekday")["r"].agg(["count", "mean"])
        print("    " + "  ".join(f"{WEEKDAYS[i]} {r['mean']:+.2f} (n={int(r['count'])})"
                                  for i, r in wd.iterrows()))
        bins = ["09:35", "10:00", "11:00", "13:00", "16:00"] if frame == "1m" \
            else ["09:45", "10:00", "11:00", "13:00", "16:00"]
        stop["bucket"] = pd.cut(pd.to_datetime(stop.signal_time, format="%H:%M").dt.hour * 60
                                + pd.to_datetime(stop.signal_time, format="%H:%M").dt.minute,
                                [int(b[:2]) * 60 + int(b[3:]) - 1 for b in bins],
                                labels=[f"{bins[i]}–{bins[i + 1]}" for i in range(len(bins) - 1)])
        tb = stop.groupby("bucket", observed=False)["r"].agg(["count", "mean"])
        print("  Nach Uhrzeit des Signals:")
        print("    " + "  ".join(f"{b} {r['mean']:+.2f} (n={int(r['count'])})" for b, r in tb.iterrows()))
        stop["rel"] = stop.range_pct / stop.prev_range_pct
        q = pd.qcut(stop.rel, 4, labels=["schmalste", "2.", "3.", "breiteste"])
        rq = stop.groupby(q, observed=False)["r"].agg(["count", "mean"])
        print("  Nach Breite der Range im Verhältnis zur Vortagesspanne (Viertel):")
        print("    " + "  ".join(f"{b} {r['mean']:+.2f}" for b, r in rq.iterrows()))

        rows.append({"symbol": symbol, "kerze": frame, "trades": len(stop),
                     "anteil_ausgestoppt": (stop.exit_reason == "stop").mean(),
                     "zurueck_am_einstieg": s.after_stop_back_to_entry.astype(float).mean(),
                     "zurueck_am_einstieg_muenzwurf": c.after_stop_back_to_entry.astype(float).mean(),
                     "bis_2r_nach_stop": s.after_stop_reached_2r.astype(float).mean(),
                     "bis_2r_nach_stop_muenzwurf": c.after_stop_reached_2r.astype(float).mean(),
                     "erreicht_2r": (free.mfe_session_r >= 2).mean(),
                     "erreicht_2r_muenzwurf": (free_c.mfe_session_r >= 2).mean()})
    return rows


def main() -> int:
    symbols = sys.argv[1:] or ["BTCUSDT"]
    rows = []
    for sym in symbols:
        rows += report(sym)
    pd.DataFrame(rows).to_csv("research/orb_diagnose.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
