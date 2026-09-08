"""Zustandsverwaltung und Konfigurationsvalidierung."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml
from conftest import write_config

from techrot.config import ConfigError, load_config
from techrot.state import PortfolioState, is_rebalance_due


def test_zustand_ueberlebt_speichern_und_laden(tmp_path: Path):
    state = PortfolioState(cash=1234.5, positions={"AAPL": 10.0})
    state.record_equity(date(2026, 1, 5), 5000.0)
    state.last_rebalance = "2026-01-05"

    path = tmp_path / "state.json"
    state.save(path)
    loaded = PortfolioState.load(path, starting_cash=0.0)

    assert loaded.cash == pytest.approx(1234.5)
    assert loaded.positions == {"AAPL": 10.0}
    assert loaded.last_rebalance == "2026-01-05"
    assert len(loaded.equity_history) == 1


def test_fehlende_datei_startet_frisch(tmp_path: Path):
    state = PortfolioState.load(tmp_path / "gibtsnicht.json", starting_cash=50_000)
    assert state.cash == 50_000
    assert state.positions == {}
    assert state.last_rebalance is None


def test_zu_neue_zustandsversion_wird_abgelehnt(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text('{"version": 99, "cash": 1}', encoding="utf-8")
    with pytest.raises(ValueError, match="Version 99"):
        PortfolioState.load(path, starting_cash=0.0)


def test_equity_punkt_desselben_tages_wird_ersetzt():
    state = PortfolioState(cash=0.0)
    state.record_equity(date(2026, 1, 5), 100.0)
    state.record_equity(date(2026, 1, 5), 200.0)
    assert len(state.equity_history) == 1
    assert state.equity_history[0].equity == 200.0


def test_fill_bucht_cash_und_position():
    state = PortfolioState(cash=10_000.0)
    state.apply_fill("AAPL", 10.0, 100.0, cost=5.0)
    assert state.positions["AAPL"] == 10.0
    assert state.cash == pytest.approx(10_000 - 1000 - 5)

    state.apply_fill("AAPL", -10.0, 110.0, cost=5.0)
    assert "AAPL" not in state.positions
    assert state.cash == pytest.approx(10_000 - 1000 - 5 + 1100 - 5)


def test_bewertung_ignoriert_fehlende_kurse():
    state = PortfolioState(cash=100.0, positions={"A": 2.0, "B": 3.0})
    prices = pd.Series({"A": 50.0, "B": float("nan")})
    assert state.equity(prices) == pytest.approx(200.0)


def test_rebalancing_faellig_erst_im_folgemonat():
    state = PortfolioState(cash=0.0)
    assert is_rebalance_due(state, date(2026, 1, 5)) is True

    state.last_rebalance = "2026-01-05"
    assert is_rebalance_due(state, date(2026, 1, 6)) is False
    assert is_rebalance_due(state, date(2026, 1, 31)) is False
    assert is_rebalance_due(state, date(2026, 2, 1)) is True
    # Ein ausgefallener Monat schiebt den Termin, er faellt nicht aus.
    assert is_rebalance_due(state, date(2026, 4, 1)) is True


# --------------------------------------------------------------------------
# Konfiguration
# --------------------------------------------------------------------------


def test_gueltige_konfiguration_laedt(tmp_path: Path):
    cfg = load_config(write_config(tmp_path, ["A", "B", "C", "D", "E"]))
    assert cfg.selection.top_n == 4
    assert cfg.ranking.normalized_weights()["mom_12_1"] == pytest.approx(0.40)


def test_unbekannter_schluessel_faellt_auf(tmp_path: Path):
    path = write_config(tmp_path, ["A", "B", "C", "D"])
    raw = yaml.safe_load(path.read_text())
    raw["selection"]["tippfehler"] = 1
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ConfigError, match="Unbekannte Schluessel"):
        load_config(path)


def test_top_n_groesser_als_universum(tmp_path: Path):
    with pytest.raises(ConfigError, match="groesser als das Universum"):
        load_config(write_config(tmp_path, ["A", "B"], selection={"top_n": 4}))


def test_zu_kurze_historie_fuer_den_lookback(tmp_path: Path):
    with pytest.raises(ConfigError, match="min_history_days"):
        load_config(
            write_config(tmp_path, ["A", "B", "C", "D"], data={"min_history_days": 100})
        )


def test_positionslimit_muss_die_exposure_tragen(tmp_path: Path):
    with pytest.raises(ConfigError, match="max_gross_exposure"):
        load_config(
            write_config(
                tmp_path,
                ["A", "B", "C", "D", "E"],
                risk={"portfolio": {"max_position_weight": 0.10}},
            )
        )


def test_puffer_darf_nicht_kleiner_als_top_n_sein(tmp_path: Path):
    with pytest.raises(ConfigError, match="buffer_rank"):
        load_config(
            write_config(
                tmp_path, ["A", "B", "C", "D", "E"], selection={"top_n": 4, "buffer_rank": 2}
            )
        )


def test_paper_broker_kann_nicht_live(tmp_path: Path):
    with pytest.raises(ConfigError, match="Paper-Broker"):
        load_config(
            write_config(tmp_path, ["A", "B", "C", "D", "E"], execution={"mode": "live"})
        )


def test_gewicht_auf_unbekanntes_signal(tmp_path: Path):
    with pytest.raises(ConfigError, match="unbekannte Signale"):
        load_config(
            write_config(
                tmp_path,
                ["A", "B", "C", "D", "E"],
                ranking={"weights": {"mom_12_1": 1.0, "mom_99": 0.5}},
            )
        )


def test_leeres_universum(tmp_path: Path):
    with pytest.raises(ConfigError, match="universe.tickers ist leer"):
        load_config(write_config(tmp_path, []))
