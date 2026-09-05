"""Backtest: Terminplan, Lookahead-Schutz und Kennzahlen."""

from __future__ import annotations

import pandas as pd
import pytest
from conftest import make_panel, write_config

from techrot.backtest import performance_metrics, rebalance_dates, run_backtest
from techrot.config import load_config
from techrot.data import PriceData


def test_rebalance_termine_treffen_monatsgrenzen():
    index = pd.bdate_range("2026-01-01", "2026-03-31")
    starts = rebalance_dates(index, "month_start")
    ends = rebalance_dates(index, "month_end")

    assert [d.strftime("%Y-%m-%d") for d in starts] == ["2026-01-01", "2026-02-02", "2026-03-02"]
    assert [d.strftime("%Y-%m-%d") for d in ends] == ["2026-01-30", "2026-02-27", "2026-03-31"]


def test_performance_metrics_auf_bekannter_kurve():
    # Exakte Verdoppelung ueber genau ein Kalenderjahr: dann muessen
    # Gesamtrendite und CAGR beide bei 100 % liegen.
    index = pd.date_range("2025-01-01", "2026-01-01", freq="D")
    equity = pd.Series(
        [100.0 * (2 ** (i / (len(index) - 1))) for i in range(len(index))],
        index=index,
        dtype="float64",
    )
    m = performance_metrics(equity)

    assert m["total_return"] == pytest.approx(1.0, rel=1e-6)
    assert m["cagr"] == pytest.approx(1.0, rel=0.02)
    assert m["max_drawdown"] == pytest.approx(0.0)
    assert m["positive_days"] == pytest.approx(1.0)


def test_performance_metrics_findet_den_drawdown():
    index = pd.bdate_range("2026-01-01", periods=4)
    equity = pd.Series([100.0, 150.0, 75.0, 120.0], index=index)
    assert performance_metrics(equity)["max_drawdown"] == pytest.approx(-0.5)


def test_zu_kurze_kurve_liefert_nichts():
    assert performance_metrics(pd.Series(dtype="float64")) == {}


def test_backtest_laeuft_durch(panel: PriceData, tmp_path):
    cfg = load_config(
        write_config(
            tmp_path,
            [c for c in panel.close.columns if c != "QQQ"],
            backtest={"start": "2023-01-01"},
        )
    )
    result = run_backtest(cfg, panel)

    assert len(result.equity) > 0
    assert result.equity.iloc[0] == pytest.approx(cfg.execution.starting_cash)
    assert not result.trades.empty
    assert not result.rebalances.empty

    for key in ("cagr", "volatility", "max_drawdown", "sharpe", "n_rebalances"):
        assert key in result.metrics

    # Jedes geplante Rebalancing wurde am Folgetag auch gehandelt.
    assert result.rebalances["trade_date"].notna().all()
    assert result.benchmark is not None
    assert result.benchmark_metrics is not None


def test_backtest_handelt_erst_nach_dem_signaltag(panel: PriceData, tmp_path):
    """Der Handelstag muss echt nach dem Signaltag liegen."""
    cfg = load_config(
        write_config(
            tmp_path,
            [c for c in panel.close.columns if c != "QQQ"],
            backtest={"start": "2023-01-01"},
        )
    )
    result = run_backtest(cfg, panel)
    paare = result.rebalances[["signal_date", "trade_date"]].dropna()
    assert (paare["trade_date"] > paare["signal_date"]).all()


def test_backtest_haelt_das_positionslimit(panel: PriceData, tmp_path):
    cfg = load_config(
        write_config(
            tmp_path,
            [c for c in panel.close.columns if c != "QQQ"],
            backtest={"start": "2023-01-01"},
        )
    )
    result = run_backtest(cfg, panel)
    assert (result.rebalances["n_selected"] <= cfg.selection.top_n).all()
    assert (result.rebalances["exposure"] <= cfg.risk.portfolio.max_gross_exposure + 1e-9).all()


def test_baerenmarkt_haelt_die_strategie_in_cash(tmp_path):
    """Faellt der Benchmark, greift der Regime-Filter und es wird nicht gehandelt."""
    baisse = make_panel(benchmark_drift=-0.0012)
    cfg = load_config(
        write_config(
            tmp_path,
            [c for c in baisse.close.columns if c != "QQQ"],
            backtest={"start": "2023-01-01"},
        )
    )
    result = run_backtest(cfg, baisse)

    assert (result.rebalances["exposure"] == 0.0).all()
    assert result.trades.empty
    # Ohne Positionen bleibt die Equity exakt beim Startkapital.
    assert result.equity.nunique() == 1
    assert result.equity.iloc[-1] == pytest.approx(cfg.execution.starting_cash)


def test_zu_wenig_historie_wird_gemeldet(tmp_path):
    kurz = make_panel(n_days=320)
    cfg = load_config(
        write_config(
            tmp_path,
            [c for c in kurz.close.columns if c != "QQQ"],
            backtest={"start": "2019-01-01"},
        )
    )
    with pytest.raises(ValueError, match="Zu wenig Historie"):
        run_backtest(cfg, kurz)


def test_zeitraum_ohne_termin_wird_gemeldet(panel: PriceData, tmp_path):
    cfg = load_config(
        write_config(
            tmp_path,
            [c for c in panel.close.columns if c != "QQQ"],
            backtest={"start": "2030-01-01", "end": "2030-06-01"},
        )
    )
    with pytest.raises(ValueError, match="Kein Rebalancing-Termin"):
        run_backtest(cfg, panel)
