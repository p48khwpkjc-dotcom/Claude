"""Performance statistics.

Judge a day-trading strategy on profit factor, expectancy in R and maximum
drawdown. Win rate on its own says nothing: a 70%-winner that gives it all
back on the three losers is worse than a 35%-winner with runners.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from ..core.types import BacktestResult

MINUTES_PER_YEAR = 365 * 24 * 60


@dataclass(slots=True)
class Metrics:
    strategy: str = ""
    symbol: str = ""
    trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy_r: float = 0.0
    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    return_over_drawdown: float = 0.0
    sharpe: float = 0.0
    max_consecutive_losses: int = 0
    avg_hold_minutes: float = 0.0
    trades_per_day: float = 0.0
    fees_paid: float = 0.0
    fees_pct_of_gross: float = 0.0
    fee_r: float = 0.0  # fees per unit of risk -- the day-trader's real hurdle
    exposure_pct: float = 0.0
    best_trade_r: float = 0.0
    worst_trade_r: float = 0.0
    days: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def compute(result: BacktestResult) -> Metrics:
    m = Metrics(strategy=result.strategy, symbol=result.symbol)
    equity = pd.Series(
        [p.equity for p in result.equity_curve],
        index=pd.DatetimeIndex([p.time for p in result.equity_curve]),
    )
    if not equity.empty:
        m.days = max(1, (equity.index[-1] - equity.index[0]).days)
        m.total_return_pct = (equity.iloc[-1] / result.start_equity - 1.0) * 100.0
        m.max_drawdown_pct = _max_drawdown_pct(equity)
        m.sharpe = _sharpe(equity)
        m.exposure_pct = float(np.mean([p.open_positions > 0 for p in result.equity_curve])) * 100.0
    if m.max_drawdown_pct > 0:
        m.return_over_drawdown = m.total_return_pct / m.max_drawdown_pct

    trades = result.trades
    m.trades = len(trades)
    if not trades:
        return m

    pnl = np.array([t.net_pnl for t in trades])
    r = np.array([t.r_multiple for t in trades])
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]

    m.win_rate = len(wins) / len(pnl) * 100.0
    gross_loss = -losses.sum()
    m.profit_factor = float(wins.sum() / gross_loss) if gross_loss > 0 else float("inf")
    m.expectancy_r = float(r.mean())
    m.avg_win_r = float(r[r > 0].mean()) if (r > 0).any() else 0.0
    m.avg_loss_r = float(r[r <= 0].mean()) if (r <= 0).any() else 0.0
    m.best_trade_r, m.worst_trade_r = float(r.max()), float(r.min())
    m.max_consecutive_losses = _max_streak(pnl <= 0)
    m.avg_hold_minutes = float(np.mean([t.holding_time.total_seconds() / 60 for t in trades]))
    m.trades_per_day = len(trades) / m.days if m.days else 0.0
    m.fees_paid = float(sum(t.fees for t in trades))
    gross = sum(abs(t.gross_pnl) for t in trades)
    m.fees_pct_of_gross = m.fees_paid / gross * 100.0 if gross > 0 else 0.0
    risks = np.array([t.risk_amount for t in trades if t.risk_amount > 0])
    if risks.size:
        fees = np.array([t.fees for t in trades if t.risk_amount > 0])
        m.fee_r = float((fees / risks).mean())
    return m


def _max_drawdown_pct(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = (equity - peak) / peak
    return float(-dd.min() * 100.0)


def _sharpe(equity: pd.Series, periods_per_year: int = 365) -> float:
    """Annualised Sharpe on daily marks. Risk-free is taken as zero."""
    daily = equity.resample("1D").last().dropna()
    if len(daily) < 3:
        return 0.0
    rets = daily.pct_change().dropna()
    if rets.empty or rets.std() == 0:
        return 0.0
    return float(rets.mean() / rets.std() * np.sqrt(periods_per_year))


def _max_streak(flags: np.ndarray) -> int:
    best = current = 0
    for flag in flags:
        current = current + 1 if flag else 0
        best = max(best, current)
    return best


def exit_breakdown(result: BacktestResult) -> pd.DataFrame:
    if not result.trades:
        return pd.DataFrame(columns=["count", "net_pnl", "avg_r"])
    rows = [
        {"exit": t.exit_reason.value, "net_pnl": t.net_pnl, "r": t.r_multiple}
        for t in result.trades
    ]
    df = pd.DataFrame(rows)
    return df.groupby("exit").agg(count=("r", "size"), net_pnl=("net_pnl", "sum"),
                                  avg_r=("r", "mean")).sort_values("count", ascending=False)


def trades_frame(result: BacktestResult) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "symbol": t.symbol, "side": t.side.value,
            "entry_time": t.entry_time, "exit_time": t.exit_time,
            "entry_price": t.entry_price, "exit_price": t.exit_price,
            "qty": t.qty, "net_pnl": t.net_pnl, "fees": t.fees,
            "r_multiple": t.r_multiple, "exit_reason": t.exit_reason.value,
            "hold_minutes": t.holding_time.total_seconds() / 60,
            "reason": t.reason,
        }
        for t in result.trades
    ])
