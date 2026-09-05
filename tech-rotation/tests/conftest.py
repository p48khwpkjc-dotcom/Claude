"""Deterministische Kursfixtures.

Statt Zufallspfaden werden die Kurse analytisch konstruiert: ein exponentieller
Trend mal einer kleinen Sinuswelle. Damit sind Momentum-Reihenfolge und
Volatilitaet exakt vorhersagbar und die Tests haben keine Flake-Quelle.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest
import yaml

from techrot.config import load_config
from techrot.data import PriceData

N_DAYS = 1600
END_DATE = "2026-08-31"
BENCHMARK = "QQQ"


def make_series(
    n: int, *, drift: float, amplitude: float, period: float, start: float = 100.0
) -> list[float]:
    """Exponentieller Trend mit ueberlagerter Welle."""
    return [
        start * math.exp(drift * t) * (1.0 + amplitude * math.sin(2 * math.pi * t / period))
        for t in range(n)
    ]


def make_panel(
    *,
    n_tickers: int = 12,
    n_days: int = N_DAYS,
    end: str = END_DATE,
    benchmark_drift: float = 0.0004,
    illiquid: tuple[str, ...] = ("T09",),
    falling: tuple[str, ...] = ("T10", "T11"),
    uniform_wiggle: bool = False,
) -> PriceData:
    """Baut ein Panel mit klar gestaffeltem Momentum.

    T00 hat den staerksten Trend, T08 den schwaechsten positiven. ``falling``
    bekommt einen negativen Trend, ``illiquid`` ein zu kleines Volumen.

    ``uniform_wiggle`` gibt allen Titeln dieselbe Welle. Dann ist der Trend
    der einzige Unterschied und die Rangfolge exakt vorhersagbar.
    """
    index = pd.bdate_range(end=pd.Timestamp(end), periods=n_days)
    close: dict[str, list[float]] = {}
    volume: dict[str, list[float]] = {}

    for i in range(n_tickers):
        ticker = f"T{i:02d}"
        if ticker in falling:
            drift = -0.0006 - 0.0002 * i
        else:
            # Absteigend gestaffelt: T00 am staerksten.
            drift = 0.0012 - 0.00012 * i
        amplitude = 0.02 if uniform_wiggle else 0.02 + 0.004 * (i % 5)
        period = 45.0 if uniform_wiggle else 45 + 7 * (i % 4)
        close[ticker] = make_series(n_days, drift=drift, amplitude=amplitude, period=period)
        # 5 Mio Stueck taeglich bei ~100 USD sind gut 500 Mio USD Umsatz und
        # liegen klar ueber jedem sinnvollen Liquiditaetslimit.
        daily_volume = 20_000.0 if ticker in illiquid else 5_000_000.0
        volume[ticker] = [daily_volume] * n_days

    close[BENCHMARK] = make_series(n_days, drift=benchmark_drift, amplitude=0.015, period=60)
    volume[BENCHMARK] = [50_000_000.0] * n_days

    return PriceData(
        close=pd.DataFrame(close, index=index),
        volume=pd.DataFrame(volume, index=index),
    )


def write_config(tmp_path: Path, tickers: list[str], **overrides: dict) -> Path:
    """Schreibt eine vollstaendige config.yaml fuer Tests."""
    base: dict = {
        "strategy": {"name": "test", "base_currency": "USD", "benchmark": BENCHMARK},
        "universe": {"tickers": tickers},
        "data": {
            "provider": "local_csv",
            "cache_dir": "data/cache",
            "cache_ttl_hours": 0,
            "history_years": 8,
            "min_history_days": 300,
            "max_staleness_days": 5,
            "max_missing_ratio": 0.02,
        },
        "ranking": {
            "lookbacks": {
                "mom_12_1": {"start": 252, "end": 21},
                "mom_6_1": {"start": 126, "end": 21},
                "mom_3_0": {"start": 63, "end": 0},
            },
            "vol_window": 63,
            "weights": {
                "mom_12_1": 0.40,
                "mom_6_1": 0.30,
                "mom_3_0": 0.15,
                "risk_adj_mom": 0.15,
            },
            "winsorize_z": 3.0,
        },
        "selection": {"top_n": 4, "buffer_rank": 6, "weighting": "inverse_vol"},
        "risk": {
            "eligibility": {
                "min_avg_dollar_volume": 50_000_000,
                "adv_window": 20,
                "max_annual_vol": 0.90,
                "require_positive_absolute_momentum": True,
                "require_above_sma": 200,
            },
            "portfolio": {
                "max_position_weight": 0.35,
                "max_gross_exposure": 1.0,
                "min_names": 2,
                "regime_sma": 200,
                "regime_exposure": 0.0,
                "vol_target": 0.18,
                "vol_lookback": 63,
                "max_vol_scalar": 1.0,
                "max_drawdown_brake": 0.20,
                "drawdown_exposure_floor": 0.30,
                "max_turnover_per_rebalance": 1.0,
            },
        },
        "execution": {
            "broker": "paper",
            "mode": "paper",
            "order_type": "market",
            "min_order_notional": 250,
            "slippage_bps": 5,
            "commission_bps": 1,
            "starting_cash": 100_000,
            "state_file": "data/state.json",
            "journal_file": "data/orders.jsonl",
        },
        "backtest": {"start": "2024-01-01", "end": None, "rebalance": "month_start"},
    }

    for section, values in overrides.items():
        if isinstance(values, dict) and isinstance(base.get(section), dict):
            for key, value in values.items():
                if isinstance(value, dict) and isinstance(base[section].get(key), dict):
                    base[section][key].update(value)
                else:
                    base[section][key] = value
        else:
            base[section] = values

    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def panel() -> PriceData:
    return make_panel()


@pytest.fixture
def tickers(panel: PriceData) -> list[str]:
    return [c for c in panel.close.columns if c != BENCHMARK]


@pytest.fixture
def cfg(tmp_path: Path, tickers: list[str]):
    return load_config(write_config(tmp_path, tickers))
