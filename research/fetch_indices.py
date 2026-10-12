"""Fetch five years of one-minute Nasdaq 100 and S&P 500 from Dukascopy.

    python research/fetch_indices.py              # NQ and ES
    python research/fetch_indices.py --only NQ

Keeps only 09:00-16:30 New York time, which is all the opening range breakout
reads, and writes it to data/exchange/ so the data survives a container that
gets recycled -- this one has been, twice.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from daytrader.data import dukascopy  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

ap = argparse.ArgumentParser()
ap.add_argument("--only", choices=sorted(dukascopy.INSTRUMENTS))
ap.add_argument("--start", default="2021-10-11")
ap.add_argument("--end", default="2026-10-09")
args = ap.parse_args()

out_dir = Path("data/exchange")
out_dir.mkdir(parents=True, exist_ok=True)
for name in ([args.only] if args.only else ["NQ", "ES"]):
    df = dukascopy.fetch(name, date.fromisoformat(args.start), date.fromisoformat(args.end),
                         Path("data/cache/dukascopy"))
    ny = df.tz_convert("America/New_York").between_time("09:00", "16:30").tz_convert("UTC")
    path = out_dir / f"{name}_1m.parquet"
    ny.to_parquet(path)
    print(f"{name}: {len(ny):,} Minuten, {ny.index[0].date()} .. {ny.index[-1].date()} -> {path}",
          flush=True)
