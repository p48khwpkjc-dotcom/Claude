"""Run the New York opening range breakout as registered in ORB_ANMELDUNG.md.

    python research/orb_study.py --symbol BTCUSDT                 # from the 1m cache
    python research/orb_study.py --csv data/exchange/NQ_1m.csv --name NQ --costs futures
    python research/orb_study.py --csv ... --tz America/New_York  # if the export is local time

Every variant is reported, next to the same variant without costs and the same
variant with a coin-flip direction, and split into the first and second half
of the history. Nothing is selected.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daytrader.backtest.orb import OrbConfig, run, summarise  # noqa: E402
from daytrader.data.loader import cache_path, read_cache  # noqa: E402

COSTS = {
    # Binance taker, as everywhere else in this project.
    "crypto": dict(fee_pct=0.05, slippage_bps=3.0, stop_slippage_bps=5.0),
    # About $4-5 commission per round turn and a tick of slippage on NQ/ES.
    "futures": dict(fee_pct=0.0015, slippage_bps=0.5, stop_slippage_bps=1.0),
}
FREE = dict(fee_pct=0.0, slippage_bps=0.0, stop_slippage_bps=0.0)

VARIANTS = [
    ("halten, kein Stop", dict(stop="none", target_r=None)),
    ("halten mit Stop", dict(stop="range", target_r=None)),
    ("1:1", dict(stop="range", target_r=1.0)),
    ("1,5:1", dict(stop="range", target_r=1.5)),
    ("2:1", dict(stop="range", target_r=2.0)),
    ("3:1", dict(stop="range", target_r=3.0)),
    ("4:1", dict(stop="range", target_r=4.0)),
    ("5:1", dict(stop="range", target_r=5.0)),
]


def load_csv(path: Path, tz: str) -> pd.DataFrame:
    """Any one-minute export with a time column and OHLC, normalised to UTC.

    A .parquet file from research/fetch_databento.py or fetch_indices.py is
    already UTC-indexed and is read as it is.
    """
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
        df.index = pd.DatetimeIndex(df.index).tz_convert("UTC")
        return df[["open", "high", "low", "close"]].astype(float).sort_index()
    raw = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in raw.columns}
    tcol = next((cols[k] for k in ("time", "timestamp", "datetime", "date") if k in cols), None)
    if tcol is None:
        raise SystemExit(f"{path}: keine Zeitspalte (time/timestamp/datetime/date)")
    t = raw[tcol]
    if pd.api.types.is_numeric_dtype(t):
        unit = "ms" if t.iloc[0] > 1e11 else "s"
        idx = pd.to_datetime(t, unit=unit, utc=True)
    else:
        idx = pd.to_datetime(t)
        idx = idx.dt.tz_localize(tz) if idx.dt.tz is None else idx
        idx = idx.dt.tz_convert("UTC")
    df = pd.DataFrame({k: raw[cols[k]].astype(float) for k in ("open", "high", "low", "close")})
    df.index = pd.DatetimeIndex(idx)
    return df[~df.index.duplicated()].sort_index()


def halves(trades: pd.DataFrame):
    if trades.empty:
        return trades, trades
    mid = trades["day"].min() + (trades["day"].max() - trades["day"].min()) / 2
    return trades[trades["day"] < mid], trades[trades["day"] >= mid]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol")
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--name")
    ap.add_argument("--costs", choices=sorted(COSTS), default="crypto")
    ap.add_argument("--tz", default="UTC", help="timezone of a naive CSV time column")
    args = ap.parse_args()

    if args.csv:
        df = load_csv(args.csv, args.tz)
        name = args.name or args.csv.stem
    else:
        df = read_cache(cache_path(Path("data/cache"), args.symbol, "1m"))
        if df is None:
            raise SystemExit(f"kein 1m-Cache für {args.symbol}")
        name = args.name or args.symbol
    costs = COSTS[args.costs]

    print(f"{name}: {len(df):,} Minuten, {df.index[0].date()} .. {df.index[-1].date()}, "
          f"Kosten '{args.costs}'\n")
    rows, per_year = [], []
    for label, v in VARIANTS:
        real = run(df, OrbConfig(**v, **costs))
        free = run(df, OrbConfig(**v, **FREE))
        coin = run(df, OrbConfig(**v, **costs, direction="coin"))
        first, second = halves(real)
        s, s0, sc = summarise(real), summarise(free), summarise(coin)
        s1, s2 = summarise(first), summarise(second)
        rows.append({"variante": label, **s,
                     "exp_r_ohne_kosten": s0.get("exp_r"),
                     "exp_r_muenzwurf": sc.get("exp_r"),
                     "exp_r_1_haelfte": s1.get("exp_r"),
                     "exp_r_2_haelfte": s2.get("exp_r")})
        if not real.empty:
            y = real.groupby(real["day"].dt.year)["r"].agg(["count", "mean", "sum"])
            for year, r in y.iterrows():
                per_year.append({"variante": label, "jahr": year, "trades": int(r["count"]),
                                 "exp_r": round(r["mean"], 4), "summe_r": round(r["sum"], 1)})
        print(f"  {label:18s} n={s.get('trades', 0):5d}  Treffer {s.get('win_rate', 0):5.1f}%  "
              f"E={s.get('exp_r', 0):+.4f}R  [{s.get('ci_low', 0):+.3f}, {s.get('ci_high', 0):+.3f}]  "
              f"PF={s.get('pf', 0)}  ohne Kosten {s0.get('exp_r', 0):+.4f}  "
              f"Münzwurf {sc.get('exp_r', 0):+.4f}", flush=True)

    out = pd.DataFrame(rows)
    years = pd.DataFrame(per_year)
    out.to_csv(f"research/orb_{name}.csv", index=False)
    years.to_csv(f"research/orb_{name}_jahre.csv", index=False)

    pd.set_option("display.width", 250)
    print("\n=== Übersicht ===")
    print(out[["variante", "trades", "win_rate", "exp_r", "ci_low", "ci_high", "t", "pf",
               "total_r", "max_dd_r", "cost_r", "exp_r_ohne_kosten", "exp_r_muenzwurf",
               "exp_r_1_haelfte", "exp_r_2_haelfte"]].to_string(index=False))
    print(f"\nMedian-Range der ersten 5 Minuten: {out['range_pct'].iloc[0]} % des Kurses")
    if not years.empty:
        print("\n=== Erwartungswert je Jahr (R) ===")
        print(years.pivot(index="variante", columns="jahr", values="exp_r")
              .reindex([v for v, _ in VARIANTS]).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
