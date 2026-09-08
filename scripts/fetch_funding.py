"""Download perpetual funding-rate history and stage it for the repo.

Meant to run on a machine that can reach the Binance futures host, because the
container this project is developed in cannot. See FUNDING-HOLEN.md.

    python scripts/fetch_funding.py                    # everything, full history
    python scripts/fetch_funding.py --symbols BTCUSDT  # one symbol
    python scripts/fetch_funding.py --verify           # check what was staged
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daytrader.data import funding as fnd

DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "AVAXUSDT", "LINKUSDT", "DOGEUSDT", "DOTUSDT", "LTCUSDT", "ATOMUSDT",
]


def verify(symbols: list[str]) -> int:
    out = fnd.exchange_path("X").parent
    missing = 0
    for sym in symbols:
        path = fnd.exchange_path(sym)
        if not path.exists():
            print(f"  {sym:10s} FEHLT")
            missing += 1
            continue
        import pandas as pd
        df = fnd._normalise(pd.read_csv(path))
        mean = df["funding_rate"].mean()
        neg = (df["funding_rate"] < 0).mean() * 100
        print(f"  {sym:10s} {len(df):6,d} Perioden  "
              f"{df.index[0].date()} .. {df.index[-1].date()}  "
              f"Mittel {mean*100:.4f} %  = {fnd.annualised(mean):5.1f} % p.a.  "
              f"negativ in {neg:.0f} % der Perioden")
    print(f"\nAbgelegt unter {out}/")
    return 1 if missing else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    ap.add_argument("--days", type=int, default=3000)
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    if args.verify:
        return verify(symbols)

    out_dir = fnd.exchange_path("X").parent
    out_dir.mkdir(parents=True, exist_ok=True)
    start = datetime.now(timezone.utc) - timedelta(days=args.days)
    failed = 0
    for sym in symbols:
        try:
            df = fnd.fetch(sym, start)
        except fnd.FundingDataError as exc:
            print(f"  {sym:10s} FEHLER: {exc}")
            failed += 1
            continue
        path = fnd.exchange_path(sym)
        df.reset_index().rename(columns={"time": "time"}).to_csv(path, index=False)
        mean = df["funding_rate"].mean()
        print(f"  {sym:10s} {len(df):6,d} Perioden  "
              f"{df.index[0].date()} .. {df.index[-1].date()}  "
              f"Mittel {mean*100:.4f} %  = {fnd.annualised(mean):5.1f} % p.a.")
    print(f"\nGeschrieben nach {out_dir}/")
    print("Weiter mit:  git add data/exchange/funding && git commit && git push")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
