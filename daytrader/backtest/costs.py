"""What trading costs do to a day-trading edge, before any strategy is chosen.

On 5m crypto bars a 1.2xATR stop is roughly 0.3% of price. Round-trip taker
fees plus slippage are roughly 0.18% of price. That means well over half of
the risk unit is spent on costs, and the strategy has to earn it back before
it earns anything. This module makes that arithmetic explicit, because it
decides which stop distances are worth backtesting at all.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import Config
from ..core import indicators as ind

DEFAULT_MULTIPLES = (1.0, 1.5, 2.0, 3.0, 5.0, 8.0)


def cost_per_r(cfg: Config, stop_pct: float) -> tuple[float, float]:
    """Fees and slippage expressed in units of risk, given a stop distance in %."""
    if stop_pct <= 0:
        return float("inf"), float("inf")
    fee_r = 2 * cfg.execution.taker_fee_pct / stop_pct
    slip_r = (cfg.execution.slippage_bps + cfg.execution.stop_slippage_bps) / 100.0 / stop_pct
    return fee_r, slip_r


def breakeven_win_rate(total_cost_r: float, target_r: float) -> float:
    """Hit rate needed to break even at a given reward-to-risk, after costs.

    A winner nets (target - cost) and a loser costs (1 + cost), so
    p = (1 + cost) / (1 + target).
    """
    if target_r <= 0:
        return 1.0
    return min(1.0, (1.0 + total_cost_r) / (1.0 + target_r))


def analyse(df: pd.DataFrame, cfg: Config, atr_window: int = 14,
            multiples=DEFAULT_MULTIPLES, targets=(1.0, 2.0, 3.0)) -> pd.DataFrame:
    """Cost table for one symbol across candidate stop distances."""
    atr = ind.atr(df["high"], df["low"], df["close"], atr_window)
    atr_pct = float((atr / df["close"]).median() * 100.0)

    rows = []
    for mult in multiples:
        stop_pct = mult * atr_pct
        fee_r, slip_r = cost_per_r(cfg, stop_pct)
        total = fee_r + slip_r
        row = {
            "stop_atr_mult": mult,
            "stop_pct_of_price": stop_pct,
            "fee_r": fee_r,
            "slippage_r": slip_r,
            "cost_r": total,
        }
        for target in targets:
            row[f"breakeven_wr_at_{target:g}r"] = breakeven_win_rate(total, target) * 100.0
        rows.append(row)
    out = pd.DataFrame(rows)
    out.attrs["atr_pct"] = atr_pct
    return out


def summarise(data: dict[str, pd.DataFrame], cfg: Config) -> pd.DataFrame:
    frames = []
    for symbol, df in data.items():
        table = analyse(df, cfg)
        table.insert(0, "symbol", symbol)
        table.insert(1, "median_atr_pct", table.attrs["atr_pct"])
        frames.append(table)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def verdict(table: pd.DataFrame, configured_mult: float, target_r: float = 2.0) -> str:
    """One plain sentence about whether the configured stop can pay for itself."""
    row = table.iloc[(table["stop_atr_mult"] - configured_mult).abs().argmin()]
    wr = row[f"breakeven_wr_at_{target_r:g}r"]
    cost = row["cost_r"]
    if cost >= 0.5:
        tone = "costs dominate: this stop spends over half the risk unit before the trade starts"
    elif cost >= 0.25:
        tone = "costs are heavy but survivable with a real edge"
    else:
        tone = "costs are a manageable drag"
    return (f"At {configured_mult:g}xATR ({row['stop_pct_of_price']:.2f}% of price) each trade "
            f"pays {cost:.2f} R in fees and slippage -- {tone}. "
            f"Breaking even at {target_r:g}R needs a {wr:.0f}% hit rate.")
