"""Der yfinance-Pfad, gegen eine nachgebaute Antwort.

Das ist der Code, der beim ersten echten Lauf als erstes anspringt. Er laesst
sich hier nicht gegen Yahoo testen, wohl aber gegen exakt die Struktur, die
``yf.download`` liefert -- Spalten-MultiIndex bei mehreren Tickern, flache
Spalten bei einem.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from techrot.data import DataError, YFinanceProvider

START = datetime(2026, 1, 1)
END = datetime(2026, 1, 8)
DATES = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])

FIELDS = ["Close", "High", "Low", "Open", "Volume"]


def multi_frame(tickers: list[str], *, missing: set[str] = frozenset()) -> pd.DataFrame:
    """Baut die MultiIndex-Antwort von yf.download nach (group_by='column')."""
    data: dict[tuple[str, str], list[float]] = {}
    for field in FIELDS:
        for i, ticker in enumerate(tickers):
            if ticker in missing:
                values = [np.nan] * len(DATES)
            elif field == "Volume":
                values = [1_000_000.0 * (i + 1)] * len(DATES)
            else:
                values = [100.0 + i * 10 + j for j in range(len(DATES))]
            data[(field, ticker)] = values

    frame = pd.DataFrame(data, index=DATES)
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)
    return frame


def flat_frame() -> pd.DataFrame:
    """Antwort fuer einen einzelnen Ticker: flache Spalten."""
    return pd.DataFrame(
        {
            "Close": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Open": [99.5, 100.5, 101.5],
            "Volume": [1_000_000.0] * 3,
        },
        index=DATES,
    )


@pytest.fixture
def fake_download(monkeypatch):
    """Ersetzt yf.download durch eine Funktion, die ein festes Frame liefert."""
    import yfinance

    def install(frame, recorder: list | None = None):
        def download(*args, **kwargs):
            if recorder is not None:
                recorder.append((args, kwargs))
            return frame

        monkeypatch.setattr(yfinance, "download", download)

    return install


def test_mehrere_ticker_werden_entpackt(fake_download):
    fake_download(multi_frame(["AAPL", "MSFT", "NVDA"]))
    close, volume = YFinanceProvider().fetch(["AAPL", "MSFT", "NVDA"], START, END)

    assert list(close.columns) == ["AAPL", "MSFT", "NVDA"]
    assert list(volume.columns) == ["AAPL", "MSFT", "NVDA"]
    assert len(close) == 3
    assert close["AAPL"].iloc[0] == pytest.approx(100.0)
    assert close["MSFT"].iloc[0] == pytest.approx(110.0)
    assert volume["NVDA"].iloc[0] == pytest.approx(3_000_000.0)
    assert close.dtypes.unique().tolist() == [np.dtype("float64")]


def test_spaltenreihenfolge_folgt_der_anfrage(fake_download):
    """Yahoo sortiert alphabetisch; die Reihenfolge muss der Anfrage folgen,
    sonst passen Kurse und Ticker spaeter nicht mehr zusammen."""
    fake_download(multi_frame(["AAPL", "MSFT", "NVDA"]))
    close, _ = YFinanceProvider().fetch(["NVDA", "AAPL", "MSFT"], START, END)

    assert list(close.columns) == ["NVDA", "AAPL", "MSFT"]
    # NVDA war im Rohframe der dritte Ticker, also Basis 120.
    assert close["NVDA"].iloc[0] == pytest.approx(120.0)


def test_einzelner_ticker_mit_flachen_spalten(fake_download):
    fake_download(flat_frame())
    close, volume = YFinanceProvider().fetch(["AAPL"], START, END)

    assert list(close.columns) == ["AAPL"]
    assert close["AAPL"].iloc[-1] == pytest.approx(102.0)
    assert volume["AAPL"].iloc[0] == pytest.approx(1_000_000.0)


def test_fehlender_ticker_wird_zu_nan_statt_zum_absturz(fake_download):
    """Liefert Yahoo einen Ticker gar nicht mit, darf das nicht den ganzen
    Lauf abbrechen -- der Titel faellt ueber die Qualitaetspruefung heraus."""
    fake_download(multi_frame(["AAPL", "MSFT"]))
    close, volume = YFinanceProvider().fetch(["AAPL", "MSFT", "GIBTESNICHT"], START, END)

    assert list(close.columns) == ["AAPL", "MSFT", "GIBTESNICHT"]
    assert close["GIBTESNICHT"].isna().all()
    assert volume["GIBTESNICHT"].isna().all()
    assert close["AAPL"].notna().all()


def test_delisteter_ticker_kommt_als_nan_spalte(fake_download):
    fake_download(multi_frame(["AAPL", "TOT"], missing={"TOT"}))
    close, _ = YFinanceProvider().fetch(["AAPL", "TOT"], START, END)
    assert close["TOT"].isna().all()
    assert close["AAPL"].notna().all()


def test_leere_antwort_wird_gemeldet(fake_download):
    fake_download(pd.DataFrame())
    with pytest.raises(DataError, match="lieferte keine Daten"):
        YFinanceProvider().fetch(["AAPL"], START, END)


def test_none_antwort_wird_gemeldet(fake_download):
    fake_download(None)
    with pytest.raises(DataError, match="lieferte keine Daten"):
        YFinanceProvider().fetch(["AAPL"], START, END)


def test_zeitzone_wird_abgestreift(fake_download):
    frame = multi_frame(["AAPL"])
    frame.index = frame.index.tz_localize("America/New_York")
    fake_download(frame)

    close, _ = YFinanceProvider().fetch(["AAPL"], START, END)
    assert close.index.tz is None


def test_doppelte_datumszeile_wird_entfernt(fake_download):
    frame = multi_frame(["AAPL"])
    doppelt = pd.concat([frame, frame.iloc[[-1]]])
    fake_download(doppelt)

    close, _ = YFinanceProvider().fetch(["AAPL"], START, END)
    assert close.index.is_unique
    assert len(close) == 3


def test_unsortierte_antwort_wird_sortiert(fake_download):
    fake_download(multi_frame(["AAPL"]).iloc[::-1])
    close, _ = YFinanceProvider().fetch(["AAPL"], START, END)
    assert close.index.is_monotonic_increasing


def test_anfrage_nutzt_adjustierte_kurse(fake_download):
    aufrufe: list = []
    fake_download(multi_frame(["AAPL"]), recorder=aufrufe)
    YFinanceProvider().fetch(["AAPL"], START, END)

    _, kwargs = aufrufe[0]
    # Ohne auto_adjust waeren Splits und Dividenden nicht eingerechnet und
    # jedes Momentum-Signal waere an jedem Split falsch.
    assert kwargs["auto_adjust"] is True
    assert kwargs["start"] == "2026-01-01"
    assert kwargs["end"] == "2026-01-08"
