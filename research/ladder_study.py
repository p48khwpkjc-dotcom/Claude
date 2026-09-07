"""Does a staged exit plan beat leaving the trade alone?

The plan asked about, in its own words: at half way to target move the stop to
break even, at three quarters take 80% off and lift the stop to half way. It
is compared against doing nothing and against a plain break-even move, on the
timeframes a five-hour holding limit actually permits.

Everything else is held identical -- same entries, same stops, same targets --
so any difference is the exit plan and nothing else.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from search import HTF, load, run_cell  # noqa: E402

PLANS = {
    "A nichts tun": [],
    "B nur BE bei 50%": [
        {"at_tp_frac": 0.5, "close_frac": 0.0, "stop_to_tp_frac": 0.0},
    ],
    "C dein Schema": [
        {"at_tp_frac": 0.5, "close_frac": 0.0, "stop_to_tp_frac": 0.0},
        {"at_tp_frac": 0.75, "close_frac": 0.8, "stop_to_tp_frac": 0.5},
    ],
    "D wie C, ohne BE": [
        {"at_tp_frac": 0.75, "close_frac": 0.8, "stop_to_tp_frac": 0.5},
    ],
}
STRATEGIES = ["random_entry", "donchian_breakout", "vol_expansion",
              "keltner_trend", "squeeze_breakout", "fair_value_gap",
              "opening_range", "failed_breakout"]


def main() -> int:
    interval = sys.argv[1] if len(sys.argv) > 1 else "1h"
    hold = int(sys.argv[2]) if len(sys.argv) > 2 else 5      # the five-hour limit
    target = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
    data = load(interval)
    rows = []
    for name in STRATEGIES:
        for label, ladder in PLANS.items():
            c = run_cell(name, interval, HTF[interval], hold, data, "train",
                         overrides={"target_r": target, "trail_atr_mult": 0.0},
                         execution={"exit_ladder": ladder})
            rows.append({"strategy": name, "plan": label, "trades": c.trades,
                         "win_rate": c.win_rate, "pf": c.profit_factor,
                         "exp_r": c.expectancy_r})
            print(f"  {name:20s} {label:18s} n={c.trades:6d}  "
                  f"Treffer {c.win_rate:5.1f}%  PF={c.profit_factor:5.2f}  "
                  f"E={c.expectancy_r:+.4f}", flush=True)
    d = pd.DataFrame(rows)
    d.to_csv(f"research/ladder_{interval}_{hold}h_{target:g}R.csv", index=False)
    for metric, title in [("win_rate", "Trefferquote %"), ("exp_r", "Erwartungswert R")]:
        print(f"\n=== {title} ===")
        print(d.pivot(index="strategy", columns="plan", values=metric).round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
