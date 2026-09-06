"""The regime harness itself must be trustworthy before its verdicts are."""

import numpy as np
import pytest

from daytrader.backtest import regimes
from daytrader.config import Config
from daytrader.data.synthetic import REGIMES, generate


def variance_ratio(df, window: int = 24) -> float:
    """Above 1 the series trends, below 1 it mean reverts."""
    r = df["close"].pct_change().dropna()
    return float(r.rolling(window).sum().var() / (window * r.var()))


def test_regimes_actually_behave_as_labelled():
    trending = variance_ratio(generate(bars=8000, regime="trending"))
    choppy = variance_ratio(generate(bars=8000, regime="choppy"))
    assert trending > 2.0, f"the trending regime does not trend (VR {trending:.2f})"
    assert choppy < 0.5, f"the choppy regime does not mean revert (VR {choppy:.2f})"
    assert trending > choppy * 5


def test_quiet_regime_is_quieter_and_volatile_is_wilder():
    def vol(name):
        r = generate(bars=8000, regime=name)["close"].pct_change().dropna()
        return r.std()
    assert vol("quiet") < vol("mixed") < vol("volatile")


def test_every_regime_produces_valid_candles():
    for name in REGIMES:
        df = generate(bars=2000, regime=name)
        assert (df["high"] >= df[["open", "close"]].max(axis=1) - 1e-9).all(), name
        assert (df["low"] <= df[["open", "close"]].min(axis=1) + 1e-9).all(), name
        assert (df["volume"] > 0).all(), name
        assert df["close"].gt(0).all(), name


def test_generation_is_deterministic():
    a = generate(bars=1000, regime="mixed", seed=5)
    b = generate(bars=1000, regime="mixed", seed=5)
    assert np.array_equal(a["close"].to_numpy(), b["close"].to_numpy())
    c = generate(bars=1000, regime="mixed", seed=6)
    assert not np.array_equal(a["close"].to_numpy(), c["close"].to_numpy())


def test_frictionless_config_charges_nothing():
    cfg = Config()
    free = regimes.frictionless(cfg)
    assert free.execution.taker_fee_pct == 0
    assert free.execution.slippage_bps == 0
    assert cfg.execution.taker_fee_pct > 0, "the original config must not be mutated"


def test_claim_check_calls_a_losing_trend_strategy_broken():
    matrix = _matrix([("ema_momentum", "trending", -0.4, 100),
                      ("ema_momentum", "choppy", -0.9, 100)])
    out = regimes.check_claims(Config(), matrix)
    verdict = out[(out["regime"] == "trending")]["status"].iloc[0]
    assert verdict == "FAIL"


def test_claim_check_passes_a_working_trend_strategy():
    matrix = _matrix([("ema_momentum", "trending", 0.8, 100),
                      ("ema_momentum", "choppy", -0.5, 100)])
    out = regimes.check_claims(Config(), matrix)
    assert set(out["status"]) == {"pass"}


def test_too_few_trades_is_inconclusive_not_a_pass():
    matrix = _matrix([("ema_momentum", "trending", 3.0, 2),
                      ("ema_momentum", "choppy", -0.5, 100)])
    out = regimes.check_claims(Config(), matrix)
    assert out[out["regime"] == "trending"]["status"].iloc[0] == "inconclusive"


def test_calibration_flags_a_strategy_that_fires_where_it_loses():
    import pandas as pd
    matrix = _matrix([("rsi_reversion", "choppy", 1.0, 50),
                      ("rsi_reversion", "trending", -0.7, 50)])
    frequency = pd.DataFrame([
        {"strategy": "rsi_reversion", "regime": "choppy", "signals": 5, "per_1k_bars": 0.3},
        {"strategy": "rsi_reversion", "regime": "trending", "signals": 995, "per_1k_bars": 50.0},
    ])
    out = regimes.calibration(Config(), matrix, frequency)
    assert out["misfire_pct"].iloc[0] == pytest.approx(99.5)
    assert "miscalibrated" in out["verdict"].iloc[0]


def _matrix(rows):
    import pandas as pd
    return pd.DataFrame([
        {"strategy": s, "regime": r, "costs": "frictionless", "trades": n,
         "expectancy_r": e, "profit_factor": 1.0, "total_return_pct": 0.0, "win_rate": 50.0}
        for s, r, e, n in rows
    ])
