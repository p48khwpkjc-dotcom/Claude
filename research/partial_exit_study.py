"""What scaling out does to the win rate, and what it does to the money.

Three exit policies, identical entries, identical stops and targets:

  A  no partial                      -- the baseline
  B  take half off at 75% of the way to target, stop stays put
  C  the same, then move the stop to entry ("risk-free runner")

C is the one that produces the win rates people quote, because it converts
trades that would have been small losses into small wins. The question this
answers is whether it also converts them into money.

random_entry is included as the null model: whatever it scores at a given
target is the part of a win rate that is geometry rather than information.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from search import HTF, load, run_cell  # noqa: E402

STRATEGIES = ["random_entry", "momentum_persistence", "donchian_breakout",
              "vol_expansion", "keltner_trend", "fair_value_gap",
              "order_block", "squeeze_breakout"]
TARGETS = [2.0, 3.0]

POLICIES = {
    "A ohne Teilverkauf":      {},
    "B Teil bei 75%":          {"partial_at_r_frac": 0.75, "partial_fraction": 0.5},
    "C Teil bei 75% + BE":     {"partial_at_r_frac": 0.75, "partial_fraction": 0.5,
                                "breakeven_after_partial": True},
}


def main() -> int:
    interval = sys.argv[1] if len(sys.argv) > 1 else "4h"
    hold = int(sys.argv[2]) if len(sys.argv) > 2 else 96
    data = load(interval)
    rows = []
    for name in STRATEGIES:
        for k in TARGETS:
            for label, pol in POLICIES.items():
                exe = {}
                if pol:
                    exe = {"partial_at_r": pol["partial_at_r_frac"] * k,
                           "partial_fraction": pol["partial_fraction"],
                           "breakeven_after_partial": pol.get("breakeven_after_partial", False)}
                c = run_cell(name, interval, HTF[interval], hold, data, "train",
                             overrides={"target_r": k, "trail_atr_mult": 0.0},
                             execution=exe)
                rows.append({"strategy": name, "target_r": k, "policy": label,
                             "trades": c.trades, "win_rate": c.win_rate,
                             "pf": c.profit_factor, "exp_r": c.expectancy_r})
                print(f"  {name:22s} {k:.0f}R  {label:22s} "
                      f"n={c.trades:6d}  Treffer {c.win_rate:5.1f}%  "
                      f"PF={c.profit_factor:5.2f}  E={c.expectancy_r:+.4f}", flush=True)
    d = pd.DataFrame(rows)
    d.to_csv(f"research/partial_{interval}_{hold}h.csv", index=False)
    for metric, title in [("win_rate", "Trefferquote in %"),
                          ("exp_r", "Erwartungswert in R")]:
        print(f"\n=== {title} ===")
        print(d.pivot_table(index=["strategy", "target_r"], columns="policy",
                            values=metric).round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
