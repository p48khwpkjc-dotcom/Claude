"""Die gebaute Seite muss zur Vorlage und zu den Daten passen.

`web/querschnitt.html` ist erzeugt und wird trotzdem versioniert, damit die
Ansicht ohne Buildschritt zu oeffnen ist. Damit kann sie von der Vorlage
abdriften: wer die Vorlage aendert und den Build vergisst, veroeffentlicht
weiter die alte Seite. Dieser Test faengt genau das.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "scripts"))

import build_view  # noqa: E402

VORLAGE = WURZEL / "web" / "querschnitt.template.html"
GEBAUT = WURZEL / "web" / "querschnitt.html"
DATEN = WURZEL / "data" / "ranking.json"


def test_vorlage_traegt_die_platzhaltermarke():
    assert build_view.MARKE in VORLAGE.read_text(encoding="utf-8")


@pytest.mark.skipif(not DATEN.exists(), reason="noch kein Lauf exportiert")
def test_gebaute_seite_ist_aktuell(tmp_path):
    """Neu bauen muss byteweise dasselbe ergeben wie die versionierte Datei."""
    ziel = tmp_path / "neu.html"
    code = build_view.main(
        ["--daten", str(DATEN), "--vorlage", str(VORLAGE), "--ziel", str(ziel)]
    )
    assert code == 0
    assert ziel.read_text(encoding="utf-8") == GEBAUT.read_text(encoding="utf-8"), (
        "web/querschnitt.html ist nicht aus der aktuellen Vorlage und den "
        "aktuellen Daten gebaut. Bitte `python scripts/build_view.py` laufen "
        "lassen und das Ergebnis mitcommitten."
    )


def test_build_meldet_fehlende_daten(tmp_path, capsys):
    code = build_view.main(
        [
            "--daten", str(tmp_path / "gibtsnicht.json"),
            "--vorlage", str(VORLAGE),
            "--ziel", str(tmp_path / "out.html"),
        ]
    )
    assert code == 2
    assert "fehlt" in capsys.readouterr().err


def test_json_landet_parsebar_in_der_seite(tmp_path):
    """Die Daten stecken im Dokument -- sie muessen dort gueltig ankommen."""
    daten = {
        "schema_version": 1,
        "signal_date": "2026-01-01",
        "tickers": [{"ticker": "A</script>B", "eligible": True}],
    }
    quelle = tmp_path / "daten.json"
    quelle.write_text(json.dumps(daten), encoding="utf-8")
    ziel = tmp_path / "out.html"

    assert build_view.main(
        ["--daten", str(quelle), "--vorlage", str(VORLAGE), "--ziel", str(ziel)]
    ) == 0

    seite = ziel.read_text(encoding="utf-8")
    # Ein Ticker mit "</script>" darf den Datenblock nicht vorzeitig beenden.
    assert "A</script>B" not in seite
    assert "A<\\/script>B" in seite
