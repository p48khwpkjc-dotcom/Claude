"""Typed configuration, loaded from YAML.

Every number that governs risk lives here rather than in strategy code, so a
strategy cannot quietly widen its own limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class AccountConfig:
    start_equity: float = 10_000.0
    quote_currency: str = "USDT"


@dataclass(slots=True)
class RiskConfig:
    risk_per_trade_pct: float = 0.5      # of current equity, per trade
    max_daily_loss_pct: float = 3.0      # kill switch, measured from day-start equity
    max_leverage: float = 1.0            # 1.0 = notional never exceeds equity
    max_concurrent_positions: int = 1
    max_trades_per_day: int = 5
    cooldown_after_losses: int = 3       # consecutive losers before a pause
    cooldown_bars: int = 12              # length of that pause
    max_hold_hours: float = 4.0          # crypto never closes, so time it out
    min_stop_distance_pct: float = 0.05  # reject stops tighter than this
    max_stop_distance_pct: float = 5.0   # and ones so wide the size is meaningless


@dataclass(slots=True)
class ExecutionConfig:
    taker_fee_pct: float = 0.05   # per side, Binance spot taker without discounts
    slippage_bps: float = 3.0     # applied against you on every fill
    stop_slippage_bps: float = 5.0  # stops fill worse; they are market orders in a rush

    # Scaling out. `partial_at_r` is measured in units of the initial risk, so
    # 1.5 means "take some off at 1.5 times the distance to the stop". Zero
    # switches the whole mechanism off, which is the default.
    #
    # This is an exit policy, not a strategy decision, which is why it lives
    # here: every strategy is measured under the same policy or none of the
    # comparison means anything.
    partial_at_r: float = 0.0
    partial_fraction: float = 0.5        # how much of the position comes off
    breakeven_after_partial: bool = False  # move the stop to entry afterwards

    # A multi-step exit plan, as a list of rungs climbed in order. Each rung is
    # {at_tp_frac, close_frac, stop_to_tp_frac}, measured as fractions of the
    # distance from entry to the target -- which is how these plans are
    # normally described ("at half way, stop to break even").
    #
    #   at_tp_frac      trigger, 0.5 = half way to the target
    #   close_frac      share of what is still open to sell there
    #   stop_to_tp_frac where the stop moves, 0.0 = entry, 0.5 = half way
    #                   (null leaves the stop alone)
    #
    # Rungs must be listed in ascending at_tp_frac. This supersedes the single
    # partial above when both are set.
    exit_ladder: list[dict] = field(default_factory=list)


@dataclass(slots=True)
class DataConfig:
    symbols: list[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    interval: str = "5m"
    htf_interval: str = "1h"
    history_days: int = 540
    cache_dir: str = "data/cache"
    source: str = "cache"
    synthetic_bars: int = 40_000


@dataclass(slots=True)
class BacktestConfig:
    train_split: float = 0.6   # in-sample fraction used to choose a strategy
    warmup_bars: int = 250
    out_dir: str = "out"


@dataclass(slots=True)
class Config:
    account: AccountConfig = field(default_factory=AccountConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    data: DataConfig = field(default_factory=DataConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    strategies: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def cache_dir(self) -> Path:
        return Path(self.data.cache_dir)

    @property
    def out_dir(self) -> Path:
        return Path(self.backtest.out_dir)


def _build(cls, raw: dict | None):
    if raw is None:
        return cls()
    known = {f.name for f in fields(cls)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"unknown keys in {cls.__name__.replace('Config','').lower()}: {sorted(unknown)}")
    return cls(**{k: v for k, v in raw.items() if k in known})


def load_config(path: str | Path = "config.yaml") -> Config:
    path = Path(path)
    raw: dict = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text()) or {}

    cfg = Config(
        account=_build(AccountConfig, raw.get("account")),
        risk=_build(RiskConfig, raw.get("risk")),
        execution=_build(ExecutionConfig, raw.get("execution")),
        data=_build(DataConfig, raw.get("data")),
        backtest=_build(BacktestConfig, raw.get("backtest")),
        strategies=raw.get("strategies") or {},
    )
    validate_config(cfg)
    return cfg


def validate_config(cfg: Config) -> None:
    r = cfg.risk
    if not 0 < r.risk_per_trade_pct <= 5:
        raise ValueError("risk.risk_per_trade_pct must be in (0, 5]")
    if not 0 < r.max_daily_loss_pct <= 50:
        raise ValueError("risk.max_daily_loss_pct must be in (0, 50]")
    if r.risk_per_trade_pct > r.max_daily_loss_pct:
        raise ValueError("a single trade may not risk more than the whole daily budget")
    if r.max_leverage < 1:
        raise ValueError("risk.max_leverage below 1 would forbid using your own capital")
    if cfg.account.start_equity <= 0:
        raise ValueError("account.start_equity must be positive")
    if not 0.2 <= cfg.backtest.train_split <= 0.9:
        raise ValueError("backtest.train_split must be in [0.2, 0.9]")
