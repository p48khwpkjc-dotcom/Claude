"""Persistenter Portfoliozustand.

Der Zustand ist die einzige Quelle der Wahrheit zwischen zwei Laeufen: welche
Positionen gehalten werden, wie viel Cash da ist, wann zuletzt rebalanciert
wurde und wie die Equity-Kurve verlaufen ist. Die Drawdown-Bremse liest
daraus.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

STATE_VERSION = 1


@dataclass
class EquityPoint:
    date: str
    equity: float


@dataclass
class PortfolioState:
    cash: float
    positions: dict[str, float] = field(default_factory=dict)
    equity_history: list[EquityPoint] = field(default_factory=list)
    last_rebalance: str | None = None
    version: int = STATE_VERSION

    # -- Persistenz -------------------------------------------------------

    @classmethod
    def load(cls, path: Path, starting_cash: float) -> PortfolioState:
        """Liest den Zustand; legt bei fehlender Datei ein frisches Depot an."""
        if not path.exists():
            return cls(cash=starting_cash)

        raw = json.loads(path.read_text(encoding="utf-8"))
        version = raw.get("version", 1)
        if version > STATE_VERSION:
            raise ValueError(
                f"Zustandsdatei hat Version {version}, dieser Code kennt nur "
                f"{STATE_VERSION}. Bitte techrot aktualisieren."
            )
        return cls(
            cash=float(raw.get("cash", starting_cash)),
            positions={k: float(v) for k, v in raw.get("positions", {}).items() if v},
            equity_history=[EquityPoint(**p) for p in raw.get("equity_history", [])],
            last_rebalance=raw.get("last_rebalance"),
            version=STATE_VERSION,
        )

    def save(self, path: Path) -> None:
        """Schreibt atomar, damit ein Abbruch keine halbe Datei hinterlaesst."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(asdict(self), indent=2, sort_keys=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload + "\n")
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    # -- Bewertung --------------------------------------------------------

    def market_value(self, prices: pd.Series) -> float:
        total = 0.0
        for ticker, shares in self.positions.items():
            price = prices.get(ticker)
            if price is not None and pd.notna(price):
                total += float(shares) * float(price)
        return total

    def equity(self, prices: pd.Series) -> float:
        return self.cash + self.market_value(prices)

    def record_equity(self, on: date, value: float) -> None:
        """Haengt einen Equity-Punkt an; ersetzt den Eintrag desselben Tages."""
        stamp = on.isoformat()
        self.equity_history = [p for p in self.equity_history if p.date != stamp]
        self.equity_history.append(EquityPoint(date=stamp, equity=float(value)))
        self.equity_history.sort(key=lambda p: p.date)

    def equity_curve(self) -> pd.Series | None:
        if not self.equity_history:
            return None
        return pd.Series(
            [p.equity for p in self.equity_history],
            index=pd.to_datetime([p.date for p in self.equity_history]),
            dtype="float64",
        )

    def apply_fill(self, ticker: str, quantity: float, price: float, cost: float) -> None:
        """Bucht eine Ausfuehrung in Positionen und Cash."""
        new_qty = self.positions.get(ticker, 0.0) + quantity
        if abs(new_qty) < 1e-9:
            self.positions.pop(ticker, None)
        else:
            self.positions[ticker] = new_qty
        self.cash -= quantity * price + cost


def is_rebalance_due(state: PortfolioState, today: date) -> bool:
    """Faellig, sobald der Kalendermonat des letzten Laufs vorbei ist.

    So bleibt der Zeitplan robust: ein Feiertag, ein ausgefallener Job oder
    ein spaeterer Start verschieben den Termin nur, sie ueberspringen ihn nicht.
    """
    if state.last_rebalance is None:
        return True
    last = date.fromisoformat(state.last_rebalance)
    return (today.year, today.month) > (last.year, last.month)
