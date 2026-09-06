"""Does a good train result predict anything at all?

This is not a second attempt at picking a winner -- the protocol closed that
question when the candidate failed on test, and the holdout stays shut. It
asks a different thing: across every cell that cleared the train hurdles, how
much of the train ranking survives into test? If the answer is "none", then a
high train profit factor carries no information, and any search built on one
is picking noise however carefully it is fenced.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from search import HTF, load, run_cell  # noqa: E402

train = pd.read_csv("research/search_train.csv")
surv = train[train.passes].sort_values("pf", ascending=False)

cache: dict[str, dict] = {}
rows = []
for r in surv.itertuples(index=False):
    if r.interval not in cache:
        cache[r.interval] = load(r.interval)
    c = run_cell(r.strategy, r.interval, HTF[r.interval], int(r.hold_h),
                 cache[r.interval], "test")
    rows.append({"strategy": r.strategy, "interval": r.interval, "hold_h": int(r.hold_h),
                 "pf_train": r.pf, "pf_test": c.profit_factor,
                 "n_train": int(r.trades), "n_test": c.trades,
                 "sym_train": f"{int(r.sym_ok)}/{int(r.sym)}",
                 "sym_test": f"{c.symbols_profitable}/{c.symbols}"})
    print(f"  {r.strategy:22s} {r.interval:3s} {int(r.hold_h):3d}h  "
          f"train PF {r.pf:5.2f} -> test PF {c.profit_factor:5.2f}", flush=True)

d = pd.DataFrame(rows)
d.to_csv("research/transfer.csv", index=False)
print(f"\nKombinationen, die die Train-Hürden nahmen: {len(d)}")
print(f"davon auf test noch über PF 1,0:            {(d.pf_test > 1.0).sum()}")
print(f"Median Profitfaktor train: {d.pf_train.median():.3f}")
print(f"Median Profitfaktor test:  {d.pf_test.median():.3f}")
if len(d) > 2:
    print(f"Rangkorrelation train->test: {d.pf_train.rank().corr(d.pf_test.rank()):.3f}")
