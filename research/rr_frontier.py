"""What win rate is actually reachable at each risk-reward ratio?

The question behind this is not "does strategy X work" but "can any of these
produce 70% winners at 2:1". That is answerable without searching, because win
rate and reward-to-risk trade off against each other mechanically: the further
away the target, the less often price gets there before the stop. Measuring the
whole curve for every strategy says what is on the table and what is not.

Trailing is switched off and the target set to exactly k times risk, so a
"win" means precisely one thing: price reached +kR before it reached -1R, with
the engine's pessimistic tie-break (stop first) intact. Runs on `train` only.

Break-even win rate at kR, ignoring costs, is 1/(1+k): 50% at 1:1, 33% at 2:1,
25% at 3:1. Costs push each of those up by a few points.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from search import HTF, load, run_cell, SYMBOLS  # noqa: E402

TARGETS = [1.0, 1.5, 2.0, 2.5, 3.0]
STRATEGIES = [
    # the ICT / smart-money models
    "fair_value_gap", "liquidity_sweep", "order_block", "failed_breakout",
    # the best of everything found so far, for comparison
    "donchian_breakout", "vol_expansion", "keltner_trend", "momentum_persistence",
    "opening_range", "squeeze_breakout",
]


def frontier(interval: str, hold_h: int) -> pd.DataFrame:
    data = load(interval)
    rows = []
    for name in STRATEGIES:
        for k in TARGETS:
            over = {"target_r": k, "trail_atr_mult": 0.0}
            c = run_cell(name, interval, HTF[interval], hold_h, data, "train",
                         overrides=over)
            need = 100.0 / (1.0 + k)          # break-even win rate before costs
            rows.append({"strategy": name, "target_r": k, "trades": c.trades,
                         "win_rate": c.win_rate, "breakeven_wr": round(need, 1),
                         "edge_pp": round(c.win_rate - need, 1),
                         "pf": c.profit_factor, "exp_r": c.expectancy_r})
            print(f"  {name:22s} {k:.1f}R  n={c.trades:6d}  "
                  f"Treffer {c.win_rate:5.1f}%  (break-even {need:4.1f}%)  "
                  f"PF={c.profit_factor:5.2f}", flush=True)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    interval = sys.argv[1] if len(sys.argv) > 1 else "4h"
    hold = int(sys.argv[2]) if len(sys.argv) > 2 else 96
    print(f"Trefferquote je Ziel-R auf {interval}, Haltedauer {hold}h, Segment train\n")
    d = frontier(interval, hold)
    d.to_csv(f"research/frontier_{interval}_{hold}h.csv", index=False)
    print("\n=== Trefferquote in % ===")
    print(d.pivot(index="strategy", columns="target_r", values="win_rate").round(1).to_string())
    print("\n=== Trades ===")
    print(d.pivot(index="strategy", columns="target_r", values="trades").to_string())
    hit = d[(d.target_r >= 2.0) & (d.win_rate >= 70.0) & (d.trades >= 100)]
    print(f"\nKombinationen mit >=70% Treffern bei >=2R und >=100 Trades: {len(hit)}")
    if len(hit):
        print(hit.to_string(index=False))
