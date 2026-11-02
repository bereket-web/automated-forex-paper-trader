from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fx_paper.features import make_feature_target
from fx_paper.risk import RiskConfig, RiskManager
from fx_paper.strategy import decide


def make_prices(values: np.ndarray) -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-01", periods=len(values))
    return pd.DataFrame({"close": values}, index=dates)


def test_target_starts_after_delayed_entry_close():
    close = np.array([1.00, 1.01, 1.03, 1.02, 1.04])
    features, target = make_feature_target(make_prices(close))
    assert target.iloc[0] == pytest.approx(np.log(close[2] / close[1]))
    assert target.iloc[1] == pytest.approx(np.log(close[3] / close[2]))
    assert pd.isna(target.iloc[-2])


def test_features_at_time_t_do_not_use_future_prices():
    rng = np.random.default_rng(23)
    values = 1.1 * np.exp(np.cumsum(rng.normal(0, 0.003, 150)))
    original = make_prices(values)
    changed_values = values.copy()
    changed_values[100:] *= np.exp(np.linspace(0, 0.4, len(values) - 100))
    changed = make_prices(changed_values)
    x_original, _ = make_feature_target(original)
    x_changed, _ = make_feature_target(changed)
    pd.testing.assert_frame_equal(x_original.iloc[:100], x_changed.iloc[:100])


def test_signal_requires_costs_plus_extra_buffer():
    threshold = 4.0 / 10_000
    assert decide(threshold * 0.9, round_trip_cost_bps=2, extra_edge_bps=2).label == "NO_TRADE"
    assert decide(threshold * 1.1, round_trip_cost_bps=2, extra_edge_bps=2).label == "LONG"
    assert decide(-threshold * 1.1, round_trip_cost_bps=2, extra_edge_bps=2).label == "SHORT"


def test_risk_sizing_respects_risk_budget_and_leverage_cap():
    manager = RiskManager(RiskConfig(risk_fraction=0.0025, max_leverage=1.0))
    units, reason = manager.size_order(
        equity=10_000,
        peak_equity=10_000,
        day_start_equity=10_000,
        price=1.1,
        volatility=0.005,
    )
    assert units * 1.1 <= 10_000
    assert units * 1.1 * max(0.0025, 2 * 0.005) <= 25.01
    assert "approved" in reason


def test_daily_loss_blocks_new_positions_and_drawdown_latches():
    config = RiskConfig(daily_loss_limit=0.02, max_drawdown_limit=0.05)
    manager = RiskManager(config)
    units, reason = manager.size_order(
        equity=9_700,
        peak_equity=10_000,
        day_start_equity=10_000,
        price=1.1,
        volatility=0.01,
    )
    assert units == 0
    assert "daily loss" in reason
    units, reason = manager.size_order(
        equity=9_500,
        peak_equity=10_000,
        day_start_equity=9_700,
        price=1.1,
        volatility=0.01,
    )
    assert units == 0
    assert manager.halted
    assert "drawdown" in reason


def test_drawdown_breaker_latches_on_equity_observation_without_an_order():
    manager = RiskManager(RiskConfig(max_drawdown_limit=0.05))
    reason = manager.observe_equity(equity=9_490, peak_equity=10_000)
    assert manager.halted
    assert "drawdown" in reason
    assert manager.observe_equity(equity=9_000, peak_equity=10_000) is None


def test_leverage_above_one_is_rejected():
    with pytest.raises(ValueError, match="above 1x"):
        RiskConfig(max_leverage=1.01)
