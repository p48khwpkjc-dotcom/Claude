"""Laden und Validieren der Strategie-Konfiguration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Die Konfiguration ist unvollstaendig oder in sich widerspruechlich."""


@dataclass(frozen=True)
class Lookback:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start <= self.end:
            raise ConfigError(
                f"Lookback start ({self.start}) muss groesser als end ({self.end}) sein"
            )
        if self.end < 0:
            raise ConfigError(f"Lookback end ({self.end}) darf nicht negativ sein")


@dataclass(frozen=True)
class DataConfig:
    provider: str = "yfinance"
    cache_dir: str = "data/cache"
    cache_ttl_hours: float = 12.0
    history_years: int = 8
    min_history_days: int = 300
    max_staleness_days: int = 5
    max_missing_ratio: float = 0.02


@dataclass(frozen=True)
class RankingConfig:
    lookbacks: dict[str, Lookback]
    vol_window: int = 63
    weights: dict[str, float] = field(default_factory=dict)
    winsorize_z: float = 3.0

    def normalized_weights(self) -> dict[str, float]:
        total = sum(abs(w) for w in self.weights.values())
        if total == 0:
            raise ConfigError("ranking.weights summieren sich auf 0")
        return {k: v / total for k, v in self.weights.items()}


@dataclass(frozen=True)
class SelectionConfig:
    top_n: int = 8
    buffer_rank: int = 12
    weighting: str = "inverse_vol"

    def __post_init__(self) -> None:
        if self.top_n < 1:
            raise ConfigError("selection.top_n muss mindestens 1 sein")
        if self.buffer_rank < self.top_n:
            raise ConfigError("selection.buffer_rank muss >= top_n sein")
        if self.weighting not in {"equal", "inverse_vol"}:
            raise ConfigError(f"Unbekannte Gewichtung: {self.weighting}")


@dataclass(frozen=True)
class EligibilityConfig:
    min_avg_dollar_volume: float = 50_000_000
    adv_window: int = 20
    max_annual_vol: float = 0.90
    require_positive_absolute_momentum: bool = True
    require_above_sma: int = 200


@dataclass(frozen=True)
class PortfolioRiskConfig:
    max_position_weight: float = 0.20
    max_gross_exposure: float = 1.00
    min_names: int = 4
    regime_sma: int = 200
    regime_exposure: float = 0.0
    vol_target: float = 0.18
    vol_lookback: int = 63
    max_vol_scalar: float = 1.0
    max_drawdown_brake: float = 0.20
    drawdown_exposure_floor: float = 0.30
    max_turnover_per_rebalance: float = 0.60

    def __post_init__(self) -> None:
        if not 0 < self.max_position_weight <= 1:
            raise ConfigError("max_position_weight muss in (0, 1] liegen")
        if self.min_names < 1:
            raise ConfigError("min_names muss mindestens 1 sein")
        if not 0 <= self.drawdown_exposure_floor <= 1:
            raise ConfigError("drawdown_exposure_floor muss in [0, 1] liegen")


@dataclass(frozen=True)
class RiskConfig:
    eligibility: EligibilityConfig
    portfolio: PortfolioRiskConfig


@dataclass(frozen=True)
class ExecutionConfig:
    broker: str = "paper"
    mode: str = "paper"
    order_type: str = "market"
    min_order_notional: float = 250.0
    slippage_bps: float = 5.0
    commission_bps: float = 1.0
    starting_cash: float = 100_000.0
    state_file: str = "data/state.json"
    journal_file: str = "data/orders.jsonl"

    def __post_init__(self) -> None:
        if self.broker not in {"paper", "alpaca"}:
            raise ConfigError(f"Unbekannter Broker: {self.broker}")
        if self.mode not in {"paper", "live"}:
            raise ConfigError(f"Unbekannter Modus: {self.mode}")
        if self.broker == "paper" and self.mode == "live":
            raise ConfigError("Der Paper-Broker kann nicht im Live-Modus laufen")


@dataclass(frozen=True)
class BacktestConfig:
    start: str = "2019-01-01"
    end: str | None = None
    rebalance: str = "month_start"

    def __post_init__(self) -> None:
        if self.rebalance not in {"month_start", "month_end"}:
            raise ConfigError(f"Unbekannter Rebalance-Termin: {self.rebalance}")


@dataclass(frozen=True)
class Config:
    name: str
    base_currency: str
    benchmark: str
    tickers: tuple[str, ...]
    data: DataConfig
    ranking: RankingConfig
    selection: SelectionConfig
    risk: RiskConfig
    execution: ExecutionConfig
    backtest: BacktestConfig
    root: Path

    def path(self, relative: str) -> Path:
        """Loest einen Config-Pfad gegen das Projektverzeichnis auf."""
        p = Path(relative)
        return p if p.is_absolute() else self.root / p


def _subset(cls: type, raw: dict[str, Any], where: str) -> Any:
    """Baut eine Dataclass und meldet unbekannte Schluessel als Fehler."""
    known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    unknown = set(raw) - known
    if unknown:
        raise ConfigError(f"Unbekannte Schluessel in {where}: {sorted(unknown)}")
    return cls(**raw)


def load_config(path: str | Path) -> Config:
    """Liest config.yaml und validiert sie vollstaendig."""
    path = Path(path).resolve()
    if not path.exists():
        raise ConfigError(f"Konfiguration nicht gefunden: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    strategy = raw.get("strategy", {})
    tickers = tuple(dict.fromkeys(raw.get("universe", {}).get("tickers", [])))
    if not tickers:
        raise ConfigError("universe.tickers ist leer")

    ranking_raw = dict(raw.get("ranking", {}))
    lookbacks_raw = ranking_raw.pop("lookbacks", {})
    lookbacks = {k: Lookback(**v) for k, v in lookbacks_raw.items()}
    if not lookbacks:
        raise ConfigError("ranking.lookbacks ist leer")

    ranking = _subset(RankingConfig, {**ranking_raw, "lookbacks": lookbacks}, "ranking")

    weight_keys = set(ranking.weights)
    known_signals = set(lookbacks) | {"risk_adj_mom"}
    if not weight_keys <= known_signals:
        raise ConfigError(
            f"ranking.weights verweist auf unbekannte Signale: "
            f"{sorted(weight_keys - known_signals)}"
        )
    if "risk_adj_mom" in weight_keys and "mom_12_1" not in lookbacks:
        raise ConfigError("risk_adj_mom braucht einen Lookback namens mom_12_1")

    risk_raw = raw.get("risk", {})
    risk = RiskConfig(
        eligibility=_subset(
            EligibilityConfig, risk_raw.get("eligibility", {}), "risk.eligibility"
        ),
        portfolio=_subset(
            PortfolioRiskConfig, risk_raw.get("portfolio", {}), "risk.portfolio"
        ),
    )

    cfg = Config(
        name=strategy.get("name", "tech-rotation"),
        base_currency=strategy.get("base_currency", "USD"),
        benchmark=strategy.get("benchmark", "QQQ"),
        tickers=tickers,
        data=_subset(DataConfig, raw.get("data", {}), "data"),
        ranking=ranking,
        selection=_subset(SelectionConfig, raw.get("selection", {}), "selection"),
        risk=risk,
        execution=_subset(ExecutionConfig, raw.get("execution", {}), "execution"),
        backtest=_subset(BacktestConfig, raw.get("backtest", {}), "backtest"),
        root=path.parent,
    )

    longest = max(lb.start for lb in cfg.ranking.lookbacks.values())
    needed = max(longest, cfg.risk.eligibility.require_above_sma, cfg.ranking.vol_window)
    if cfg.data.min_history_days < needed:
        raise ConfigError(
            f"data.min_history_days ({cfg.data.min_history_days}) ist kleiner als der "
            f"laengste benoetigte Lookback ({needed} Handelstage)"
        )
    if cfg.selection.top_n > len(tickers):
        raise ConfigError(
            f"selection.top_n ({cfg.selection.top_n}) ist groesser als das Universum "
            f"({len(tickers)} Ticker)"
        )
    # Mit top_n Positionen und dem Einzelpositionslimit muss die volle
    # Zielexposure ueberhaupt erreichbar sein, sonst ist das Portfolio
    # strukturell unterinvestiert.
    reachable = cfg.selection.top_n * cfg.risk.portfolio.max_position_weight
    if reachable < cfg.risk.portfolio.max_gross_exposure - 1e-9:
        raise ConfigError(
            f"selection.top_n ({cfg.selection.top_n}) x max_position_weight "
            f"({cfg.risk.portfolio.max_position_weight}) = {reachable:.2f} erreicht "
            f"max_gross_exposure ({cfg.risk.portfolio.max_gross_exposure}) nicht"
        )
    return cfg
