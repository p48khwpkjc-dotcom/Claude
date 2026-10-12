"""One-minute NQ and ES futures from Databento, priced before anything is bought.

    python research/fetch_databento.py            # print what it would cost, download nothing
    python research/fetch_databento.py --confirm  # download, after the cost has been seen

The key is read from DATABENTO_API_KEY, which the environment provides at
session start. It is never printed and never written anywhere.

Databento charges per byte, so the default run only asks for the price. The
download needs --confirm on purpose: spending someone's credit is their call,
and it should be made with the number in front of them.

Symbols are the continuous front month rolled by volume (`NQ.v.0`, `ES.v.0`),
which is the contract that actually trades at the open on any given day. Only
09:00 to 16:30 New York is kept, which is all the opening range breakout
reads, and it goes to data/exchange/ so it survives a recycled container.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

DATASET = "GLBX.MDP3"
SYMBOLS = {"NQ": "NQ.v.0", "ES": "ES.v.0"}
SCHEMA = "ohlcv-1m"


def client():
    key = os.environ.get("DATABENTO_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "DATABENTO_API_KEY ist in dieser Session nicht gesetzt. Secrets und\n"
            "Umgebungsvariablen werden beim Start einer Session geladen: in den\n"
            "Umgebungseinstellungen eintragen, dann eine neue Session starten.")
    import databento as db
    return db.Historical(key)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2021-10-11")
    ap.add_argument("--end", default="2026-10-10")
    ap.add_argument("--only", choices=sorted(SYMBOLS))
    ap.add_argument("--confirm", action="store_true",
                    help="really download; without it only the cost is shown")
    args = ap.parse_args()
    names = [args.only] if args.only else list(SYMBOLS)
    hist = client()

    total = 0.0
    for name in names:
        query = dict(dataset=DATASET, symbols=[SYMBOLS[name]], stype_in="continuous",
                     schema=SCHEMA, start=args.start, end=args.end)
        cost = float(hist.metadata.get_cost(**query))
        size = hist.metadata.get_billable_size(**query)
        total += cost
        print(f"  {name} ({SYMBOLS[name]}): {size / 1e6:8.1f} MB  ->  {cost:8.2f} USD")
    print(f"  zusammen: {total:.2f} USD  ({args.start} .. {args.end}, {SCHEMA})")

    if not args.confirm:
        print("\nNichts geladen. Mit --confirm wird heruntergeladen und abgerechnet.")
        return 0

    out_dir = Path("data/exchange")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        data = hist.timeseries.get_range(dataset=DATASET, symbols=[SYMBOLS[name]],
                                         stype_in="continuous", schema=SCHEMA,
                                         start=args.start, end=args.end)
        df = data.to_df()                       # prices as floats, UTC index
        df = df[["open", "high", "low", "close", "volume"]].astype(float)
        df.index = pd.DatetimeIndex(df.index).tz_convert("UTC")
        ny = df.tz_convert("America/New_York").between_time("09:00", "16:30").tz_convert("UTC")
        path = out_dir / f"{name}_1m.parquet"
        ny.to_parquet(path)
        print(f"  {name}: {len(ny):,} Minuten, {ny.index[0].date()} .. {ny.index[-1].date()} -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
