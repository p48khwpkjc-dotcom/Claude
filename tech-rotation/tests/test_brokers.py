"""Broker-Anbindung, vor allem die Sicherungen gegen ungewollten Live-Handel.

Der Alpaca-Pfad wird gegen einen httpx-MockTransport gefahren: echte
Client-Konstruktion, echte Header, echtes Fehlerverhalten -- nur die
Gegenstelle ist simuliert. Es geht nie eine Anfrage ins Netz.
"""

from __future__ import annotations

import json

import httpx
import pytest

from techrot.brokers import (
    LIVE_CONFIRMATION,
    AlpacaBroker,
    BrokerError,
    PaperBroker,
    build_broker,
)
from techrot.config import ExecutionConfig
from techrot.portfolio import Order
from techrot.state import PortfolioState

PAPER_CFG = ExecutionConfig(broker="paper", mode="paper", slippage_bps=10, commission_bps=2)
ALPACA_PAPER = ExecutionConfig(broker="alpaca", mode="paper")
ALPACA_LIVE = ExecutionConfig(broker="alpaca", mode="live")


@pytest.fixture
def alpaca_keys(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY_ID", "test-key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "test-secret")
    monkeypatch.delenv("TECHROT_ALLOW_LIVE", raising=False)


def recording_transport(responses: dict[str, object]) -> tuple[httpx.MockTransport, list]:
    """Transport, der feste Antworten liefert und alle Anfragen mitschreibt."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        key = f"{request.method} {request.url.path}"
        if key not in responses:
            return httpx.Response(404, json={"message": f"kein Stub fuer {key}"})
        payload = responses[key]
        if isinstance(payload, int):
            return httpx.Response(payload, json={"message": "abgelehnt"})
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler), seen


# --------------------------------------------------------------------------
# Paper-Broker
# --------------------------------------------------------------------------


def test_slippage_wirkt_gegen_den_auftraggeber():
    state = PortfolioState(cash=100_000.0)
    broker = PaperBroker(state, PAPER_CFG)

    kauf = broker.submit(Order("AAPL", "buy", 10, 100.0))
    verkauf = broker.submit(Order("MSFT", "sell", -10, 100.0))

    assert kauf.price == pytest.approx(100.0 * 1.001)
    assert verkauf.price == pytest.approx(100.0 * 0.999)


def test_paper_broker_bucht_cash_und_kommission():
    state = PortfolioState(cash=100_000.0)
    broker = PaperBroker(state, PAPER_CFG)
    fill = broker.submit(Order("AAPL", "buy", 10, 100.0))

    erwartete_kommission = 10 * fill.price * 2 / 10_000
    assert fill.cost == pytest.approx(erwartete_kommission)
    assert state.positions == {"AAPL": 10.0}
    assert state.cash == pytest.approx(100_000 - 10 * fill.price - erwartete_kommission)


def test_paper_sync_laesst_den_zustand_unberuehrt():
    state = PortfolioState(cash=500.0, positions={"AAPL": 3.0})
    PaperBroker(state, PAPER_CFG).sync(state)
    assert state.cash == 500.0
    assert state.positions == {"AAPL": 3.0}


# --------------------------------------------------------------------------
# Live-Verriegelung
# --------------------------------------------------------------------------


def test_ohne_zugangsdaten_kein_alpaca(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    with pytest.raises(BrokerError, match="ALPACA_API_KEY_ID"):
        AlpacaBroker(ALPACA_PAPER)


def test_live_ohne_freigabe_wird_verweigert(alpaca_keys):
    with pytest.raises(BrokerError, match="nicht freigegeben"):
        AlpacaBroker(ALPACA_LIVE)


def test_falsche_freigabe_zaehlt_nicht(alpaca_keys, monkeypatch):
    monkeypatch.setenv("TECHROT_ALLOW_LIVE", "ja")
    with pytest.raises(BrokerError, match="nicht freigegeben"):
        AlpacaBroker(ALPACA_LIVE)


def test_live_braucht_beides(alpaca_keys, monkeypatch):
    monkeypatch.setenv("TECHROT_ALLOW_LIVE", LIVE_CONFIRMATION)
    transport, _ = recording_transport({})

    # Freigabe allein schaltet nicht live -- die Konfiguration entscheidet mit.
    papier = AlpacaBroker(ALPACA_PAPER, transport=transport)
    assert papier.live is False
    assert str(papier._client.base_url).startswith(AlpacaBroker.PAPER_URL)

    live = AlpacaBroker(ALPACA_LIVE, transport=transport)
    assert live.live is True
    assert str(live._client.base_url).startswith(AlpacaBroker.LIVE_URL)


def test_paper_ist_der_standard_endpunkt(alpaca_keys):
    transport, _ = recording_transport({})
    broker = AlpacaBroker(ALPACA_PAPER, transport=transport)
    assert broker.live is False
    assert "paper-api" in str(broker._client.base_url)


# --------------------------------------------------------------------------
# Alpaca-REST
# --------------------------------------------------------------------------


def test_zugangsdaten_wandern_in_die_header(alpaca_keys):
    transport, seen = recording_transport({"GET /v2/positions": []})
    AlpacaBroker(ALPACA_PAPER, transport=transport).positions()

    assert seen[0].headers["APCA-API-KEY-ID"] == "test-key"
    assert seen[0].headers["APCA-API-SECRET-KEY"] == "test-secret"


def test_positionen_werden_gelesen(alpaca_keys):
    transport, _ = recording_transport(
        {"GET /v2/positions": [{"symbol": "AAPL", "qty": "12"}, {"symbol": "MSFT", "qty": "-3"}]}
    )
    positionen = AlpacaBroker(ALPACA_PAPER, transport=transport).positions()
    assert positionen == {"AAPL": 12.0, "MSFT": -3.0}


def test_sync_uebernimmt_positionen_und_cash(alpaca_keys):
    transport, _ = recording_transport(
        {
            "GET /v2/positions": [{"symbol": "NVDA", "qty": "5"}],
            "GET /v2/account": {"equity": "51000.00", "cash": "1000.50"},
        }
    )
    # Der lokale Zustand ist absichtlich falsch -- der Broker muss ihn ueberschreiben.
    state = PortfolioState(cash=99_999.0, positions={"VERALTET": 42.0})
    AlpacaBroker(ALPACA_PAPER, transport=transport).sync(state)

    assert state.positions == {"NVDA": 5.0}
    assert state.cash == pytest.approx(1000.50)


def test_order_wird_als_marktorder_geschickt(alpaca_keys):
    transport, seen = recording_transport(
        {
            "POST /v2/orders": {
                "id": "abc-123",
                "status": "filled",
                "filled_avg_price": "101.25",
            }
        }
    )
    broker = AlpacaBroker(ALPACA_PAPER, transport=transport)
    fill = broker.submit(Order("AAPL", "buy", 10, 100.0))

    payload = json.loads(seen[0].content)
    assert payload == {
        "symbol": "AAPL",
        "qty": "10",
        "side": "buy",
        "type": "market",
        "time_in_force": "day",
    }
    assert fill.price == pytest.approx(101.25)
    assert fill.broker_order_id == "abc-123"
    assert fill.status == "filled"


def test_verkauf_schickt_positive_menge(alpaca_keys):
    transport, seen = recording_transport(
        {"POST /v2/orders": {"id": "x", "status": "accepted", "filled_avg_price": None}}
    )
    broker = AlpacaBroker(ALPACA_PAPER, transport=transport)
    fill = broker.submit(Order("AAPL", "sell", -7, 100.0))

    payload = json.loads(seen[0].content)
    assert payload["qty"] == "7"
    assert payload["side"] == "sell"
    # Die Menge im Fill bleibt vorzeichenbehaftet fuer die Buchhaltung.
    assert fill.quantity == -7


def test_noch_nicht_ausgefuehrte_order_faellt_auf_den_referenzkurs_zurueck(alpaca_keys):
    transport, _ = recording_transport(
        {"POST /v2/orders": {"id": "y", "status": "accepted", "filled_avg_price": None}}
    )
    broker = AlpacaBroker(ALPACA_PAPER, transport=transport)
    fill = broker.submit(Order("AAPL", "buy", 4, 250.0))

    assert fill.status == "accepted"
    assert fill.price == pytest.approx(250.0)


def test_abgelehnte_order_wird_zu_brokererror(alpaca_keys):
    transport, _ = recording_transport({"POST /v2/orders": 403})
    broker = AlpacaBroker(ALPACA_PAPER, transport=transport)
    with pytest.raises(BrokerError, match="HTTP 403"):
        broker.submit(Order("AAPL", "buy", 1, 100.0))


def test_netzfehler_wird_zu_brokererror(alpaca_keys):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Verbindung abgelehnt")

    broker = AlpacaBroker(ALPACA_PAPER, transport=httpx.MockTransport(handler))
    with pytest.raises(BrokerError, match="nicht erreichbar"):
        broker.positions()


def test_fehlermeldung_enthaelt_keine_zugangsdaten(alpaca_keys):
    transport, _ = recording_transport({"POST /v2/orders": 401})
    broker = AlpacaBroker(ALPACA_PAPER, transport=transport)
    with pytest.raises(BrokerError) as exc:
        broker.submit(Order("AAPL", "buy", 1, 100.0))
    assert "test-key" not in str(exc.value)
    assert "test-secret" not in str(exc.value)


def test_broker_schliesst_sich_als_kontextmanager(alpaca_keys):
    transport, _ = recording_transport({"GET /v2/positions": []})
    with AlpacaBroker(ALPACA_PAPER, transport=transport) as broker:
        broker.positions()
    assert broker._client.is_closed


# --------------------------------------------------------------------------
# Fabrik
# --------------------------------------------------------------------------


def test_build_broker_liefert_den_konfigurierten_typ():
    state = PortfolioState(cash=1000.0)
    assert build_broker(PAPER_CFG, state).name == "paper"


def test_build_broker_kennt_nur_bekannte_namen():
    state = PortfolioState(cash=1000.0)
    kaputt = ExecutionConfig.__new__(ExecutionConfig)
    object.__setattr__(kaputt, "broker", "phantasiebroker")
    with pytest.raises(BrokerError, match="Unbekannter Broker"):
        build_broker(kaputt, state)
