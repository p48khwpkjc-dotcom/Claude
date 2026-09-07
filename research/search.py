"""Broad strategy search with a segment held back from the search itself.

The rules this obeys are written down in SUCHPROTOKOLL.md, before any of it
ran. The short version: history splits three ways, the search only ever sees
`train`, the single strategy that survives a fixed set of hurdles is confirmed
once on `test`, and `holdout` is opened exactly once at the very end. The
holdout run is behind a flag so that it cannot happen by accident, because a
holdout looked at twice is just another test set.

    python research/search.py                 # search train, apply the rule
    python research/search.py --confirm NAME  # one candidate on test
    python research/search.py --final NAME    # one candidate on holdout. Once.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daytrader.backtest.engine import BacktestEngine
from daytrader.backtest.metrics import compute
from daytrader.config import Config, load_config
from daytrader.data.loader import cache_path, read_cache
from daytrader.strategies import available, build

SYMBOLS = [
    # The original twelve.
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "AVAXUSDT", "LINKUSDT", "DOGEUSDT", "DOTUSDT", "LTCUSDT", "ATOMUSDT",
    # Widened so that "profitable on 60% of symbols" is a real hurdle rather
    # than a coin flip over twelve correlated majors.
    "TRXUSDT", "BCHUSDT", "ETCUSDT", "UNIUSDT", "AAVEUSDT", "NEARUSDT",
    "FILUSDT", "ICPUSDT", "HBARUSDT", "VETUSDT", "ALGOUSDT", "INJUSDT",
    "RUNEUSDT", "GRTUSDT", "SANDUSDT", "AXSUSDT",
]

# (decision interval, higher-timeframe filter, hold times in hours)
# The higher-timeframe filter must actually be higher: resampling 4h to 4h
# is a no-op, which quietly turns the trend filter into "the previous bar".
GRIDS = [("15m", "4h", [5, 12, 24]), ("1h", "4h", [12, 24, 48]), ("4h", "1d", [48, 96, 192])]

HTF = {iv: htf for iv, htf, _ in GRIDS}

# Split by calendar date, not by fraction of each symbol's history. Fractions
# move when history is added, and moving them would slide the holdout boundary
# backwards over ground that test has already been run on. These two dates are
# exactly where the original 900-day fractional split fell, so the holdout
# covers the same untouched period it always did -- and every symbol now shares
# the same boundaries instead of each having its own.
SPLITS = {
    "train":   (None,         "2025-06-13"),
    "test":    ("2025-06-13", "2026-01-24"),
    "holdout": ("2026-01-24", None),
}

# --- the hurdles, fixed in advance (SUCHPROTOKOLL.md) ------------------------
MIN_TRADES = 300
MIN_PF = 1.10
MIN_SYMBOL_SHARE = 0.60
MIN_EXPECTANCY = 0.05


def segment(df: pd.DataFrame, name: str, warmup: int) -> pd.DataFrame:
    """Slice one split, prefixed with enough history to warm the indicators."""
    lo, hi = SPLITS[name]
    a = 0 if lo is None else int(df.index.searchsorted(pd.Timestamp(lo, tz="UTC")))
    b = len(df) if hi is None else int(df.index.searchsorted(pd.Timestamp(hi, tz="UTC")))
    return df.iloc[max(0, a - warmup):b]


def load(interval: str) -> dict[str, pd.DataFrame]:
    out = {}
    for sym in SYMBOLS:
        df = read_cache(cache_path(Path("data/cache"), sym, interval))
        if df is not None and len(df) > 2000:
            out[sym] = df
    return out


@dataclass
class Cell:
    strategy: str
    interval: str
    hold_h: int
    trades: int
    win_rate: float
    profit_factor: float
    expectancy_r: float
    symbols_profitable: int
    symbols: int
    per_symbol: dict

    @property
    def symbol_share(self) -> float:
        return self.symbols_profitable / self.symbols if self.symbols else 0.0

    def passes(self) -> bool:
        return (self.trades >= MIN_TRADES
                and self.profit_factor >= MIN_PF
                and self.symbol_share >= MIN_SYMBOL_SHARE
                and self.expectancy_r >= MIN_EXPECTANCY)


def run_cell(strategy: str, interval: str, htf: str, hold_h: int,
             data: dict[str, pd.DataFrame], split: str,
             overrides: dict | None = None,
             execution: dict | None = None) -> Cell:
    cfg = load_config(Path("config.yaml"))
    for key, value in (execution or {}).items():
        setattr(cfg.execution, key, value)
    if overrides:
        # Only keys the strategy already declares; an unknown one is a typo,
        # and Strategy.__init__ raises on it rather than silently ignoring it.
        cfg.strategies[strategy] = {**cfg.strategies.get(strategy, {}), **overrides}
    cfg.data.interval = interval
    cfg.data.htf_interval = htf
    cfg.risk.max_hold_hours = float(hold_h)
    # Keep the cooldown at roughly an hour of wall clock, as elsewhere. On
    # these timeframes one bar already exceeds it, so one bar is the floor.
    cfg.risk.cooldown_bars = 1

    gross_win = gross_loss = 0.0
    rs: list[float] = []
    wins = 0
    per_symbol = {}
    for sym, df in data.items():
        strat = build(strategy, cfg)
        warm = max(cfg.backtest.warmup_bars, strat.warmup_bars)
        seg = segment(df, split, warm)
        if len(seg) < warm + 100:
            continue
        res = BacktestEngine(cfg, strat, sym).run(seg)
        m = compute(res)
        per_symbol[sym] = {"trades": m.trades, "pf": round(m.profit_factor, 3),
                           "exp_r": round(m.expectancy_r, 4)}
        for t in res.trades:
            rs.append(t.r_multiple)
            if t.net_pnl > 0:
                gross_win += t.net_pnl
                wins += 1
            else:
                gross_loss += abs(t.net_pnl)

    n = len(rs)
    pf = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win else 0.0)
    profitable = sum(1 for v in per_symbol.values() if v["pf"] > 1.0 and v["trades"] > 0)
    return Cell(strategy, interval, hold_h, n,
                round(wins / n * 100, 2) if n else 0.0,
                round(pf, 3),
                round(sum(rs) / n, 4) if n else 0.0,
                profitable, len([v for v in per_symbol.values() if v["trades"] > 0]),
                per_symbol)


def search(split: str, only: str | None = None) -> list[Cell]:
    cells: list[Cell] = []
    names = [only] if only else available()
    for interval, htf, holds in GRIDS:
        data = load(interval)
        if not data:
            print(f"  (keine Daten für {interval})")
            continue
        for name in names:
            for h in holds:
                c = run_cell(name, interval, htf, h, data, split)
                cells.append(c)
                print(f"  {split:8s} {name:22s} {interval:3s} {h:3d}h  "
                      f"n={c.trades:5d}  PF={c.profit_factor:5.2f}  "
                      f"E={c.expectancy_r:+.3f}  Symbole {c.symbols_profitable}/{c.symbols}",
                      flush=True)
    return cells


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", metavar="NAME", help="einen Kandidaten auf test prüfen")
    ap.add_argument("--final", metavar="NAME", help="einen Kandidaten auf holdout. Nur einmal.")
    ap.add_argument("--interval", default="1h")
    ap.add_argument("--hold", type=int, default=24)
    args = ap.parse_args()

    if args.final:
        print(f"HOLDOUT — einmalig, für {args.final} ({args.interval}, {args.hold}h)\n")
        c = run_cell(args.final, args.interval, HTF[args.interval], args.hold,
                 load(args.interval), "holdout")
        print(json.dumps(c.per_symbol, indent=2))
        print(f"\nGesamt: n={c.trades}  PF={c.profit_factor}  E={c.expectancy_r:+.4f}  "
              f"Symbole profitabel {c.symbols_profitable}/{c.symbols}")
        return 0

    if args.confirm:
        print(f"TEST — Bestätigung für {args.confirm} ({args.interval}, {args.hold}h)\n")
        c = run_cell(args.confirm, args.interval, HTF[args.interval], args.hold,
                 load(args.interval), "test")
        print(json.dumps(c.per_symbol, indent=2))
        print(f"\nGesamt: n={c.trades}  PF={c.profit_factor}  E={c.expectancy_r:+.4f}  "
              f"Symbole profitabel {c.symbols_profitable}/{c.symbols}")
        return 0

    print("SUCHE auf train — holdout wird nicht berührt.\n")
    cells = search("train")
    df = pd.DataFrame([{"strategy": c.strategy, "interval": c.interval, "hold_h": c.hold_h,
                        "trades": c.trades, "pf": c.profit_factor, "exp_r": c.expectancy_r,
                        "sym_ok": c.symbols_profitable, "sym": c.symbols,
                        "passes": c.passes()} for c in cells])
    df.to_csv("research/search_train.csv", index=False)

    print(f"\nGerechnete Kombinationen: {len(cells)}")
    print(f"Median Profitfaktor:      {df.pf.median():.3f}")
    print(f"Bester:                   {df.pf.max():.3f}")
    surv = df[df.passes].sort_values("pf", ascending=False)
    print(f"\nHürden genommen: {len(surv)} von {len(cells)}")
    if len(surv):
        print(surv.to_string(index=False))
        top = surv.iloc[0]
        print(f"\n-> Kandidat: {top.strategy} auf {top.interval}, {top.hold_h}h Haltedauer")
        print(f"   Bestätigen mit: python research/search.py --confirm {top.strategy} "
              f"--interval {top.interval} --hold {top.hold_h}")
    else:
        print("Kein Kandidat hat die vorab festgelegten Hürden genommen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
