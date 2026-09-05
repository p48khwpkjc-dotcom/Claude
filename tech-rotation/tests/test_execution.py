"""Der komplette Lauf: Plan, Lookahead-Schutz und Ausfuehrung."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from conftest import make_panel, write_config

from techrot.brokers import BrokerError, PaperBroker
from techrot.config import load_config
from techrot.data import PriceData, load_prices
from techrot.execution import execute_plan, mark_to_market, plan_rebalance
from techrot.portfolio import Order
from techrot.report import plan_to_markdown, render_plan
from techrot.state import PortfolioState


def fresh_state(cfg) -> PortfolioState:
    return PortfolioState(cash=cfg.execution.starting_cash)


def test_plan_waehlt_die_staerksten_eligible_titel(panel: PriceData, cfg):
    plan = plan_rebalance(cfg, panel, fresh_state(cfg), force=True)

    assert len(plan.selected) == cfg.selection.top_n
    # Der illiquide T09 und die fallenden T10/T11 duerfen nicht vorkommen.
    assert "T09" not in plan.selected
    assert "T10" not in plan.selected and "T11" not in plan.selected
    assert plan.selected[0] == "T00"


def test_zielgewichte_respektieren_exposure_und_limit(panel: PriceData, cfg):
    plan = plan_rebalance(cfg, panel, fresh_state(cfg), force=True)
    total = sum(plan.target_weights.values())

    assert total == pytest.approx(plan.exposure.exposure, abs=1e-9)
    assert total <= cfg.risk.portfolio.max_gross_exposure + 1e-9
    assert max(plan.target_weights.values()) <= cfg.risk.portfolio.max_position_weight + 1e-9
    assert plan.cash_weight == pytest.approx(1.0 - total)


def test_orders_passen_zu_den_zielgewichten(panel: PriceData, cfg):
    state = fresh_state(cfg)
    plan = plan_rebalance(cfg, panel, state, force=True)

    assert plan.orders
    assert all(o.side == "buy" for o in plan.orders)
    invested = sum(o.notional for o in plan.orders)
    # Rundung auf ganze Stuecke laesst einen kleinen Rest liegen.
    assert invested <= plan.equity * sum(plan.target_weights.values()) + 1e-6
    assert invested > plan.equity * sum(plan.target_weights.values()) * 0.98


def test_kein_lookahead(panel: PriceData, cfg):
    """Der Plan zum Stichtag darf sich nicht aendern, wenn spaetere Kurse
    im Panel stehen -- sonst leckt Zukunftswissen ins Signal."""
    asof = panel.close.index[-200]

    mit_zukunft = plan_rebalance(cfg, panel, fresh_state(cfg), asof=asof, force=True)
    ohne_zukunft = plan_rebalance(cfg, panel.up_to(asof), fresh_state(cfg), force=True)

    assert mit_zukunft.asof == ohne_zukunft.asof == asof
    assert mit_zukunft.selected == ohne_zukunft.selected
    assert mit_zukunft.target_weights == pytest.approx(ohne_zukunft.target_weights)


def test_nicht_faelliger_lauf_erzeugt_keine_orders(panel: PriceData, cfg):
    state = fresh_state(cfg)
    state.last_rebalance = str(panel.last_date.date())

    plan = plan_rebalance(cfg, panel, state)
    assert plan.due is False
    assert plan.orders == []
    assert any("Kein Rebalancing faellig" in n for n in plan.notes)


def test_regime_bruch_fuehrt_in_cash(cfg):
    fallend = make_panel(benchmark_drift=-0.0012)
    plan = plan_rebalance(cfg, fallend, fresh_state(cfg), force=True)

    assert plan.exposure.regime_ok is False
    assert plan.target_weights == {}
    assert plan.cash_weight == pytest.approx(1.0)
    assert plan.orders == []


def test_ausfuehrung_aktualisiert_zustand_und_journal(panel: PriceData, cfg, tmp_path):
    cfg = load_config(write_config(tmp_path, list(cfg.tickers)))
    state = fresh_state(cfg)
    plan = plan_rebalance(cfg, panel, state, force=True)

    broker = PaperBroker(state, cfg.execution)
    fills = execute_plan(cfg, plan, state, broker)

    assert len(fills) == len(plan.orders)
    assert set(state.positions) == set(plan.target_weights)
    assert state.cash < cfg.execution.starting_cash
    assert state.last_rebalance == str(plan.asof.date())

    # Slippage wirkt gegen den Kaeufer.
    for fill in fills:
        order = next(o for o in plan.orders if o.ticker == fill.ticker)
        assert fill.price > order.reference_price

    journal = cfg.path(cfg.execution.journal_file)
    entries = [json.loads(line) for line in journal.read_text().splitlines()]
    assert len(entries) == len(fills)
    assert all(e["status"] == "filled" for e in entries)


def test_gesamtwert_bleibt_bis_auf_kosten_erhalten(panel: PriceData, cfg, tmp_path):
    cfg = load_config(write_config(tmp_path, list(cfg.tickers)))
    state = fresh_state(cfg)
    plan = plan_rebalance(cfg, panel, state, force=True)
    execute_plan(cfg, plan, state, PaperBroker(state, cfg.execution))

    nach = state.equity(panel.close.iloc[-1])
    # Slippage und Kommission kosten wenige Basispunkte, mehr darf es nicht sein.
    assert nach == pytest.approx(plan.equity, rel=0.002)
    assert nach < plan.equity


def test_fehlgeschlagene_order_stoppt_den_lauf_nicht(panel: PriceData, cfg, tmp_path):
    cfg = load_config(write_config(tmp_path, list(cfg.tickers)))
    state = fresh_state(cfg)
    plan = plan_rebalance(cfg, panel, state, force=True)

    class HalbKaputterBroker(PaperBroker):
        def submit(self, order: Order):
            if order.ticker == plan.orders[0].ticker:
                raise BrokerError("Simulierte Ablehnung")
            return super().submit(order)

    fills = execute_plan(cfg, plan, state, HalbKaputterBroker(state, cfg.execution))

    assert len(fills) == len(plan.orders) - 1
    entries = [
        json.loads(line)
        for line in cfg.path(cfg.execution.journal_file).read_text().splitlines()
    ]
    fehler = [e for e in entries if e["status"] == "error"]
    assert len(fehler) == 1
    assert "Simulierte Ablehnung" in fehler[0]["error"]


def test_zweiter_lauf_rotiert_statt_neu_zu_kaufen(panel: PriceData, cfg, tmp_path):
    cfg = load_config(write_config(tmp_path, list(cfg.tickers)))
    state = fresh_state(cfg)

    erster = plan_rebalance(cfg, panel, state, asof=panel.close.index[-300], force=True)
    execute_plan(cfg, erster, state, PaperBroker(state, cfg.execution))
    bestand = set(state.positions)

    zweiter = plan_rebalance(cfg, panel, state, force=True)
    # Der Bestandsschutz haelt die Auswahl weitgehend stabil.
    assert set(zweiter.selected) & bestand
    assert zweiter.turnover < 1.0
    assert zweiter.current_weights


def test_mark_to_market_schreibt_die_equity_kurve(panel: PriceData, cfg):
    state = fresh_state(cfg)
    equity = mark_to_market(state, panel)
    assert equity == pytest.approx(cfg.execution.starting_cash)
    assert len(state.equity_history) == 1
    assert state.equity_curve() is not None


def test_reports_lassen_sich_rendern(panel: PriceData, cfg):
    plan = plan_rebalance(cfg, panel, fresh_state(cfg), force=True)
    text = render_plan(plan)
    assert "Rebalancing-Plan" in text
    assert "Zielgewichte" in text
    assert "T00" in text

    markdown = plan_to_markdown(plan)
    assert markdown.startswith("## Tech-Rotation")
    assert "| Ticker |" in markdown


def test_local_csv_provider_und_cache(panel: PriceData, cfg, tmp_path):
    cfg = load_config(write_config(tmp_path, list(cfg.tickers)))
    local = cfg.path("data/local")
    local.mkdir(parents=True)
    panel.close.to_csv(local / "close.csv")
    panel.volume.to_csv(local / "volume.csv")

    geladen = load_prices(cfg, refresh=True)
    assert list(geladen.close.columns) == list(cfg.tickers) + [cfg.benchmark]
    assert len(geladen.close) > 0
    assert (cfg.path(cfg.data.cache_dir) / "meta.json").exists()

    meta = json.loads((cfg.path(cfg.data.cache_dir) / "meta.json").read_text())
    assert meta["provider"] == "local_csv"
    assert meta["rows"] == len(geladen.close)


def test_up_to_schneidet_beide_frames(panel: PriceData):
    asof = panel.close.index[100]
    gekuerzt = panel.up_to(asof)
    assert gekuerzt.close.index[-1] == asof
    assert gekuerzt.volume.index[-1] == asof
    assert len(gekuerzt.close) == len(gekuerzt.volume) == 101
