"""Backtest mit wechselndem Universum und endenden Kursreihen.

Die beiden Wege, auf denen sich Survivorship-Bias zurueck in einen Backtest
schleicht: ein Universum, das spaeteres Wissen enthaelt, und Titel, die bei
einer Uebernahme still aus der Bewertung fallen.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import make_panel, write_config

from techrot.backtest import fill_inner_gaps, run_backtest
from techrot.config import load_config
from techrot.data import PriceData


def _cfg(tmp_path, tickers, **overrides):
    base = {
        "backtest": {"start": "2025-06-01", "end": None, "rebalance": "month_start"},
    }
    base.update(overrides)
    return load_config(write_config(tmp_path, tickers, **base))


# --------------------------------------------------------------------------
# Lueckenfuellung
# --------------------------------------------------------------------------


def test_innere_luecken_werden_geschlossen_das_ende_nicht():
    index = pd.bdate_range("2026-01-01", periods=6)
    close = pd.DataFrame(
        {
            # Luecke am dritten Tag, Reihe endet nach dem vierten.
            "A": [10.0, 11.0, np.nan, 12.0, np.nan, np.nan],
            # Boersengang erst am dritten Tag.
            "B": [np.nan, np.nan, 5.0, 5.5, 6.0, 6.5],
        },
        index=index,
    )
    out = fill_inner_gaps(close)

    assert out["A"].tolist()[:4] == [10.0, 11.0, 11.0, 12.0]
    assert out["A"].iloc[4:].isna().all(), "nach dem letzten Kurs darf nichts erfunden werden"
    assert out["B"].iloc[:2].isna().all(), "vor dem Boersengang darf nichts erfunden werden"
    assert out["B"].iloc[2:].tolist() == [5.0, 5.5, 6.0, 6.5]


def test_leere_reihe_bleibt_leer():
    index = pd.bdate_range("2026-01-01", periods=3)
    close = pd.DataFrame({"A": [1.0, 2.0, 3.0], "LEER": [np.nan] * 3}, index=index)
    out = fill_inner_gaps(close)
    assert out["LEER"].isna().all()
    assert out["A"].tolist() == [1.0, 2.0, 3.0]


# --------------------------------------------------------------------------
# Endende Kursreihen
# --------------------------------------------------------------------------


def _panel_mit_ende(ticker: str, ende: pd.Timestamp) -> PriceData:
    """Panel, in dem die Reihe von ``ticker`` nach ``ende`` abbricht."""
    panel = make_panel()
    close = panel.close.copy()
    volume = panel.volume.copy()
    close.loc[close.index > ende, ticker] = np.nan
    volume.loc[volume.index > ende, ticker] = np.nan
    return PriceData(close=close, volume=volume)


def test_titel_mit_endender_reihe_wird_zu_cash_statt_zu_null(tmp_path):
    """Der Kern: kein fiktiver Totalverlust, wenn ein gehaltener Titel endet."""
    panel = make_panel()
    tickers = [c for c in panel.close.columns if c != "QQQ"]
    cfg = _cfg(tmp_path, tickers)

    # Erst ohne Ende laufen lassen, um einen sicher gehaltenen Titel zu finden.
    probe = run_backtest(cfg, panel)
    gehalten = probe.trades[probe.trades["side"] == "buy"]["ticker"].iloc[0]
    erster_kauf = probe.trades[probe.trades["ticker"] == gehalten]["date"].min()
    ende = panel.close.index[panel.close.index.get_loc(erster_kauf) + 5]

    result = run_backtest(cfg, _panel_mit_ende(gehalten, ende))

    assert not result.delistings.empty
    zeile = result.delistings[result.delistings["ticker"] == gehalten].iloc[0]
    assert zeile["last_date"] == ende
    assert zeile["price"] == pytest.approx(float(panel.close.at[ende, gehalten]))

    # Der Depotwert darf am Tag nach dem Ende nicht um den Positionswert
    # einbrechen. Erlaubt ist nur die normale Tagesschwankung der uebrigen
    # Titel -- hier deutlich unter 5 %.
    tag_danach = result.equity.index[result.equity.index.get_loc(ende) + 1]
    sprung = result.equity[tag_danach] / result.equity[ende] - 1
    assert abs(sprung) < 0.05, f"Depotwert springt um {sprung:.1%} -- Position mit null bewertet?"


def test_beendeter_titel_wird_danach_nicht_mehr_gekauft(tmp_path):
    panel = make_panel()
    tickers = [c for c in panel.close.columns if c != "QQQ"]
    cfg = _cfg(tmp_path, tickers)
    ende = pd.Timestamp("2025-09-15")

    result = run_backtest(cfg, _panel_mit_ende("T00", ende))

    kaeufe = result.trades[(result.trades["ticker"] == "T00") & (result.trades["side"] == "buy")]
    assert (kaeufe["date"] <= ende + pd.Timedelta(days=1)).all()


# --------------------------------------------------------------------------
# Universum zum Stichtag
# --------------------------------------------------------------------------


def test_nichtmitglied_wird_nie_gewaehlt_auch_nicht_als_bester(tmp_path):
    panel = make_panel()
    tickers = [c for c in panel.close.columns if c != "QQQ"]
    cfg = _cfg(tmp_path, tickers)

    # T00 hat im Fixture das staerkste Momentum. Ohne Universumsfilter wird
    # er gekauft -- mit Filter darf er nie auftauchen.
    ohne = run_backtest(cfg, panel)
    assert "T00" in set(ohne.trades["ticker"])

    mit = run_backtest(cfg, panel, universe_at=lambda d: [t for t in tickers if t != "T00"])
    assert "T00" not in set(mit.trades["ticker"])
    assert (mit.rebalances["n_universe"] == len(tickers) - 1).all()


def test_universum_wird_am_signaltag_abgefragt_nicht_spaeter(tmp_path):
    """Look-ahead-Schutz: die Mitgliedschaft gilt zum Signal, nicht zur Ausfuehrung."""
    panel = make_panel()
    tickers = [c for c in panel.close.columns if c != "QQQ"]
    cfg = _cfg(tmp_path, tickers)

    abgefragt: list[pd.Timestamp] = []

    def universum(tag: pd.Timestamp) -> list[str]:
        abgefragt.append(tag)
        return tickers

    result = run_backtest(cfg, panel, universe_at=universum)
    assert abgefragt == list(result.rebalances["signal_date"])


def test_gehaltener_titel_der_das_universum_verlaesst_wird_verkauft(tmp_path):
    panel = make_panel()
    tickers = [c for c in panel.close.columns if c != "QQQ"]
    cfg = _cfg(tmp_path, tickers)

    stichtag = pd.Timestamp("2025-10-01")

    def universum(tag: pd.Timestamp) -> list[str]:
        # T00 fliegt zum Stichtag aus dem Index.
        return tickers if tag < stichtag else [t for t in tickers if t != "T00"]

    result = run_backtest(cfg, panel, universe_at=universum)
    t00 = result.trades[result.trades["ticker"] == "T00"]
    assert not t00[t00["date"] < stichtag].empty, "T00 sollte vorher gehalten werden"

    # Nach dem Austritt: verkauft, und danach kein neuer Kauf.
    danach = t00[t00["date"] >= stichtag]
    assert (danach["side"] == "sell").any()
    assert not (danach["side"] == "buy").any()


def test_ohne_universumsfunktion_unveraendertes_verhalten(tmp_path):
    panel = make_panel()
    tickers = [c for c in panel.close.columns if c != "QQQ"]
    cfg = _cfg(tmp_path, tickers)

    a = run_backtest(cfg, panel)
    b = run_backtest(cfg, panel, universe_at=lambda d: tickers)
    pd.testing.assert_series_equal(a.equity, b.equity)
    assert (a.rebalances["n_universe"] == len(tickers)).all()
