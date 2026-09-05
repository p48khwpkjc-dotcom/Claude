"""Broker-Anbindung.

Zwei Implementierungen hinter einer Schnittstelle:

* ``PaperBroker``  -- simuliert Fills gegen den lokalen Zustand. Standard.
* ``AlpacaBroker`` -- echte Orders ueber die Alpaca-REST-API.

Der Live-Modus ist bewusst schwer zu erreichen: er verlangt gleichzeitig
``execution.mode: live`` in der Konfiguration und die Umgebungsvariable
``TECHROT_ALLOW_LIVE=I_UNDERSTAND``. Eine vergessene Config-Zeile allein
loest damit keinen echten Handel aus.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from .config import ExecutionConfig
from .portfolio import Order
from .state import PortfolioState

LIVE_CONFIRMATION = "I_UNDERSTAND"


class BrokerError(RuntimeError):
    """Der Broker hat die Order abgelehnt oder ist nicht erreichbar."""


@dataclass(frozen=True)
class Fill:
    """Bestaetigte oder simulierte Ausfuehrung."""

    ticker: str
    side: str
    quantity: float
    price: float
    cost: float
    broker_order_id: str | None = None
    status: str = "filled"

    @property
    def notional(self) -> float:
        return abs(self.quantity) * self.price


class Broker(Protocol):
    name: str

    def positions(self) -> dict[str, float]: ...

    def submit(self, order: Order) -> Fill: ...

    def sync(self, state: PortfolioState) -> None:
        """Uebernimmt den Kontostand des Brokers in den lokalen Zustand."""
        ...


class PaperBroker:
    """Simuliert Ausfuehrungen mit Slippage- und Gebuehrenmodell.

    Slippage wirkt immer gegen den Auftraggeber: Kaeufe fuellen ueber, Verkaeufe
    unter dem Referenzkurs. Damit ist das Papierergebnis eher zu pessimistisch
    als zu optimistisch.
    """

    name = "paper"

    def __init__(self, state: PortfolioState, cfg: ExecutionConfig) -> None:
        self.state = state
        self.slippage_bps = cfg.slippage_bps
        self.commission_bps = cfg.commission_bps

    def positions(self) -> dict[str, float]:
        return dict(self.state.positions)

    def sync(self, state: PortfolioState) -> None:
        """Nichts zu tun: der Paper-Broker bucht direkt in den Zustand."""

    def submit(self, order: Order) -> Fill:
        direction = 1.0 if order.quantity > 0 else -1.0
        fill_price = order.reference_price * (1 + direction * self.slippage_bps / 10_000)
        commission = abs(order.quantity) * fill_price * self.commission_bps / 10_000
        self.state.apply_fill(order.ticker, order.quantity, fill_price, commission)
        return Fill(
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            cost=commission,
            status="filled",
        )


class AlpacaBroker:
    """Marktorders ueber die Alpaca-REST-API.

    Erwartet ``ALPACA_API_KEY_ID`` und ``ALPACA_API_SECRET_KEY``. Der
    Paper-Endpunkt ist der Standard; auf den Live-Endpunkt schaltet nur die
    ausdrueckliche Freigabe um.
    """

    name = "alpaca"

    PAPER_URL = "https://paper-api.alpaca.markets"
    LIVE_URL = "https://api.alpaca.markets"

    def __init__(self, cfg: ExecutionConfig, transport: object | None = None) -> None:
        import httpx

        key = os.environ.get("ALPACA_API_KEY_ID")
        secret = os.environ.get("ALPACA_API_SECRET_KEY")
        if not key or not secret:
            raise BrokerError(
                "ALPACA_API_KEY_ID und ALPACA_API_SECRET_KEY muessen gesetzt sein"
            )

        self.live = cfg.mode == "live"
        if self.live and os.environ.get("TECHROT_ALLOW_LIVE") != LIVE_CONFIRMATION:
            raise BrokerError(
                "Live-Handel ist konfiguriert, aber nicht freigegeben. "
                f"Zum Bestaetigen TECHROT_ALLOW_LIVE={LIVE_CONFIRMATION} setzen."
            )

        base_url = self.LIVE_URL if self.live else self.PAPER_URL
        self._client = httpx.Client(
            base_url=base_url,
            timeout=30.0,
            headers={
                "APCA-API-KEY-ID": key,
                "APCA-API-SECRET-KEY": secret,
                "accept": "application/json",
            },
            # Nur Tests reichen hier einen Transport herein; im Betrieb bleibt
            # es der echte HTTP-Stack.
            transport=transport,  # type: ignore[arg-type]
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> AlpacaBroker:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: object) -> object:
        import httpx

        try:
            resp = self._client.request(method, path, **kwargs)  # type: ignore[arg-type]
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Der Body enthaelt Alpacas Ablehnungsgrund, aber keine Zugangsdaten.
            raise BrokerError(
                f"Alpaca {method} {path} -> HTTP {exc.response.status_code}: "
                f"{exc.response.text[:300]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise BrokerError(f"Alpaca {method} {path} nicht erreichbar: {exc}") from exc
        return resp.json()

    def account(self) -> dict[str, float]:
        """Kontostand: Depotwert und freies Guthaben."""
        data = self._request("GET", "/v2/account")
        return {
            "equity": float(data["equity"]),  # type: ignore[index,call-overload]
            "cash": float(data["cash"]),  # type: ignore[index,call-overload]
        }

    def positions(self) -> dict[str, float]:
        data = self._request("GET", "/v2/positions")
        return {p["symbol"]: float(p["qty"]) for p in data}  # type: ignore[union-attr]

    def sync(self, state: PortfolioState) -> None:
        """Uebernimmt Positionen UND Cash vom Broker.

        Beides gehoert zusammen: mit gesyncten Positionen, aber lokal
        fortgeschriebenem Cash waere der Depotwert falsch -- und damit jede
        Ordergroesse, die Drawdown-Bremse und das Vol-Targeting.
        """
        state.positions = self.positions()
        state.cash = self.account()["cash"]

    def submit(self, order: Order) -> Fill:
        quantity = abs(order.quantity)
        payload = {
            "symbol": order.ticker,
            "qty": str(int(quantity)) if quantity >= 1 else str(quantity),
            "side": order.side,
            "type": "market",
            "time_in_force": "day",
        }
        data = self._request("POST", "/v2/orders", json=payload)
        filled_price = data.get("filled_avg_price")  # type: ignore[union-attr]
        return Fill(
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            price=float(filled_price) if filled_price else order.reference_price,
            cost=0.0,
            broker_order_id=str(data.get("id")),  # type: ignore[union-attr]
            # Marktorders vor der Eroeffnung sind zunaechst "accepted"; der Fill
            # kommt beim naechsten Lauf ueber die Positionsabfrage zurueck.
            status=str(data.get("status", "accepted")),  # type: ignore[union-attr]
        )


def build_broker(cfg: ExecutionConfig, state: PortfolioState) -> Broker:
    match cfg.broker:
        case "paper":
            return PaperBroker(state, cfg)
        case "alpaca":
            return AlpacaBroker(cfg)
        case other:
            raise BrokerError(f"Unbekannter Broker: {other}")
