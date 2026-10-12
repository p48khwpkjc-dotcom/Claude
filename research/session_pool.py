"""Apply the registered rule to the holding windows, pooled over the four coins.

Part 3 of SESSION_ANMELDUNG.md, exploration window only. Same three hurdles as
the breakout variants: positive with a 95% interval above zero, positive in
both halves, positive on at least three of four coins.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from session_hold import LOCK, WINDOWS, window_returns  # noqa: E402
from daytrader.data.loader import cache_path, read_cache  # noqa: E402

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]


def stats(x):
    se = x.std(ddof=1) / np.sqrt(len(x))
    return x.mean(), x.mean() - 1.96 * se, x.mean() / se


frames = []
for sym in SYMBOLS:
    df = read_cache(cache_path(Path("data/cache"), sym, "1m"))
    opens = df[df.index < LOCK]["open"]
    for name, (tz, buy, sell, later, wd) in WINDOWS.items():
        frames.append(window_returns(opens, tz, buy, sell, later, wd).assign(symbol=sym, fenster=name))
r = pd.concat(frames, ignore_index=True)

rows = []
for name, g in r.groupby("fenster", sort=False):
    mid = g.buy.min() + (g.buy.max() - g.buy.min()) / 2
    m, lo, t = stats(g.net)
    per = g.groupby("symbol").net.mean()
    gross = g.groupby("symbol").gross.mean()
    rows.append({"fenster": name, "n": len(g), "brutto_%": round(g.gross.mean(), 4),
                 "netto_%": round(m, 4), "ci_low": round(lo, 4), "t": round(t, 2),
                 "1_haelfte": round(g[g.buy < mid].net.mean(), 4),
                 "2_haelfte": round(g[g.buy >= mid].net.mean(), 4),
                 "coins_positiv": int((per > 0).sum()),
                 **{s.replace("USDT", "") + "_brutto": round(gross[s], 3) for s in SYMBOLS}})
out = pd.DataFrame(rows)
out["besteht"] = ((out["netto_%"] > 0) & (out.ci_low > 0) & (out["1_haelfte"] > 0)
                  & (out["2_haelfte"] > 0) & (out.coins_positiv >= 3))
pd.set_option("display.width", 250)
print("Haltefenster, gepoolt über BTC/ETH/SOL/XRP, Prozent je Durchgang (Kosten 0,16 %):")
print(out.to_string(index=False))
print(f"\nDie Regel bestehen: {int(out.besteht.sum())} von {len(out)}")
out.to_csv("research/session_pool.csv", index=False)
