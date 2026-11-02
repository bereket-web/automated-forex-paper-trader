from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fx_paper.dashboard import generate_dashboard
from fx_paper.engine import PaperConfig, run_paper_simulation
from fx_paper.model import WalkForwardForecaster
from fx_paper.risk import RiskConfig


class ConstantForecaster:
    model_kind = "test-constant"
    fit_count = 0

    def predict_asof(self, index, features, target):
        if features.iloc[index].isna().any():
            return None
        return 0.01


def make_prices(n=100):
    dates = pd.bdate_range("2022-01-03", periods=n)
    values = 1.05 * np.exp(np.arange(n) * 0.001)
    return pd.DataFrame({"close": values}, index=dates)


def test_zero_baseline_produces_no_orders():
    prices = make_prices()
    result = run_paper_simulation(
        prices,
        forecaster=WalkForwardForecaster(model_kind="zero"),
        config=PaperConfig(spread_pips=0, slippage_pips_per_side=0),
    )
    assert result.trades.empty
    assert result.metrics["closed_trades"] == 0
    assert not any(event["event"] == "paper_order_filled" for event in result.events)
    assert all(event["action"] == "NO_TRADE" for event in result.events if event["event"] == "decision")


def test_orders_fill_next_close_and_hold_one_observation():
    prices = make_prices()
    result = run_paper_simulation(
        prices,
        forecaster=ConstantForecaster(),
        config=PaperConfig(
            spread_pips=0,
            slippage_pips_per_side=0,
            extra_edge_bps=0,
            risk=RiskConfig(risk_fraction=0.01, max_leverage=1.0),
        ),
    )
    assert len(result.trades) > 10
    first_decision = next(event for event in result.events if event["event"] == "paper_order_scheduled")
    first_fill = next(event for event in result.events if event["event"] == "paper_order_filled")
    first_trade = result.trades.iloc[0]
    assert pd.Timestamp(first_fill["date"]) > pd.Timestamp(first_decision["signal_date"])
    assert pd.Timestamp(first_trade["exit_date"]) > pd.Timestamp(first_trade["entry_date"])
    assert len(result.equity) == len(prices)
    assert result.metrics["peak_gross_leverage"] <= 1.001


def test_round_trip_cost_is_booked_once():
    prices = make_prices()
    result = run_paper_simulation(
        prices,
        forecaster=ConstantForecaster(),
        config=PaperConfig(extra_edge_bps=0),
    )
    trade = result.trades.iloc[0]
    expected_gross = trade["units_eur"] * (trade["exit_reference"] - trade["entry_reference"])
    assert trade["gross_pnl_usd"] == pytest.approx(expected_gross)
    assert trade["net_pnl_usd"] == pytest.approx(trade["gross_pnl_usd"] - trade["fees_usd"])
    assert trade["entry_fill_price"] > trade["entry_reference"]
    assert trade["exit_fill_price"] < trade["exit_reference"]


def test_training_excludes_unmatured_labels_at_asof_close():
    rng = np.random.default_rng(10)
    dates = pd.bdate_range("2020-01-01", periods=180)
    x = pd.DataFrame(rng.normal(size=(180, 2)), index=dates, columns=["a", "b"])
    y = pd.Series(rng.normal(size=180), index=dates)
    asof = 120
    # At as-of 120, labels through 118 are mature; mutations at 119 and 120
    # must not affect the model forecast.
    y_changed = y.copy()
    y_changed.iloc[119:121] = 1_000_000
    left = WalkForwardForecaster(min_train=50, lookback=100, retrain_every=1, seed=9)
    right = WalkForwardForecaster(min_train=50, lookback=100, retrain_every=1, seed=9)
    pred_a = left.predict_asof(asof, x, y)
    pred_b = right.predict_asof(asof, x, y_changed)
    assert pred_a == pytest.approx(pred_b)
    assert left.fit_count == right.fit_count == 1


def test_dashboard_is_generated_with_simulation_disclaimer(tmp_path):
    prices = make_prices()
    result = run_paper_simulation(prices, forecaster=ConstantForecaster())
    metrics = tmp_path / "metrics.json"
    equity = tmp_path / "equity.csv"
    trades = tmp_path / "trades.csv"
    import json

    metrics.write_text(json.dumps(result.metrics), encoding="utf-8")
    result.equity.to_csv(equity, index=False)
    result.trades.to_csv(trades, index=False)
    output = generate_dashboard(metrics, equity, trades, tmp_path / "dashboard.html")
    html = output.read_text(encoding="utf-8")
    assert "SIMULATION ONLY" in html
    assert "not establish a tradable edge" in html
    assert "Virtual equity" in html
    assert "Drawdown breaker" in html
