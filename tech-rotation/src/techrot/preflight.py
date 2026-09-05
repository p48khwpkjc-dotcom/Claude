"""Startbereitschaft pruefen, bevor zum ersten Mal echtes Geld bewegt wird.

Die Pruefungen laufen in der Reihenfolge, in der sie im Betrieb auch greifen:
Konfiguration, Daten, Universum, Benchmark, Schreibrechte, Zustand, Broker.
Jede liefert eine eigene Bewertung, damit ein einzelner Warnhinweis nicht den
ganzen Bericht rot faerbt.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd

from .brokers import LIVE_CONFIRMATION, BrokerError, build_broker
from .config import Config
from .data import DataError, PriceData, check_data_quality, load_prices
from .execution import plan_rebalance
from .state import PortfolioState

OK = "ok"
WARN = "warn"
FAIL = "fail"


@dataclass(frozen=True)
class Check:
    """Ergebnis einer einzelnen Pruefung."""

    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class Preflight:
    checks: list[Check]
    plan_summary: str | None

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status == FAIL]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.status == WARN]

    @property
    def ready(self) -> bool:
        return not self.failures

    @property
    def exit_code(self) -> int:
        if self.failures:
            return 2
        return 1 if self.warnings else 0


def _check_writable(cfg: Config) -> Check:
    """Zustand und Journal muessen schreibbar sein, sonst geht der Lauf
    verloren, nachdem die Orders schon draussen sind."""
    problems = []
    for label, relative in (
        ("Zustand", cfg.execution.state_file),
        ("Journal", cfg.execution.journal_file),
    ):
        path = cfg.path(relative)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            probe = path.parent / f".techrot-probe-{os.getpid()}"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            problems.append(f"{label} ({path}): {exc}")

    if problems:
        return Check("Schreibrechte", FAIL, "; ".join(problems))
    return Check("Schreibrechte", OK, "Zustand und Journal sind schreibbar")


def _check_universe(cfg: Config, prices: PriceData) -> list[Check]:
    quality = check_data_quality(prices, list(cfg.tickers), cfg.data, prices.last_date)
    healthy = [t for t, q in quality.items() if q.ok]
    broken = {t: q.reason for t, q in quality.items() if not q.ok}

    checks: list[Check] = []
    if len(healthy) < cfg.selection.top_n:
        checks.append(
            Check(
                "Universum",
                FAIL,
                f"nur {len(healthy)} von {len(cfg.tickers)} Tickern brauchbar, "
                f"top_n verlangt {cfg.selection.top_n}",
            )
        )
    elif broken:
        vorschau = ", ".join(f"{t} ({r})" for t, r in list(broken.items())[:3])
        checks.append(
            Check(
                "Universum",
                WARN,
                f"{len(healthy)} von {len(cfg.tickers)} Tickern brauchbar. "
                f"Ausgefallen: {vorschau}"
                + (" ..." if len(broken) > 3 else ""),
            )
        )
    else:
        checks.append(
            Check("Universum", OK, f"alle {len(cfg.tickers)} Ticker liefern saubere Reihen")
        )
    return checks


def _check_benchmark(cfg: Config, prices: PriceData) -> Check:
    needed = cfg.risk.portfolio.regime_sma
    if needed <= 0:
        return Check("Benchmark", WARN, "Regime-Filter ist abgeschaltet (regime_sma: 0)")

    if cfg.benchmark not in prices.close.columns:
        return Check(
            "Benchmark",
            FAIL,
            f"{cfg.benchmark} fehlt in den Kursdaten -- der Regime-Filter greift nie",
        )

    series = prices.close[cfg.benchmark].dropna()
    if len(series) < needed:
        return Check(
            "Benchmark",
            FAIL,
            f"{cfg.benchmark} hat nur {len(series)} Tage, SMA{needed} braucht mehr",
        )

    ueber = float(series.iloc[-1]) > float(series.tail(needed).mean())
    lage = "ueber" if ueber else "UNTER"
    status = OK if ueber else WARN
    hinweis = "" if ueber else " -- der erste Lauf ginge komplett in Cash"
    return Check(
        "Benchmark",
        status,
        f"{cfg.benchmark} liegt {lage} der SMA{needed}{hinweis}",
    )


def _check_state(cfg: Config, state: PortfolioState) -> Check:
    path = cfg.path(cfg.execution.state_file)
    if not path.exists():
        return Check(
            "Zustand",
            OK,
            f"noch keine Zustandsdatei -- der erste Lauf startet mit "
            f"{cfg.execution.starting_cash:,.2f} {cfg.base_currency}",
        )

    if state.last_rebalance:
        return Check(
            "Zustand",
            WARN,
            f"Depot laeuft bereits: {len(state.positions)} Positionen, letztes "
            f"Rebalancing {state.last_rebalance}",
        )
    return Check("Zustand", OK, f"Zustandsdatei vorhanden, Cash {state.cash:,.2f}")


def _check_broker(cfg: Config, state: PortfolioState) -> list[Check]:
    checks: list[Check] = []

    if cfg.execution.broker == "paper":
        checks.append(
            Check(
                "Broker",
                OK,
                "Paper-Broker: Fills werden simuliert, es fliesst kein echtes Geld",
            )
        )
        return checks

    freigabe = os.environ.get("TECHROT_ALLOW_LIVE") == LIVE_CONFIRMATION
    if cfg.execution.mode == "live":
        checks.append(
            Check(
                "Handelsmodus",
                WARN if freigabe else FAIL,
                "LIVE -- es wird echtes Geld bewegt"
                if freigabe
                else f"mode: live, aber TECHROT_ALLOW_LIVE={LIVE_CONFIRMATION} fehlt",
            )
        )
    else:
        checks.append(
            Check("Handelsmodus", OK, f"{cfg.execution.broker} gegen den Paper-Endpunkt")
        )

    try:
        broker = build_broker(cfg.execution, state)
    except BrokerError as exc:
        checks.append(Check("Brokerzugang", FAIL, str(exc)))
        return checks

    try:
        konto = broker.account()  # type: ignore[attr-defined]
        positionen = broker.positions()
    except BrokerError as exc:
        checks.append(Check("Brokerzugang", FAIL, f"Konto nicht abrufbar: {exc}"))
        return checks
    finally:
        close = getattr(broker, "close", None)
        if callable(close):
            close()

    checks.append(
        Check(
            "Brokerzugang",
            OK,
            f"Konto erreichbar: Depotwert {konto['equity']:,.2f}, "
            f"Cash {konto['cash']:,.2f}, {len(positionen)} Positionen",
        )
    )
    return checks


def run_preflight(
    cfg: Config,
    state: PortfolioState,
    *,
    prices: PriceData | None = None,
    refresh: bool = True,
) -> Preflight:
    """Prueft der Reihe nach alles, was der erste Lauf braucht."""
    checks: list[Check] = [
        Check("Konfiguration", OK, f"{cfg.name}: {len(cfg.tickers)} Ticker, "
              f"top_n={cfg.selection.top_n}, Benchmark {cfg.benchmark}")
    ]

    if prices is None:
        try:
            prices = load_prices(cfg, refresh=refresh)
        except DataError as exc:
            checks.append(Check("Kursdaten", FAIL, str(exc)))
            checks.append(_check_writable(cfg))
            return Preflight(checks, None)

    alter = (pd.Timestamp.today().normalize() - prices.last_date).days
    if alter > cfg.data.max_staleness_days:
        checks.append(
            Check(
                "Kursdaten",
                FAIL,
                f"letzter Kurs vom {prices.last_date.date()} ist {alter} Tage alt "
                f"(Limit {cfg.data.max_staleness_days})",
            )
        )
    else:
        checks.append(
            Check(
                "Kursdaten",
                OK,
                f"{len(prices.close)} Handelstage bis {prices.last_date.date()} "
                f"({cfg.data.provider})",
            )
        )

    checks.extend(_check_universe(cfg, prices))
    checks.append(_check_benchmark(cfg, prices))
    checks.append(_check_writable(cfg))
    checks.append(_check_state(cfg, state))
    checks.extend(_check_broker(cfg, state))

    # Zum Schluss der Probelauf: was wuerde der erste echte Lauf tun?
    plan_summary = None
    try:
        plan = plan_rebalance(cfg, prices, state, force=True)
        notional = sum(o.notional for o in plan.orders)
        plan_summary = (
            f"{len(plan.orders)} Orders ueber {notional:,.2f} {cfg.base_currency}, "
            f"Zielexposure {sum(plan.target_weights.values()):.1%}, "
            f"Titel: {', '.join(plan.selected) or 'keine'}"
        )
        checks.append(Check("Probelauf", OK, plan_summary))
    except (ValueError, DataError) as exc:
        checks.append(Check("Probelauf", FAIL, f"Plan nicht berechenbar: {exc}"))

    return Preflight(checks, plan_summary)


def render_preflight(result: Preflight) -> str:
    """Bericht fuer die Konsole."""
    symbol = {OK: "  ok  ", WARN: " warn ", FAIL: " FAIL "}
    lines = ["# Startbereitschaft", ""]
    for check in result.checks:
        lines.append(f"[{symbol[check.status]}] {check.name:<14} {check.detail}")

    lines.append("")
    if result.failures:
        lines.append(
            f"NICHT startbereit: {len(result.failures)} Pruefung(en) fehlgeschlagen."
        )
    elif result.warnings:
        lines.append(
            f"Startbereit mit {len(result.warnings)} Hinweis(en) -- bitte oben lesen."
        )
    else:
        lines.append("Startbereit.")
    return "\n".join(lines)
