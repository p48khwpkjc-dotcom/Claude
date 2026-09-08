"""Portfoliobau: Auswahl, Gewichtung, Turnover-Bremse, Orders."""

from __future__ import annotations

import pandas as pd
import pytest

from techrot.config import SelectionConfig
from techrot.portfolio import (
    apply_exposure,
    build_orders,
    compute_weights,
    limit_turnover,
    select_holdings,
    turnover,
    weights_from_positions,
)


def make_ranking(scores: dict[str, float], vols: dict[str, float] | None = None):
    frame = pd.DataFrame({"score": pd.Series(scores, dtype="float64")})
    frame["volatility"] = pd.Series(vols or {t: 0.30 for t in scores}, dtype="float64")
    frame = frame.sort_values("score", ascending=False)
    frame.insert(0, "rank", range(1, len(frame) + 1))
    return frame


SELECTION = SelectionConfig(top_n=3, buffer_rank=5, weighting="equal")


def test_auswahl_ohne_bestand_nimmt_die_besten():
    ranking = make_ranking({"A": 3.0, "B": 2.0, "C": 1.0, "D": 0.5, "E": 0.1})
    selected = select_holdings(ranking, set(ranking.index), set(), SELECTION)
    assert selected == ["A", "B", "C"]


def test_bestandsschutz_haelt_titel_bis_zum_puffer():
    # E steht auf Rang 5 und damit noch innerhalb des Puffers.
    ranking = make_ranking({"A": 3.0, "B": 2.0, "C": 1.0, "D": 0.5, "E": 0.1})
    selected = select_holdings(ranking, set(ranking.index), {"E"}, SELECTION)
    assert "E" in selected
    assert selected == ["A", "B", "E"]


def test_bestandsschutz_endet_hinter_dem_puffer():
    ranking = make_ranking(
        {"A": 3.0, "B": 2.0, "C": 1.0, "D": 0.5, "E": 0.1, "F": 0.0, "G": -1.0}
    )
    # G ist Rang 7, also ausserhalb von buffer_rank=5.
    selected = select_holdings(ranking, set(ranking.index), {"G"}, SELECTION)
    assert "G" not in selected
    assert selected == ["A", "B", "C"]


def test_nicht_eligible_titel_werden_uebersprungen():
    ranking = make_ranking({"A": 3.0, "B": 2.0, "C": 1.0, "D": 0.5})
    selected = select_holdings(ranking, {"C", "D"}, set(), SELECTION)
    assert selected == ["C", "D"]


def test_auswahl_ignoriert_scorelose_titel():
    ranking = make_ranking({"A": 3.0, "B": float("nan"), "C": 1.0})
    selected = select_holdings(ranking, set(ranking.index), set(), SELECTION)
    assert selected == ["A", "C"]


def test_gleichgewichtung_summiert_auf_eins():
    ranking = make_ranking({"A": 3.0, "B": 2.0, "C": 1.0})
    weights = compute_weights(["A", "B", "C"], ranking, SELECTION, max_position_weight=0.5)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert all(w == pytest.approx(1 / 3) for w in weights.values())


def test_inverse_vol_gewichtet_ruhige_titel_hoeher():
    ranking = make_ranking(
        {"A": 3.0, "B": 2.0}, vols={"A": 0.60, "B": 0.20}
    )
    cfg = SelectionConfig(top_n=2, buffer_rank=3, weighting="inverse_vol")
    weights = compute_weights(["A", "B"], ranking, cfg, max_position_weight=1.0)
    assert weights["B"] > weights["A"]
    # 1/0.2 : 1/0.6 = 3 : 1
    assert weights["B"] / weights["A"] == pytest.approx(3.0)


def test_fehlende_vol_bekommt_den_median():
    ranking = make_ranking(
        {"A": 3.0, "B": 2.0, "C": 1.0}, vols={"A": 0.20, "B": 0.40, "C": float("nan")}
    )
    cfg = SelectionConfig(top_n=3, buffer_rank=4, weighting="inverse_vol")
    weights = compute_weights(["A", "B", "C"], ranking, cfg, max_position_weight=1.0)
    assert sum(weights.values()) == pytest.approx(1.0)
    # C erbt den Median 0.30 und liegt damit zwischen A und B.
    assert weights["A"] > weights["C"] > weights["B"]


def test_positionslimit_wird_eingehalten():
    ranking = make_ranking(
        {"A": 3.0, "B": 2.0, "C": 1.0}, vols={"A": 0.05, "B": 0.50, "C": 0.50}
    )
    cfg = SelectionConfig(top_n=3, buffer_rank=4, weighting="inverse_vol")
    weights = compute_weights(["A", "B", "C"], ranking, cfg, max_position_weight=0.40)
    assert max(weights.values()) <= 0.40 + 1e-9
    assert sum(weights.values()) == pytest.approx(1.0)


def test_apply_exposure_normiert_auf_das_ziel():
    weights = apply_exposure({"A": 0.5, "B": 0.5}, 0.6)
    assert sum(weights.values()) == pytest.approx(0.6)
    assert apply_exposure({"A": 1.0}, 0.0) == {}
    assert apply_exposure({}, 0.8) == {}


def test_turnover_zaehlt_einseitig():
    assert turnover({"A": 1.0}, {"A": 1.0}) == pytest.approx(0.0)
    # Komplett aus A raus und in B rein ist ein Turnover von 100 %.
    assert turnover({"A": 1.0}, {"B": 1.0}) == pytest.approx(1.0)
    assert turnover({}, {"A": 0.5}) == pytest.approx(0.25)


def test_turnover_bremse_daempft_auf_das_limit():
    current = {"A": 1.0}
    target = {"B": 1.0}
    blended, alpha = limit_turnover(current, target, cap=0.30)
    assert alpha == pytest.approx(0.30)
    assert turnover(current, blended) == pytest.approx(0.30)
    assert blended["A"] == pytest.approx(0.70)
    assert blended["B"] == pytest.approx(0.30)


def test_turnover_bremse_greift_nicht_unter_dem_limit():
    current = {"A": 0.5, "B": 0.5}
    target = {"A": 0.55, "B": 0.45}
    blended, alpha = limit_turnover(current, target, cap=0.30)
    assert alpha == 1.0
    assert blended == target


def test_weights_from_positions():
    prices = pd.Series({"A": 100.0, "B": 50.0})
    weights = weights_from_positions({"A": 10.0, "B": 20.0}, prices, equity=2000.0)
    assert weights["A"] == pytest.approx(0.5)
    assert weights["B"] == pytest.approx(0.5)
    assert weights_from_positions({"A": 10.0}, prices, equity=0.0) == {}


def test_orders_runden_auf_ganze_stuecke():
    prices = pd.Series({"A": 100.0})
    orders = build_orders({}, {"A": 0.5}, prices, equity=10_000.0, min_order_notional=100)
    assert len(orders) == 1
    # 5000 USD / 100 = 50 Stueck, abgerundet.
    assert orders[0].quantity == 50
    assert orders[0].side == "buy"


def test_kleine_orders_entfallen():
    prices = pd.Series({"A": 100.0})
    # Zielabweichung von 100 USD liegt unter der Mindestgroesse von 250.
    orders = build_orders({"A": 49.0}, {"A": 0.5}, prices, equity=10_000.0, min_order_notional=250)
    assert orders == []


def test_verkaeufe_kommen_vor_kaeufen():
    prices = pd.Series({"A": 100.0, "B": 100.0})
    orders = build_orders(
        {"A": 100.0}, {"B": 1.0}, prices, equity=10_000.0, min_order_notional=100
    )
    assert [o.side for o in orders] == ["sell", "buy"]
    assert orders[0].ticker == "A"
    assert orders[0].quantity == -100


def test_orders_ohne_kurs_werden_uebersprungen():
    prices = pd.Series({"A": float("nan")})
    assert build_orders({}, {"A": 1.0}, prices, equity=10_000.0, min_order_notional=1) == []
