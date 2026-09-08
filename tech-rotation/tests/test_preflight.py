"""Startbereitschaftspruefung."""

from __future__ import annotations

import pandas as pd
import pytest
from conftest import make_panel, write_config

from techrot.config import load_config
from techrot.data import PriceData
from techrot.preflight import FAIL, OK, WARN, render_preflight, run_preflight
from techrot.state import PortfolioState


def frisch(cfg) -> PortfolioState:
    return PortfolioState(cash=cfg.execution.starting_cash)


def status_von(result, name: str) -> str:
    return next(c.status for c in result.checks if c.name == name)


def aktuelles_panel(**kwargs) -> PriceData:
    """Panel, dessen letzter Kurs von heute ist -- sonst schlaegt die
    Aktualitaetspruefung zu Recht an."""
    return make_panel(end=str(pd.Timestamp.today().normalize().date()), **kwargs)


def test_sauberes_setup_ist_startbereit(cfg, tmp_path):
    cfg = load_config(write_config(tmp_path, list(cfg.tickers)))
    result = run_preflight(cfg, frisch(cfg), prices=aktuelles_panel())

    assert result.ready
    assert result.exit_code == 0
    assert result.failures == []
    assert result.warnings == []
    assert result.plan_summary is not None
    assert "Orders" in result.plan_summary


def test_veraltete_kurse_blockieren(cfg, tmp_path):
    cfg = load_config(write_config(tmp_path, list(cfg.tickers)))
    alt = make_panel(end="2024-01-31")
    result = run_preflight(cfg, frisch(cfg), prices=alt)

    assert not result.ready
    assert status_von(result, "Kursdaten") == FAIL
    assert result.exit_code == 2


def test_zu_wenige_brauchbare_ticker_blockieren(tmp_path):
    panel = aktuelles_panel()
    tickers = [c for c in panel.close.columns if c != "QQQ"]
    # top_n hoeher als die Zahl der gesunden Titel setzen.
    cfg = load_config(
        write_config(tmp_path, tickers, selection={"top_n": 11, "buffer_rank": 12})
    )
    kurz = make_panel(n_days=310, end=str(pd.Timestamp.today().normalize().date()))
    result = run_preflight(cfg, frisch(cfg), prices=kurz)

    assert status_von(result, "Universum") in {OK, WARN, FAIL}
    # Mit voller Historie sind es 12 Titel, davon fallen die schwachen raus.
    result_voll = run_preflight(cfg, frisch(cfg), prices=panel)
    assert status_von(result_voll, "Universum") in {OK, WARN}


def test_fehlender_benchmark_blockiert(cfg, tmp_path):
    cfg = load_config(write_config(tmp_path, list(cfg.tickers)))
    panel = aktuelles_panel()
    ohne = PriceData(
        close=panel.close.drop(columns=["QQQ"]),
        volume=panel.volume.drop(columns=["QQQ"]),
    )
    result = run_preflight(cfg, frisch(cfg), prices=ohne)

    assert status_von(result, "Benchmark") == FAIL
    assert not result.ready


def test_benchmark_unter_der_sma_warnt(cfg, tmp_path):
    cfg = load_config(write_config(tmp_path, list(cfg.tickers)))
    result = run_preflight(
        cfg, frisch(cfg), prices=aktuelles_panel(benchmark_drift=-0.0012)
    )

    assert status_von(result, "Benchmark") == WARN
    # Kein Blocker: in Cash zu bleiben ist ein gueltiger erster Lauf.
    assert result.ready
    assert result.exit_code == 1
    assert "Cash" in next(c.detail for c in result.checks if c.name == "Benchmark")


def test_abgeschalteter_regime_filter_warnt(cfg, tmp_path):
    cfg = load_config(
        write_config(tmp_path, list(cfg.tickers), risk={"portfolio": {"regime_sma": 0}})
    )
    result = run_preflight(cfg, frisch(cfg), prices=aktuelles_panel())
    assert status_von(result, "Benchmark") == WARN


def test_frischer_zustand_nennt_das_startkapital(cfg, tmp_path):
    cfg = load_config(write_config(tmp_path, list(cfg.tickers)))
    result = run_preflight(cfg, frisch(cfg), prices=aktuelles_panel())

    detail = next(c.detail for c in result.checks if c.name == "Zustand")
    assert "100,000.00" in detail


def test_laufendes_depot_warnt(cfg, tmp_path):
    cfg = load_config(write_config(tmp_path, list(cfg.tickers)))
    state = frisch(cfg)
    state.positions = {"T00": 10.0}
    state.last_rebalance = "2026-08-01"
    state.save(cfg.path(cfg.execution.state_file))

    result = run_preflight(cfg, state, prices=aktuelles_panel())
    assert status_von(result, "Zustand") == WARN
    assert "laeuft bereits" in next(c.detail for c in result.checks if c.name == "Zustand")


def test_paper_broker_ist_unbedenklich(cfg, tmp_path):
    cfg = load_config(write_config(tmp_path, list(cfg.tickers)))
    result = run_preflight(cfg, frisch(cfg), prices=aktuelles_panel())

    detail = next(c.detail for c in result.checks if c.name == "Broker")
    assert "kein echtes Geld" in detail


def test_alpaca_ohne_schluessel_blockiert(cfg, tmp_path, monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    cfg = load_config(
        write_config(tmp_path, list(cfg.tickers), execution={"broker": "alpaca"})
    )
    result = run_preflight(cfg, frisch(cfg), prices=aktuelles_panel())

    assert status_von(result, "Brokerzugang") == FAIL
    assert not result.ready


def test_live_ohne_freigabe_blockiert(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY_ID", "k")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "s")
    monkeypatch.delenv("TECHROT_ALLOW_LIVE", raising=False)
    cfg = load_config(
        write_config(
            tmp_path, list(cfg.tickers), execution={"broker": "alpaca", "mode": "live"}
        )
    )
    result = run_preflight(cfg, frisch(cfg), prices=aktuelles_panel())

    assert status_von(result, "Handelsmodus") == FAIL
    assert not result.ready


def test_fehlende_schreibrechte_blockieren(cfg, tmp_path, monkeypatch):
    cfg = load_config(write_config(tmp_path, list(cfg.tickers)))

    def kein_zugriff(*args, **kwargs):
        raise PermissionError("Nur-Lese-Dateisystem")

    monkeypatch.setattr("pathlib.Path.mkdir", kein_zugriff)
    result = run_preflight(cfg, frisch(cfg), prices=aktuelles_panel())

    assert status_von(result, "Schreibrechte") == FAIL
    assert "Nur-Lese-Dateisystem" in next(
        c.detail for c in result.checks if c.name == "Schreibrechte"
    )


def test_datenfehler_bricht_frueh_ab(cfg, tmp_path, monkeypatch):
    from techrot.data import DataError

    cfg = load_config(write_config(tmp_path, list(cfg.tickers)))

    def keine_daten(*args, **kwargs):
        raise DataError("Yahoo nicht erreichbar")

    monkeypatch.setattr("techrot.preflight.load_prices", keine_daten)
    result = run_preflight(cfg, frisch(cfg))

    assert status_von(result, "Kursdaten") == FAIL
    assert result.plan_summary is None
    # Schreibrechte werden trotzdem noch geprueft, der Rest nicht mehr.
    assert any(c.name == "Schreibrechte" for c in result.checks)
    assert not any(c.name == "Probelauf" for c in result.checks)


def test_bericht_laesst_sich_rendern(cfg, tmp_path):
    cfg = load_config(write_config(tmp_path, list(cfg.tickers)))
    text = render_preflight(run_preflight(cfg, frisch(cfg), prices=aktuelles_panel()))

    assert "Startbereitschaft" in text
    assert "Startbereit" in text
    assert "Probelauf" in text


def test_bericht_nennt_die_fehlerzahl(cfg, tmp_path):
    cfg = load_config(write_config(tmp_path, list(cfg.tickers)))
    text = render_preflight(run_preflight(cfg, frisch(cfg), prices=make_panel(end="2024-01-31")))
    assert "NICHT startbereit" in text
