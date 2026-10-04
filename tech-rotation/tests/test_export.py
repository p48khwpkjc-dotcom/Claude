"""Der JSON-Export muss den Lauf vollstaendig und gueltig beschreiben."""

from __future__ import annotations

import json
import math

import pytest

from techrot.config import load_config
from techrot.execution import plan_rebalance
from techrot.export import SCHEMA_VERSION, plan_to_dict, write_plan_json
from techrot.state import PortfolioState

from conftest import make_panel, write_config


@pytest.fixture
def lauf(tmp_path, panel, tickers):
    cfg = load_config(write_config(tmp_path, tickers))
    state = PortfolioState(cash=100_000.0)
    plan = plan_rebalance(cfg, panel, state, force=True)
    return cfg, plan, state


def test_jeder_ticker_des_universums_kommt_vor(lauf):
    cfg, plan, state = lauf
    payload = plan_to_dict(cfg, plan, state)
    assert [t["ticker"] for t in payload["tickers"]] == list(cfg.tickers)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["signal_date"] == str(plan.asof.date())


def test_signalbeitraege_summieren_sich_zum_score(lauf):
    """Der Score muss aus den ausgewiesenen Beitraegen hervorgehen.

    Sonst zeigt die Ansicht eine Zerlegung, die den Gesamtwert nicht erklaert
    -- und genau diese Zerlegung ist der Zweck des Exports.
    """
    cfg, plan, state = lauf
    payload = plan_to_dict(cfg, plan, state)

    geprueft = 0
    for entry in payload["tickers"]:
        if entry["score"] is None:
            continue
        beitraege = [
            s["contribution"] for s in entry["signals"].values() if s["contribution"] is not None
        ]
        assert math.isclose(sum(beitraege), entry["score"], rel_tol=1e-9, abs_tol=1e-9)
        geprueft += 1
    assert geprueft > 0


def test_gewichte_der_signale_summieren_sich_auf_eins(lauf):
    cfg, plan, state = lauf
    payload = plan_to_dict(cfg, plan, state)
    assert math.isclose(sum(payload["rules"]["signal_weights"].values()), 1.0, abs_tol=1e-12)


def test_gesperrter_ticker_traegt_seine_begruendung(lauf):
    cfg, plan, state = lauf
    payload = plan_to_dict(cfg, plan, state)
    gesperrt = [t for t in payload["tickers"] if not t["eligible"]]
    assert gesperrt, "Fixture sollte abgelehnte Titel enthalten"
    for entry in payload["tickers"]:
        if entry["eligible"]:
            assert entry["reasons"] == []
        else:
            assert entry["reasons"], f"{entry['ticker']} ist gesperrt, nennt aber keinen Grund"


def test_ausgewaehlte_titel_haben_zielgewicht(lauf):
    cfg, plan, state = lauf
    payload = plan_to_dict(cfg, plan, state)
    gewaehlt = [t for t in payload["tickers"] if t["selected"]]
    assert gewaehlt
    for entry in gewaehlt:
        assert entry["target_weight"] > 0
        assert entry["eligible"]


def test_rang_ist_lueckenlos_und_nach_score_sortiert(lauf):
    cfg, plan, state = lauf
    payload = plan_to_dict(cfg, plan, state)
    mit_rang = sorted(
        (t for t in payload["tickers"] if t["rank"] is not None), key=lambda t: t["rank"]
    )
    assert [t["rank"] for t in mit_rang] == list(range(1, len(mit_rang) + 1))
    scores = [t["score"] for t in mit_rang if t["score"] is not None]
    assert scores == sorted(scores, reverse=True)


def test_nan_wird_zu_null_und_json_bleibt_parsebar(tmp_path):
    """NaN ist kein gueltiges JSON -- ein Browser wuerde die Datei ablehnen."""
    panel = make_panel(n_tickers=6)
    panel.close["T03"] = float("nan")
    tickers = [c for c in panel.close.columns if c != "QQQ"]
    cfg = load_config(write_config(tmp_path, tickers, selection={"top_n": 3, "buffer_rank": 4}))
    state = PortfolioState(cash=100_000.0)
    plan = plan_rebalance(cfg, panel, state, force=True)

    out = tmp_path / "ranking.json"
    write_plan_json(out, cfg, plan, state)

    rohtext = out.read_text(encoding="utf-8")
    assert "NaN" not in rohtext
    assert "Infinity" not in rohtext
    payload = json.loads(rohtext)  # wuerde bei NaN scheitern

    kaputt = next(t for t in payload["tickers"] if t["ticker"] == "T03")
    assert kaputt["score"] is None
    assert kaputt["eligible"] is False
    assert kaputt["reasons"]


def test_equity_historie_wird_mitgegeben(lauf):
    from datetime import date

    cfg, plan, state = lauf
    state.record_equity(date(2026, 1, 2), 101_000.0)
    payload = plan_to_dict(cfg, plan, state)
    assert payload["equity_history"] == [{"date": "2026-01-02", "equity": 101_000.0}]


def test_orders_landen_im_export(lauf):
    cfg, plan, state = lauf
    payload = plan_to_dict(cfg, plan, state)
    assert len(payload["orders"]) == len(plan.orders)
    assert payload["orders"], "erster Lauf aus Cash muss Orders erzeugen"
    for order in payload["orders"]:
        assert order["side"] in {"buy", "sell"}
        assert order["notional"] > 0


def test_exposure_und_regeln_sind_vollstaendig(lauf):
    cfg, plan, state = lauf
    payload = plan_to_dict(cfg, plan, state)
    assert payload["exposure"]["exposure"] is not None
    assert payload["rules"]["top_n"] == cfg.selection.top_n
    assert payload["rules"]["buffer_rank"] == cfg.selection.buffer_rank
    assert payload["rules"]["max_annual_vol"] == cfg.risk.eligibility.max_annual_vol


def test_checks_nennen_regel_zahl_und_limit(lauf):
    """Jede Sperre muss maschinenlesbar begruendet sein.

    Eine Ansicht soll zeigen koennen, wie knapp eine Regel gegriffen hat,
    ohne die deutschen Begruendungstexte zu zerlegen.
    """
    cfg, plan, state = lauf
    payload = plan_to_dict(cfg, plan, state)

    gesperrt = [t for t in payload["tickers"] if not t["eligible"]]
    assert gesperrt

    for entry in payload["tickers"]:
        regeln = {c["rule"] for c in entry["checks"]}
        assert "data" in regeln
        # Die Checks muessen dasselbe Urteil tragen wie das Gesamtergebnis.
        alle_ok = all(c["ok"] for c in entry["checks"])
        assert alle_ok == entry["eligible"]
        # Und so viele Fehlschlaege, wie Begruendungen genannt werden.
        assert sum(1 for c in entry["checks"] if not c["ok"]) == len(entry["reasons"])


def test_momentum_check_vergleicht_gegen_null(lauf):
    cfg, plan, state = lauf
    payload = plan_to_dict(cfg, plan, state)
    fallend = [
        t
        for t in payload["tickers"]
        if any(c["rule"] == "abs_momentum" and not c["ok"] for c in t["checks"])
    ]
    assert fallend, "Fixture sollte fallende Titel enthalten"
    for entry in fallend:
        check = next(c for c in entry["checks"] if c["rule"] == "abs_momentum")
        assert check["limit"] == 0.0
        assert check["value"] is not None and check["value"] <= 0


def test_liquiditaetscheck_traegt_das_handelsvolumen(lauf):
    """Das Volumen steht in keiner Kennzahl -- nur der Check kennt es."""
    cfg, plan, state = lauf
    payload = plan_to_dict(cfg, plan, state)
    werte = [
        c["value"]
        for t in payload["tickers"]
        for c in t["checks"]
        if c["rule"] == "liquidity" and c["value"] is not None
    ]
    assert werte
    assert all(v > 0 for v in werte)
    limits = {
        c["limit"] for t in payload["tickers"] for c in t["checks"] if c["rule"] == "liquidity"
    }
    assert limits == {cfg.risk.eligibility.min_avg_dollar_volume}
