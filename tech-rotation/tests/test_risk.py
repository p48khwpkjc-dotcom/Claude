"""Risikopruefung: Eignungsfilter und Exposure-Entscheidung."""

from __future__ import annotations

import pandas as pd
import pytest
from conftest import BENCHMARK, make_panel

from techrot.data import PriceData, check_data_quality
from techrot.ranking import rank_universe
from techrot.risk import check_eligibility, current_drawdown, decide_exposure, regime_ok


def _eligibility(panel: PriceData, cfg):
    quality = check_data_quality(panel, list(cfg.tickers), cfg.data, panel.last_date)
    metrics = rank_universe(panel, cfg.ranking)
    return check_eligibility(panel, metrics, quality, cfg.risk.eligibility)


def test_illiquider_titel_faellt_raus(panel: PriceData, cfg):
    result = _eligibility(panel, cfg)
    assert not result["T09"].eligible
    assert "Liquiditaet" in result["T09"].reason_text


def test_fallender_titel_faellt_raus(panel: PriceData, cfg):
    result = _eligibility(panel, cfg)
    for ticker in ("T10", "T11"):
        assert not result[ticker].eligible
        reason = result[ticker].reason_text
        assert "absolutes Momentum negativ" in reason or "unter SMA" in reason


def test_steigende_liquide_titel_bleiben_drin(panel: PriceData, cfg):
    result = _eligibility(panel, cfg)
    for ticker in ("T00", "T01", "T02", "T03"):
        assert result[ticker].eligible, result[ticker].reason_text


def test_volatilitaetslimit_greift(panel: PriceData, cfg, tmp_path):
    from conftest import write_config
    from techrot.config import load_config

    strict = load_config(
        write_config(
            tmp_path, list(cfg.tickers), risk={"eligibility": {"max_annual_vol": 0.01}}
        )
    )
    result = _eligibility(panel, strict)
    assert all(not e.eligible for e in result.values())
    assert any("Volatilitaet" in e.reason_text for e in result.values())


def test_regime_filter_erkennt_beide_richtungen():
    steigend = make_panel(benchmark_drift=0.0006)
    fallend = make_panel(benchmark_drift=-0.0012)
    assert regime_ok(steigend, BENCHMARK, 200) is True
    assert regime_ok(fallend, BENCHMARK, 200) is False
    # Unbekannter Benchmark oder abgeschalteter Filter: keine Aussage.
    assert regime_ok(steigend, "GIBTESNICHT", 200) is None
    assert regime_ok(steigend, BENCHMARK, 0) is None


def test_regime_bruch_setzt_exposure_auf_null(cfg):
    fallend = make_panel(benchmark_drift=-0.0012)
    decision = decide_exposure(
        fallend, {"T00": 0.5, "T01": 0.5}, cfg.risk.portfolio, BENCHMARK
    )
    assert decision.exposure == 0.0
    assert decision.regime_ok is False
    assert any("Regime-Filter" in n for n in decision.notes)


def test_ohne_kandidaten_keine_exposure(panel: PriceData, cfg):
    decision = decide_exposure(panel, {}, cfg.risk.portfolio, BENCHMARK)
    assert decision.exposure == 0.0
    assert any("Eignungspruefung" in n for n in decision.notes)


def test_zu_wenige_titel_drosseln_proportional(panel: PriceData, cfg, tmp_path):
    from conftest import write_config
    from techrot.config import load_config

    strenger = load_config(
        write_config(
            tmp_path,
            list(cfg.tickers),
            risk={"portfolio": {"min_names": 4, "vol_target": 0, "regime_sma": 0}},
        )
    )
    decision = decide_exposure(panel, {"T00": 0.5, "T01": 0.5}, strenger.risk.portfolio, BENCHMARK)
    # 2 von 4 geforderten Titeln -> halbe Exposure.
    assert decision.exposure == pytest.approx(0.5)


def test_vol_targeting_skaliert_herunter(panel: PriceData, cfg, tmp_path):
    from conftest import write_config
    from techrot.config import load_config

    ziel = load_config(
        write_config(
            tmp_path,
            list(cfg.tickers),
            risk={"portfolio": {"vol_target": 0.01, "regime_sma": 0, "min_names": 1}},
        )
    )
    decision = decide_exposure(panel, {"T00": 0.5, "T01": 0.5}, ziel.risk.portfolio, BENCHMARK)
    assert decision.realized_vol is not None and decision.realized_vol > 0.01
    assert decision.vol_scalar < 1.0
    assert decision.exposure == pytest.approx(decision.vol_scalar, abs=1e-9)


def test_vol_scalar_wird_nach_oben_gedeckelt(panel: PriceData, cfg, tmp_path):
    from conftest import write_config
    from techrot.config import load_config

    ziel = load_config(
        write_config(
            tmp_path,
            list(cfg.tickers),
            risk={
                "portfolio": {
                    "vol_target": 5.0,
                    "max_vol_scalar": 1.0,
                    "regime_sma": 0,
                    "min_names": 1,
                }
            },
        )
    )
    decision = decide_exposure(panel, {"T00": 1.0}, ziel.risk.portfolio, BENCHMARK)
    assert decision.vol_scalar == pytest.approx(1.0)
    assert decision.exposure <= ziel.risk.portfolio.max_gross_exposure


def test_drawdown_berechnung():
    assert current_drawdown(None) == 0.0
    flat = pd.Series([100.0, 100.0], index=pd.bdate_range(periods=2, end="2026-01-01"))
    assert current_drawdown(flat) == 0.0
    fallend = pd.Series([100.0, 120.0, 90.0], index=pd.bdate_range(periods=3, end="2026-01-01"))
    assert current_drawdown(fallend) == pytest.approx(0.25)


def test_drawdown_bremse_reduziert_exposure(panel: PriceData, cfg):
    # 30 % Rueckgang bei 20 % Limit: halber Weg zum Boden von 30 %.
    curve = pd.Series([100.0, 70.0], index=pd.bdate_range(periods=2, end="2026-01-01"))
    decision = decide_exposure(
        panel, {"T00": 0.5, "T01": 0.5}, cfg.risk.portfolio, BENCHMARK, equity_curve=curve
    )
    assert decision.current_drawdown == pytest.approx(0.30)
    assert decision.drawdown_scalar == pytest.approx(1.0 - 0.5 * (1.0 - 0.30))
    assert any("Drawdown-Bremse" in n for n in decision.notes)


def test_drawdown_bremse_haelt_den_boden(panel: PriceData, cfg):
    # 80 % Rueckgang liegt weit jenseits der doppelten Schwelle.
    curve = pd.Series([100.0, 20.0], index=pd.bdate_range(periods=2, end="2026-01-01"))
    decision = decide_exposure(
        panel, {"T00": 1.0}, cfg.risk.portfolio, BENCHMARK, equity_curve=curve
    )
    assert decision.drawdown_scalar == pytest.approx(cfg.risk.portfolio.drawdown_exposure_floor)
