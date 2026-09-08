"""Ranking: Renditemessung, z-Scores und Reihenfolge."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from conftest import make_panel

from techrot.config import Lookback
from techrot.data import PriceData
from techrot.ranking import (
    annualized_volatility,
    horizon_return,
    moving_average,
    rank_universe,
    zscore,
)


def test_horizon_return_misst_genau_das_fenster():
    # Kurs verdoppelt sich zwischen t-10 und t-2, danach faellt er.
    values = [100.0] * 91 + [200.0] * 8 + [50.0]
    close = pd.DataFrame({"X": values}, index=pd.bdate_range(periods=100, end="2026-01-01"))

    # start=10, end=2 -> von Index -11 (100) bis Index -3 (200) = +100 %
    result = horizon_return(close, Lookback(start=10, end=2))
    assert result["X"] == pytest.approx(1.0)

    # end=0 nimmt den letzten Kurs und sieht damit den Einbruch.
    result_incl = horizon_return(close, Lookback(start=10, end=0))
    assert result_incl["X"] == pytest.approx(-0.5)


def test_horizon_return_ohne_genug_historie_ist_nan():
    close = pd.DataFrame({"X": [1.0, 2.0, 3.0]}, index=pd.bdate_range(periods=3, end="2026-01-01"))
    assert math.isnan(horizon_return(close, Lookback(start=252, end=21))["X"])


def test_annualisierte_vol_einer_konstanten_reihe_ist_null():
    close = pd.DataFrame({"X": [100.0] * 80}, index=pd.bdate_range(periods=80, end="2026-01-01"))
    assert annualized_volatility(close, 63)["X"] == pytest.approx(0.0)


def test_vol_braucht_ein_halbwegs_volles_fenster():
    values = [np.nan] * 70 + [100.0, 101.0, 102.0, 103.0, 104.0]
    close = pd.DataFrame({"X": values}, index=pd.bdate_range(periods=75, end="2026-01-01"))
    assert math.isnan(annualized_volatility(close, 63)["X"])


def test_moving_average_nimmt_das_letzte_fenster():
    close = pd.DataFrame(
        {"X": list(range(1, 21))}, index=pd.bdate_range(periods=20, end="2026-01-01")
    )
    # Mittel von 16..20
    assert moving_average(close, 5)["X"] == pytest.approx(18.0)


def test_zscore_wird_winsorisiert():
    # Ein Ausreisser unter vielen Nullen liegt weit jenseits von 2 Sigma und
    # muss auf das Limit gekappt werden.
    series = pd.Series({f"t{i}": 0.0 for i in range(20)} | {"outlier": 1000.0})
    z = zscore(series, winsorize=2.0)
    assert z.max() == pytest.approx(2.0)
    assert z.min() >= -2.0


def test_zscore_ohne_streuung_ist_null():
    series = pd.Series({"a": 5.0, "b": 5.0, "c": 5.0})
    assert (zscore(series, 3.0) == 0.0).all()


def test_ranking_folgt_dem_trend_exakt(cfg):
    """Bei identischer Welle entscheidet allein der Trend."""
    ranking = rank_universe(make_panel(uniform_wiggle=True), cfg.ranking)
    positive = sorted(t for t in ranking.index if t.startswith("T") and int(t[1:]) <= 8)
    order = [t for t in ranking.index if t in positive]
    assert order == positive, f"Reihenfolge weicht ab: {order}"


def test_ranking_korreliert_mit_dem_trend(panel: PriceData, cfg):
    """Mit unterschiedlichen Wellen darf die Reihenfolge leicht abweichen,
    der Zusammenhang zum Trend muss aber deutlich bleiben."""
    ranking = rank_universe(panel, cfg.ranking)
    positive = [t for t in ranking.index if t.startswith("T") and int(t[1:]) <= 8]

    expected = pd.Series({t: int(t[1:]) for t in positive})
    actual = ranking.loc[positive, "rank"]
    # Rangkorrelation von Hand: Pearson auf den Raengen ist Spearman.
    # pandas' method="spearman" wuerde scipy nachladen, das hier nicht zu den
    # Abhaengigkeiten gehoert.
    assert expected.rank().corr(actual.rank()) > 0.85

    assert ranking.index[0] == "T00"
    # Fallende Titel landen hinter allen steigenden.
    assert ranking.loc["T10", "rank"] > ranking.loc["T08", "rank"]
    assert ranking.loc["T11", "rank"] > ranking.loc["T08", "rank"]
    assert ranking.loc["T10", "mom_12_1"] < 0


def test_ranking_beschraenkt_sich_auf_eligible(panel: PriceData, cfg):
    subset = ["T00", "T01", "T02"]
    ranking = rank_universe(panel, cfg.ranking, eligible=subset)
    assert list(ranking.index) == subset
    # z-Scores werden nur ueber die Teilmenge gebildet.
    assert ranking["z_mom_12_1"].abs().max() <= cfg.ranking.winsorize_z


def test_score_ist_nan_ohne_jedes_signal(cfg):
    index = pd.bdate_range(periods=400, end="2026-01-01")
    close = pd.DataFrame({"A": range(400), "B": [np.nan] * 400}, dtype="float64", index=index)
    volume = pd.DataFrame(1e9, index=index, columns=["A", "B"])
    ranking = rank_universe(PriceData(close=close, volume=volume), cfg.ranking)
    assert math.isnan(ranking.loc["B", "score"])
    assert ranking.loc["A", "rank"] == 1
