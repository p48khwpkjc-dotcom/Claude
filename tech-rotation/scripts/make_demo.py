"""Erzeugt ein Demo-Setup ohne Netzzugang.

Schreibt synthetische Kurse nach ``demo/data/local`` und eine passende
config.yaml. Damit laesst sich die komplette Kette -- rank, backtest,
rebalance, status -- durchspielen, bevor echte Marktdaten im Spiel sind.

    python scripts/make_demo.py
    techrot --config demo/config.yaml check-data
    techrot --config demo/config.yaml backtest
    techrot --config demo/config.yaml rebalance --execute
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"

N_DAYS = 1700
N_TICKERS = 16
BENCHMARK = "QQQ"


def series(n: int, *, drift: float, amplitude: float, period: float) -> list[float]:
    return [
        100.0 * math.exp(drift * t) * (1.0 + amplitude * math.sin(2 * math.pi * t / period))
        for t in range(n)
    ]


def main() -> int:
    index = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=N_DAYS)
    close: dict[str, list[float]] = {}
    volume: dict[str, list[float]] = {}

    for i in range(N_TICKERS):
        ticker = f"DEMO{i:02d}"
        # Die letzten drei Titel fallen, damit die Filter etwas zu tun haben.
        drift = -0.0005 if i >= N_TICKERS - 3 else 0.0011 - 0.00009 * i
        close[ticker] = series(
            N_DAYS, drift=drift, amplitude=0.03 + 0.006 * (i % 4), period=40 + 9 * (i % 5)
        )
        volume[ticker] = [4_000_000.0] * N_DAYS

    close[BENCHMARK] = series(N_DAYS, drift=0.0004, amplitude=0.02, period=70)
    volume[BENCHMARK] = [60_000_000.0] * N_DAYS

    local = DEMO / "data" / "local"
    local.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(close, index=index).to_csv(local / "close.csv")
    pd.DataFrame(volume, index=index).to_csv(local / "volume.csv")

    base = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    base["universe"]["tickers"] = [t for t in close if t != BENCHMARK]
    base["data"]["provider"] = "local_csv"
    base["data"]["cache_ttl_hours"] = 0
    base["backtest"]["start"] = str(index[400].date())
    (DEMO / "config.yaml").write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")

    print(f"Demo-Daten:  {local}")
    print(f"Demo-Config: {DEMO / 'config.yaml'}")
    print(f"{len(index)} Handelstage, {len(close)} Reihen, bis {index[-1].date()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
