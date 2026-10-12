"""Opening range breakout with 1-, 5- and 15-minute signal candles.

    python research/orb_timeframes.py BTCUSDT    # or SOLUSDT, ETHUSDT, XRPUSDT

The follow-up asked for after the first run: the same breakout, but confirmed
on a 5- or 15-minute close instead of a 1-minute one, stop at the opposite side
of the range, targets from 1:1 to 5:1 in steps of 0.5, otherwise out at 16:00.

    1m   range = first 5 minutes,      signal = first 1-minute close beyond it
    5m   range = first 5-minute candle,  signal = first 5-minute close beyond it
    15m  range = first 15-minute candle, signal = first 15-minute close beyond it

Stops and targets are checked on one-minute bars after entry in every case.
Reported for every day (as registered) and for weekdays only (where a New York
open actually happens -- a post-hoc cut, labelled as one), with costs, without
costs and as a coin flip, and split into first and second half.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daytrader.backtest.orb import OrbConfig, run, summarise  # noqa: E402
from daytrader.data.loader import cache_path, read_cache  # noqa: E402

COST = dict(fee_pct=0.05, slippage_bps=3.0, stop_slippage_bps=5.0)
FREE = dict(fee_pct=0.0, slippage_bps=0.0, stop_slippage_bps=0.0)
FRAMES = {"1m": (5, 1), "5m": (5, 5), "15m": (15, 15)}     # (range, signal) minutes
TARGETS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]


def halves(t: pd.DataFrame):
    mid = t["day"].min() + (t["day"].max() - t["day"].min()) / 2
    return t[t["day"] < mid], t[t["day"] >= mid]


def main() -> int:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    df = read_cache(cache_path(Path("data/cache"), symbol, "1m"))
    if df is None:
        raise SystemExit(f"kein 1m-Cache für {symbol}")
    print(f"{symbol}: {len(df):,} Minuten, {df.index[0].date()} .. {df.index[-1].date()}\n")
    weekdays = df[df.tz_convert("America/New_York").index.weekday < 5]
    rows = []
    for days, data in [("alle Tage", df), ("Werktage", weekdays)]:
        for frame, (rng, sig) in FRAMES.items():
            for k in TARGETS:
                base = dict(range_minutes=rng, signal_minutes=sig, stop="range", target_r=k)
                real = run(data, OrbConfig(**base, **COST))
                s = summarise(real)
                s0 = summarise(run(data, OrbConfig(**base, **FREE)))
                sc = summarise(run(data, OrbConfig(**base, **COST, direction="coin")))
                a, b = halves(real)
                rows.append({"tage": days, "kerze": frame, "rr": k, **s,
                             "exp_r_ohne_kosten": s0["exp_r"], "t_ohne_kosten": s0["t"],
                             "exp_r_muenzwurf": sc["exp_r"],
                             "exp_r_1_haelfte": summarise(a)["exp_r"],
                             "exp_r_2_haelfte": summarise(b)["exp_r"]})
                print(f"  {days:9s} {frame:3s} {k:.1f}:1  n={s['trades']:5d}  "
                      f"Treffer {s['win_rate']:5.1f}%  E={s['exp_r']:+.3f}R "
                      f"[{s['ci_low']:+.3f},{s['ci_high']:+.3f}]  ohne Kosten {s0['exp_r']:+.3f}  "
                      f"Münzwurf {sc['exp_r']:+.3f}", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(f"research/orb_{symbol}_kerzen.csv", index=False)
    pd.set_option("display.width", 250)
    for days in ["alle Tage", "Werktage"]:
        d = out[out.tage == days]
        print(f"\n===== {days} =====")
        for col, title in [("win_rate", "Trefferquote %"), ("exp_r", "Erwartungswert mit Kosten (R)"),
                           ("exp_r_ohne_kosten", "Erwartungswert ohne Kosten (R)"),
                           ("exp_r_muenzwurf", "Münzwurf mit Kosten (R)"),
                           ("cost_r", "Kosten je Trade (R)")]:
            print(f"\n{title}")
            print(d.pivot(index="rr", columns="kerze", values=col)[list(FRAMES)].round(3).to_string())
    print(f"\nGerechnete Zellen: {len(out)}. Bei so vielen ist die beste auch zufällig gut.")
    pos = out[(out.ci_low > 0)]
    print(f"Zellen mit Kosten und 95-%-Intervall ganz über null: {len(pos)}")
    if len(pos):
        print(pos[["tage", "kerze", "rr", "trades", "exp_r", "ci_low", "exp_r_1_haelfte",
                   "exp_r_2_haelfte"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
