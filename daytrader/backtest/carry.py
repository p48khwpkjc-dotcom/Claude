"""Cash-and-carry on perpetuals: long spot, short perp, collect the funding.

The position is delta neutral by construction, so this does not backtest a
forecast. What it has to get right instead is everything that quietly eats the
carry, and those are the parts usually left out of the pitch:

1. **Both legs, four fills.** Spot in, perp in, spot out, perp out. At 0.05%
   a side that is 0.20% of notional, which the funding has to earn back before
   the trade is worth anything -- about twenty periods, a week, at the normal
   rate. This is why switching in and out is expensive and why a filter has to
   clear a high bar to be worth it.
2. **Negative funding is a cost, not a pause.** When the rate turns, the
   position pays. An always-on carry wears every one of those periods.
3. **The short can be liquidated.** A rising price loses on the perp leg while
   the matching gain sits in spot and cannot be spent. If the margin buffer
   runs out, the hedge is closed at the worst possible moment and what is left
   is an unhedged long. That is the real risk in a trade advertised as
   risk-free, so it is simulated rather than assumed away.

Returns are expressed on total capital committed -- spot notional plus the
margin posted against the short -- because that is the money that is actually
tied up. Quoting the return on margin alone is the most common way this trade
is made to look several times better than it is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd


@dataclass(slots=True)
class CarryConfig:
    fee_pct: float = 0.05          # per side, per leg
    slippage_bps: float = 3.0
    margin_pct: float = 50.0       # of notional, posted against the short
    liquidation_buffer_pct: float = 80.0   # of margin lost before forced close
    enter_above: float | None = None   # per-period rate to switch on; None = always on
    exit_below: float | None = None
    min_hold_periods: int = 3      # do not flip in and out on one noisy reading


@dataclass(slots=True)
class CarryResult:
    symbol: str
    periods: int
    periods_in_market: int
    funding_collected: float       # in units of capital
    fees_paid: float
    net_return_pct: float
    annualised_pct: float
    cycles: int
    liquidations: int
    worst_drawdown_pct: float
    equity: pd.Series = field(default_factory=pd.Series)

    @property
    def time_in_market_pct(self) -> float:
        return 100.0 * self.periods_in_market / self.periods if self.periods else 0.0


def _cost_per_cycle(cfg: CarryConfig) -> float:
    """Four fills, each paying fee and slippage, as a fraction of notional."""
    per_fill = cfg.fee_pct / 100 + cfg.slippage_bps / 10_000
    return 4 * per_fill


def run(symbol: str, funding: pd.Series, price: pd.Series,
        cfg: CarryConfig) -> CarryResult:
    """Simulate the carry over a funding-rate series aligned to prices.

    `funding` is the per-period rate (0.0001 = 0.01%), indexed by funding time.
    `price` is the mark price at those same times, used only for the margin and
    liquidation arithmetic -- the carry itself is price neutral.
    """
    idx = funding.index
    price = price.reindex(idx).ffill()
    if price.isna().any():
        price = price.bfill()

    capital = 1.0                       # everything measured per unit of capital
    notional = capital / (1.0 + cfg.margin_pct / 100)   # spot leg
    margin = notional * cfg.margin_pct / 100
    cycle_cost = _cost_per_cycle(cfg) * notional

    equity = capital
    curve, in_market, entry_price = [], False, np.nan
    collected = fees = 0.0
    periods_in = cycles = liquidations = 0
    held = 0

    for t, rate in funding.items():
        px = float(price.loc[t])

        if in_market:
            # Funding first: it is paid on the perp notional every period.
            pnl = rate * notional
            collected += pnl
            equity += pnl
            periods_in += 1
            held += 1

            # The short leg's unrealised loss is drawn against margin. Spot
            # gains the same amount, but that gain is not available as margin.
            adverse = max(0.0, (px - entry_price) / entry_price) * notional
            if adverse >= margin * cfg.liquidation_buffer_pct / 100:
                liquidations += 1
                equity -= cycle_cost / 2      # forced close of the perp leg
                fees += cycle_cost / 2
                in_market, held = False, 0

            elif (cfg.exit_below is not None and rate < cfg.exit_below
                  and held >= cfg.min_hold_periods):
                equity -= cycle_cost / 2
                fees += cycle_cost / 2
                in_market, held = False, 0
        else:
            wants_in = cfg.enter_above is None or rate > cfg.enter_above
            if wants_in:
                equity -= cycle_cost / 2      # opening both legs
                fees += cycle_cost / 2
                in_market, entry_price, held = True, px, 0
                cycles += 1

        curve.append(equity)

    if in_market:                              # close what is still open
        equity -= cycle_cost / 2
        fees += cycle_cost / 2
        curve[-1] = equity

    series = pd.Series(curve, index=idx)
    peak = series.cummax()
    drawdown = ((series - peak) / peak * 100).min() if len(series) else 0.0
    years = len(idx) / (365 * 3) if len(idx) else 0.0
    net = (equity - capital) * 100
    ann = ((equity ** (1 / years) - 1) * 100) if years > 0 and equity > 0 else 0.0

    return CarryResult(
        symbol=symbol, periods=len(idx), periods_in_market=periods_in,
        funding_collected=collected * 100, fees_paid=fees * 100,
        net_return_pct=net, annualised_pct=ann, cycles=cycles,
        liquidations=liquidations, worst_drawdown_pct=drawdown, equity=series,
    )
