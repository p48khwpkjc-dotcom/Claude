"""Part 2 of SESSION_ANMELDUNG.md: stop and target variants, weekday filters.

    python research/orb_variants.py BTCUSDT ETHUSDT SOLUSDT XRPUSDT

Exploration window only. Writes every cell, then applies the registered rule
across this part and the session-hold part:

  1. pooled over the four coins: expectancy after costs positive, 95% interval
     above zero;
  2. positive in both halves of the four years;
  3. positive on at least three of the four coins.

Among the variants that pass, the one with the largest t-statistic is the
single candidate for the locked year. If none passes, that is the result.
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
DAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

VARIANTS = [
    ("Basis, Stop Range, 2R", dict(stop="range", target_r=2.0)),
    ("Basis, Stop Range, 3R", dict(stop="range", target_r=3.0)),
    ("Stop Tagestief, 2R", dict(stop="today", target_r=2.0)),
    ("Stop Tagestief, 3R", dict(stop="today", target_r=3.0)),
    ("Stop Vortagestief, 2R", dict(stop="prev_day", target_r=2.0)),
    ("Stop Vortagestief, 3R", dict(stop="prev_day", target_r=3.0)),
    ("Stop Range, Ziel Tageshoch", dict(stop="range", target_mode="today")),
    ("Stop Range, Ziel Vortageshoch", dict(stop="range", target_mode="prev_day")),
] + [(f"nur {d}, Stop Range, 2R", dict(stop="range", target_r=2.0, weekdays=(i,)))
     for i, d in enumerate(DAYS)]


def stats(r: np.ndarray) -> dict:
    n = len(r)
    if n < 2:
        return {"n": n, "mean": np.nan, "t": np.nan, "ci_low": np.nan}
    se = r.std(ddof=1) / np.sqrt(n)
    return {"n": n, "mean": r.mean(), "t": r.mean() / se, "ci_low": r.mean() - 1.96 * se,
            "ci_high": r.mean() + 1.96 * se, "win": (r > 0).mean() * 100}


def main() -> int:
    symbols = sys.argv[1:] or ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    trades = []
    for sym in symbols:
        df = read_cache(cache_path(Path("data/cache"), sym, "1m"))
        df = df[df.index < LOCK]
        for frame, (rng, sig) in FRAMES.items():
            for label, v in VARIANTS:
                t = run(df, OrbConfig(range_minutes=rng, signal_minutes=sig, **v, **COST))
                t = t.assign(symbol=sym, kerze=frame, variante=label)
                trades.append(t)
                s = stats(t["r"].to_numpy())
                print(f"  {sym:8s} {frame:3s} {label:32s} n={s['n']:5d}  "
                      f"E={s['mean']:+.3f}R  t={s['t']:+.2f}", flush=True)
    all_t = pd.concat(trades, ignore_index=True)
    all_t.to_parquet("research/orb_variants_trades.parquet")

    rows = []
    for (frame, label), g in all_t.groupby(["kerze", "variante"], sort=False):
        mid = g["day"].min() + (g["day"].max() - g["day"].min()) / 2
        pooled = stats(g["r"].to_numpy())
        h1, h2 = stats(g[g.day < mid]["r"].to_numpy()), stats(g[g.day >= mid]["r"].to_numpy())
        per = {sym: stats(x["r"].to_numpy())["mean"] for sym, x in g.groupby("symbol")}
        rows.append({"kerze": frame, "variante": label, "trades": pooled["n"],
                     "treffer_%": round(pooled.get("win", np.nan), 1),
                     "E_R": round(pooled["mean"], 4), "ci_low": round(pooled["ci_low"], 4),
                     "t": round(pooled["t"], 2), "1_haelfte": round(h1["mean"], 4),
                     "2_haelfte": round(h2["mean"], 4),
                     "coins_positiv": sum(v > 0 for v in per.values()),
                     **{s.replace("USDT", ""): round(v, 3) for s, v in per.items()},
                     "ohne_ziel_%": round(100 * (1 - g["has_target"].mean()), 1)})
    out = pd.DataFrame(rows)
    out["besteht"] = ((out.E_R > 0) & (out.ci_low > 0) & (out["1_haelfte"] > 0)
                      & (out["2_haelfte"] > 0) & (out.coins_positiv >= 3))
    out.to_csv("research/orb_variants.csv", index=False)
    pd.set_option("display.width", 260)
    print("\n=== Alle Varianten, gepoolt über die Coins, nach Kosten ===")
    print(out.to_string(index=False))
    print(f"\nGerechnete Varianten: {len(out)}; die Regel bestehen: {int(out.besteht.sum())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
