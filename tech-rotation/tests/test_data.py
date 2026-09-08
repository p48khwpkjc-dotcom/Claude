"""Datenschicht: Normalisierung, Stooq-Fallback und Qualitaetspruefung."""

from __future__ import annotations

from datetime import datetime

import httpx
import numpy as np
import pandas as pd
import pytest

from techrot.data import (
    DataError,
    LocalCsvProvider,
    PriceData,
    StooqProvider,
    check_data_quality,
)

START = datetime(2020, 1, 1)
END = datetime(2030, 1, 1)

CSV = """Date,Open,High,Low,Close,Volume
2026-01-02,10.0,11.0,9.5,10.5,1000
2026-01-05,10.5,12.0,10.0,11.5,1200
2026-01-06,11.5,12.5,11.0,12.0,900
"""

CSV_OHNE_VOLUMEN = """Date,Open,High,Low,Close
2026-01-02,10.0,11.0,9.5,10.5
2026-01-05,10.5,12.0,10.0,11.5
2026-01-06,11.5,12.5,11.0,12.0
"""


def stooq_transport(bodies: dict[str, str | int]) -> httpx.MockTransport:
    """Antwortet je Symbol mit CSV-Text oder einem HTTP-Status."""

    def handler(request: httpx.Request) -> httpx.Response:
        symbol = request.url.params.get("s", "")
        body = bodies.get(symbol)
        if body is None:
            return httpx.Response(404, text="Not found")
        if isinstance(body, int):
            return httpx.Response(body, text="fehler")
        return httpx.Response(200, text=body)

    return httpx.MockTransport(handler)


def test_stooq_liest_kurse_und_volumen():
    provider = StooqProvider(transport=stooq_transport({"aapl.us": CSV, "msft.us": CSV}))
    close, volume = provider.fetch(["AAPL", "MSFT"], START, END)

    assert list(close.columns) == ["AAPL", "MSFT"]
    assert len(close) == 3
    assert close["AAPL"].iloc[-1] == pytest.approx(12.0)
    assert volume["AAPL"].iloc[0] == pytest.approx(1000.0)
    assert close.index.tz is None


def test_stooq_kuerzt_auf_das_zeitfenster():
    provider = StooqProvider(transport=stooq_transport({"aapl.us": CSV}))
    close, _ = provider.fetch(["AAPL"], datetime(2026, 1, 5), datetime(2026, 1, 5))
    assert len(close) == 1
    assert close.index[0] == pd.Timestamp("2026-01-05")


def test_stooq_ohne_volumenspalte_liefert_nan():
    """Fehlendes Volumen darf nicht als 0 durchgehen -- sonst wuerde die
    Liquiditaetspruefung den Titel faelschlich als handelbar sehen."""
    provider = StooqProvider(transport=stooq_transport({"aapl.us": CSV_OHNE_VOLUMEN}))
    _, volume = provider.fetch(["AAPL"], START, END)
    assert volume["AAPL"].isna().all()


def test_stooq_ueberspringt_unbekanntes_symbol():
    # Stooq antwortet auf ein unbekanntes Symbol mit Klartext statt CSV.
    provider = StooqProvider(
        transport=stooq_transport({"aapl.us": CSV, "quatsch.us": "No data"})
    )
    close, _ = provider.fetch(["AAPL", "QUATSCH"], START, END)
    assert close["AAPL"].notna().all()
    assert close["QUATSCH"].isna().all()


def test_stooq_ohne_jedes_ergebnis_meldet_fehler():
    provider = StooqProvider(transport=stooq_transport({"aapl.us": "No data"}))
    with pytest.raises(DataError, match="fuer kein Symbol"):
        provider.fetch(["AAPL"], START, END)


def test_stooq_http_fehler_wird_gemeldet():
    provider = StooqProvider(transport=stooq_transport({"aapl.us": 500}))
    with pytest.raises(DataError, match="Stooq-Abruf fuer AAPL"):
        provider.fetch(["AAPL"], START, END)


def test_local_csv_ohne_datei():
    provider = LocalCsvProvider(directory=__import__("pathlib").Path("/gibt/es/nicht"))
    with pytest.raises(DataError, match="Lokale Kursdatei fehlt"):
        provider.fetch(["AAPL"], START, END)


def test_local_csv_ohne_passenden_ticker(tmp_path):
    (tmp_path / "close.csv").write_text("Date,AAPL\n2026-01-02,10.0\n", encoding="utf-8")
    provider = LocalCsvProvider(directory=tmp_path)
    with pytest.raises(DataError, match="Keiner der Ticker"):
        provider.fetch(["NVDA"], START, END)


def test_pricedata_verlangt_gleiche_indizes():
    index_a = pd.bdate_range(periods=3, end="2026-01-05")
    index_b = pd.bdate_range(periods=4, end="2026-01-05")
    with pytest.raises(DataError, match="unterschiedliche Datumsindizes"):
        PriceData(
            close=pd.DataFrame({"A": [1.0, 2.0, 3.0]}, index=index_a),
            volume=pd.DataFrame({"A": [1.0] * 4}, index=index_b),
        )


def test_dollar_volume_multipliziert_kurs_mal_stueck():
    index = pd.bdate_range(periods=3, end="2026-01-06")
    prices = PriceData(
        close=pd.DataFrame({"A": [10.0, 20.0, 30.0]}, index=index),
        volume=pd.DataFrame({"A": [100.0, 100.0, 100.0]}, index=index),
    )
    # Mittel aus 2000 und 3000 ueber die letzten zwei Tage.
    assert prices.dollar_volume(2)["A"] == pytest.approx(2500.0)


# --------------------------------------------------------------------------
# Qualitaetspruefung
# --------------------------------------------------------------------------


def quality_config(**overrides):
    from techrot.config import DataConfig

    return DataConfig(
        **{
            "min_history_days": 100,
            "max_staleness_days": 5,
            "max_missing_ratio": 0.02,
            **overrides,
        }
    )


def panel_mit(series: dict[str, list[float]], n: int) -> PriceData:
    index = pd.bdate_range(periods=n, end="2026-09-04")
    close = pd.DataFrame(series, index=index)
    return PriceData(close=close, volume=pd.DataFrame(1e9, index=index, columns=close.columns))


def test_zu_kurze_historie_faellt_auf():
    prices = panel_mit({"A": [100.0] * 50}, 50)
    result = check_data_quality(prices, ["A"], quality_config(), prices.last_date)
    assert not result["A"].ok
    assert "Historie" in result["A"].reason


def test_veralteter_kurs_faellt_auf():
    prices = panel_mit({"A": [100.0] * 150}, 150)
    spaeter = prices.last_date + pd.Timedelta(days=30)
    result = check_data_quality(prices, ["A"], quality_config(), spaeter)
    assert not result["A"].ok
    assert "Tage alt" in result["A"].reason


def test_luecken_fallen_auf():
    werte = [100.0] * 150
    for i in range(60, 80):
        werte[i] = np.nan
    prices = panel_mit({"A": werte}, 150)
    result = check_data_quality(prices, ["A"], quality_config(), prices.last_date)
    assert not result["A"].ok
    assert "Luecken" in result["A"].reason


def test_spaeterer_boersengang_gilt_nicht_als_luecke():
    """Fuehrende NaN sind ein spaeter Handelsstart, kein Datenfehler."""
    werte = [np.nan] * 30 + [100.0] * 150
    prices = panel_mit({"A": werte}, 180)
    result = check_data_quality(prices, ["A"], quality_config(), prices.last_date)
    assert result["A"].ok, result["A"].reason
    assert result["A"].missing_ratio == pytest.approx(0.0)


def test_fehlende_reihe_wird_gemeldet():
    prices = panel_mit({"A": [100.0] * 150}, 150)
    result = check_data_quality(prices, ["A", "FEHLT"], quality_config(), prices.last_date)
    assert result["A"].ok
    assert not result["FEHLT"].ok
    assert "keine Kursreihe" in result["FEHLT"].reason
