"""Die Kommandozeile als tatsaechlicher Einstiegspunkt.

Gefahren wird gegen lokale CSV-Kurse, damit kein Netz noetig ist.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from conftest import make_panel, write_config

from techrot.cli import main
from techrot.state import PortfolioState


@pytest.fixture
def projekt(tmp_path: Path) -> Path:
    """Legt Konfiguration und lokale Kursdaten an; gibt den Config-Pfad zurueck."""
    panel = make_panel(end=str(pd.Timestamp.today().normalize().date()))
    tickers = [c for c in panel.close.columns if c != "QQQ"]
    config = write_config(tmp_path, tickers)

    local = tmp_path / "data" / "local"
    local.mkdir(parents=True)
    panel.close.to_csv(local / "close.csv")
    panel.volume.to_csv(local / "volume.csv")
    return config


def lauf(config: Path, *args: str) -> int:
    return main(["--config", str(config), *args])


def zustand(config: Path) -> PortfolioState:
    return PortfolioState.load(config.parent / "data" / "state.json", starting_cash=0.0)


def test_preflight_meldet_startbereit(projekt, capsys):
    code = lauf(projekt, "preflight")
    ausgabe = capsys.readouterr().out

    assert code == 0
    assert "Startbereit" in ausgabe
    assert "NICHT startbereit" not in ausgabe


def test_check_data_listet_alle_ticker(projekt, capsys):
    lauf(projekt, "check-data")
    ausgabe = capsys.readouterr().out
    assert "T00" in ausgabe
    assert "in Ordnung" in ausgabe


def test_rank_zeigt_die_rangliste(projekt, capsys):
    assert lauf(projekt, "rank", "--top", "5") == 0
    ausgabe = capsys.readouterr().out
    assert "Ranking (Top 5)" in ausgabe
    assert "Zielgewichte" in ausgabe


def test_trockenlauf_sendet_nichts(projekt, capsys):
    assert lauf(projekt, "rebalance") == 0
    ausgabe = capsys.readouterr().out

    assert "[Trockenlauf]" in ausgabe
    assert "Sende" not in ausgabe
    # Ohne --execute wird kein Zustand geschrieben.
    assert not (projekt.parent / "data" / "state.json").exists()


def test_ausfuehrung_legt_zustand_und_journal_an(projekt, capsys):
    assert lauf(projekt, "rebalance", "--execute") == 0
    capsys.readouterr()

    state = zustand(projekt)
    assert state.positions
    assert state.last_rebalance is not None
    assert len(state.equity_history) == 1

    journal = projekt.parent / "data" / "orders.jsonl"
    eintraege = [json.loads(z) for z in journal.read_text().splitlines()]
    assert eintraege
    assert all(e["status"] == "filled" for e in eintraege)


def test_zweiter_lauf_schreibt_nur_die_bewertung_fort(projekt, capsys):
    lauf(projekt, "rebalance", "--execute")
    capsys.readouterr()
    vorher = zustand(projekt)

    assert lauf(projekt, "rebalance", "--execute") == 0
    ausgabe = capsys.readouterr().out
    nachher = zustand(projekt)

    assert "nur Depotbewertung fortgeschrieben" in ausgabe
    # Keine neuen Orders, aber die Equity-Kurve laeuft weiter -- die
    # Drawdown-Bremse braucht taegliche Punkte.
    assert nachher.positions == vorher.positions
    assert nachher.cash == pytest.approx(vorher.cash)
    assert len(nachher.equity_history) >= len(vorher.equity_history)


def test_status_zeigt_das_depot(projekt, capsys):
    lauf(projekt, "rebalance", "--execute")
    capsys.readouterr()

    assert lauf(projekt, "status") == 0
    ausgabe = capsys.readouterr().out
    assert "Depotwert" in ausgabe
    assert "Positionen" in ausgabe
    assert "T00" in ausgabe


def test_status_ohne_depot(projekt, capsys):
    assert lauf(projekt, "status") == 0
    assert "Positionen     keine" in capsys.readouterr().out


def test_backtest_schreibt_csv(projekt, tmp_path, capsys):
    ziel = tmp_path / "ergebnis"
    assert lauf(projekt, "backtest", "--out", str(ziel)) == 0
    capsys.readouterr()

    assert (ziel / "equity.csv").exists()
    assert (ziel / "trades.csv").exists()
    assert (ziel / "rebalances.csv").exists()


def test_markdown_report_wird_geschrieben(projekt, tmp_path, capsys):
    ziel = tmp_path / "report.md"
    assert lauf(projekt, "rebalance", "--markdown", str(ziel)) == 0
    capsys.readouterr()

    inhalt = ziel.read_text(encoding="utf-8")
    assert inhalt.startswith("## Tech-Rotation")
    assert "| Ticker |" in inhalt


def test_kaputte_konfiguration_meldet_sich_sauber(tmp_path, capsys):
    kaputt = tmp_path / "config.yaml"
    kaputt.write_text("universe:\n  tickers: []\n", encoding="utf-8")

    assert main(["--config", str(kaputt), "rank"]) == 2
    assert "FEHLER" in capsys.readouterr().err


def test_fehlende_konfiguration_meldet_sich_sauber(tmp_path, capsys):
    assert main(["--config", str(tmp_path / "gibtsnicht.yaml"), "rank"]) == 2
    assert "nicht gefunden" in capsys.readouterr().err
