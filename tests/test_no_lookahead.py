"""End-to-end proof that the pipeline cannot see the future.

Each strategy is backtested twice on the same candles: once on the full
history, once on a truncated copy. Every trade that had already closed before
the truncation point must come out byte-for-byte identical. If a strategy or
an indicator peeked ahead, the two runs would diverge.
"""

import pytest

from daytrader.backtest.engine import BacktestEngine
from daytrader.config import Config
from daytrader.data.synthetic import generate
from daytrader.strategies import available, build


@pytest.fixture(scope="module")
def candles():
    return generate(bars=6000, seed=11)


@pytest.mark.parametrize("strategy_name", available())
def test_truncating_the_future_leaves_past_trades_unchanged(candles, strategy_name):
    cfg = Config()
    cut = 4000

    full = BacktestEngine(cfg, build(strategy_name, cfg), "BTCUSDT").run(candles)
    part = BacktestEngine(cfg, build(strategy_name, cfg), "BTCUSDT").run(candles.iloc[:cut])

    # The truncated run's final trade may have been forced shut at the data
    # edge, so it is excluded from the comparison.
    settled = [t for t in part.trades if t.exit_reason.value != "end_of_data"]
    assert settled, f"{strategy_name} produced no closed trades to compare"

    for a, b in zip(settled, full.trades):
        assert a.entry_time == b.entry_time
        assert a.exit_time == b.exit_time
        assert a.side == b.side
        assert a.entry_price == pytest.approx(b.entry_price)
        assert a.exit_price == pytest.approx(b.exit_price)
        assert a.qty == pytest.approx(b.qty)
        assert a.net_pnl == pytest.approx(b.net_pnl)
        assert a.exit_reason == b.exit_reason


@pytest.mark.parametrize("strategy_name", available())
def test_strategies_produce_trades_on_synthetic_data(candles, strategy_name):
    cfg = Config()
    result = BacktestEngine(cfg, build(strategy_name, cfg), "BTCUSDT").run(candles)
    assert result.trades, f"{strategy_name} never traded -- filters are too strict to evaluate"
    assert all(t.risk_amount > 0 for t in result.trades)
