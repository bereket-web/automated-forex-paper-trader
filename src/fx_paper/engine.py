"""Event-driven, broker-free paper order and position simulation."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from fx_paper.features import make_feature_target
from fx_paper.model import WalkForwardForecaster
from fx_paper.risk import RiskConfig, RiskManager
from fx_paper.strategy import Signal, decide


@dataclass(frozen=True)
class PaperConfig:
    initial_cash: float = 10_000.0
    spread_pips: float = 1.2
    slippage_pips_per_side: float = 0.2
    pip_size: float = 0.0001
    extra_edge_bps: float = 2.0
    risk: RiskConfig = RiskConfig()

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.spread_pips < 0 or self.slippage_pips_per_side < 0 or self.pip_size <= 0:
            raise ValueError("spread/slippage must be non-negative and pip_size positive")
        if self.extra_edge_bps < 0:
            raise ValueError("extra_edge_bps must be non-negative")


@dataclass
class Position:
    trade_id: int
    side: int
    units: float
    signal_date: str
    entry_date: str
    entry_reference: float
    entry_fee: float
    prediction: float
    stress_move: float


@dataclass
class PendingOrder:
    order_id: int
    signal_date: str
    side: int
    prediction: float
    required_edge: float


@dataclass
class RunResult:
    metrics: dict[str, Any]
    equity: pd.DataFrame
    trades: pd.DataFrame
    events: list[dict[str, Any]]


def _iso(value: Any) -> str:
    return pd.Timestamp(value).isoformat()


def _event(events: list[dict[str, Any]], event_type: str, **fields: Any) -> None:
    events.append({"event": event_type, **fields})


def run_paper_simulation(
    prices: pd.DataFrame,
    *,
    forecaster: WalkForwardForecaster | None = None,
    config: PaperConfig | None = None,
) -> RunResult:
    """Replay close-only prices using delayed, cost-adjusted simulated orders.

    The sole instrument source is a reference close series. A configurable
    synthetic spread and slippage are applied to paper fills. No broker client,
    live endpoint, credentials, or real order path exists in this package.
    """
    if "close" not in prices.columns or len(prices) < 3:
        raise ValueError("prices need a close column and at least three observations")
    if not prices.index.is_monotonic_increasing or prices.index.has_duplicates:
        raise ValueError("price dates must be strictly increasing and unique")
    close = prices["close"].to_numpy(dtype=float)
    if not np.isfinite(close).all() or (close <= 0).any():
        raise ValueError("close values must be finite and positive")

    cfg = config or PaperConfig()
    model = forecaster or WalkForwardForecaster()
    features, targets = make_feature_target(prices)
    risk = RiskManager(cfg.risk)
    cash = float(cfg.initial_cash)
    peak_equity = cash
    position: Position | None = None
    pending: PendingOrder | None = None
    next_order_id = 1
    next_trade_id = 1
    equity_rows: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    total_fees = 0.0
    one_side_adverse = cfg.pip_size * (cfg.spread_pips / 2.0 + cfg.slippage_pips_per_side)

    for index, (date, price) in enumerate(zip(prices.index, close, strict=True)):
        date_str = _iso(date)
        day_start_equity = cash

        # Close the prior one-bar position. Spread and slippage are booked as
        # explicit fees once; simulated fill prices are retained for audit.
        if position is not None:
            exit_fill_price = float(price - position.side * one_side_adverse)
            exit_fee = position.units * one_side_adverse
            gross_pnl = position.units * position.side * (float(price) - position.entry_reference)
            net_pnl = gross_pnl - position.entry_fee - exit_fee
            cash += gross_pnl - exit_fee
            total_fees += exit_fee
            trades.append(
                {
                    "trade_id": position.trade_id,
                    "signal_date": position.signal_date,
                    "entry_date": position.entry_date,
                    "exit_date": date_str,
                    "side": "LONG" if position.side > 0 else "SHORT",
                    "units_eur": position.units,
                    "entry_reference": position.entry_reference,
                    "exit_reference": float(price),
                    "entry_fill_price": position.entry_reference + position.side * one_side_adverse,
                    "exit_fill_price": exit_fill_price,
                    "prediction": position.prediction,
                    "gross_pnl_usd": gross_pnl,
                    "fees_usd": position.entry_fee + exit_fee,
                    "net_pnl_usd": net_pnl,
                    "stress_move_fraction": position.stress_move,
                }
            )
            _event(
                events,
                "position_closed",
                trade_id=position.trade_id,
                date=date_str,
                reason="one-bar time exit",
                gross_pnl_usd=round(gross_pnl, 6),
                fees_usd=round(position.entry_fee + exit_fee, 6),
                net_pnl_usd=round(net_pnl, 6),
            )
            position = None

        peak_equity = max(peak_equity, cash)
        was_halted = risk.halted
        breaker_reason = risk.observe_equity(equity=cash, peak_equity=peak_equity)
        if breaker_reason and not was_halted:
            _event(
                events,
                "risk_circuit_breaker",
                date=date_str,
                equity_usd=round(cash, 6),
                peak_equity_usd=round(peak_equity, 6),
                drawdown_fraction=cash / peak_equity - 1.0,
                reason=breaker_reason,
            )

        # A signal from the prior close is filled now; sizing uses only values
        # available at this fill close and prior rolling volatility.
        if pending is not None:
            vol_col = features["volatility_21"].iloc[index]
            volatility = float(vol_col) if pd.notna(vol_col) else 0.0
            units, risk_reason = risk.size_order(
                equity=cash,
                peak_equity=peak_equity,
                day_start_equity=day_start_equity,
                price=float(price),
                volatility=volatility,
            )
            if units > 0:
                entry_fee = units * one_side_adverse
                position = Position(
                    trade_id=next_trade_id,
                    side=pending.side,
                    units=units,
                    signal_date=pending.signal_date,
                    entry_date=date_str,
                    entry_reference=float(price),
                    entry_fee=entry_fee,
                    prediction=pending.prediction,
                    stress_move=max(cfg.risk.min_stress_move, cfg.risk.stress_vol_multiple * volatility),
                )
                cash -= entry_fee
                total_fees += entry_fee
                _event(
                    events,
                    "paper_order_filled",
                    order_id=pending.order_id,
                    trade_id=next_trade_id,
                    date=date_str,
                    side="BUY" if pending.side > 0 else "SELL",
                    units_eur=round(units, 6),
                    reference_price=float(price),
                    simulated_fill_price=float(price + pending.side * one_side_adverse),
                    assumed_entry_cost_usd=round(entry_fee, 6),
                    signal_date=pending.signal_date,
                    prediction=pending.prediction,
                    risk_check=risk_reason,
                )
                next_trade_id += 1
            else:
                _event(
                    events,
                    "paper_order_blocked",
                    order_id=pending.order_id,
                    date=date_str,
                    side="BUY" if pending.side > 0 else "SELL",
                    reason=risk_reason,
                )
            pending = None

        current_equity = cash
        peak_equity = max(peak_equity, current_equity)
        drawdown = current_equity / peak_equity - 1.0
        position_side = 0 if position is None else position.side
        exposure = 0.0 if position is None else position.units * float(price) / max(current_equity, 1e-12)
        equity_rows.append(
            {
                "date": date_str,
                "cash_usd": cash,
                "equity_usd": current_equity,
                "position_side": position_side,
                "gross_leverage": exposure,
                "drawdown_fraction": drawdown,
            }
        )

        # The one-bar delayed fill means row i's prediction is for the return
        # beginning at close i+1, not the interval ending at that fill.
        prediction = model.predict_asof(index, features, targets) if index + 2 < len(prices) else None
        if risk.halted:
            _event(events, "decision", date=date_str, action="NO_TRADE", reason="drawdown circuit breaker latched")
            continue
        if prediction is None:
            _event(events, "decision", date=date_str, action="NO_TRADE", reason="insufficient matured training data or horizon")
            continue
        cost_bps = 10_000.0 * (cfg.spread_pips + 2.0 * cfg.slippage_pips_per_side) * cfg.pip_size / float(price)
        signal: Signal = decide(
            prediction,
            round_trip_cost_bps=cost_bps,
            extra_edge_bps=cfg.extra_edge_bps,
        )
        _event(
            events,
            "decision",
            date=date_str,
            action=signal.label,
            prediction=prediction,
            estimated_round_trip_cost_bps=cost_bps,
            required_edge_bps=signal.required_edge * 10_000.0,
            reason=signal.reason,
        )
        if signal.side:
            pending = PendingOrder(
                order_id=next_order_id,
                signal_date=date_str,
                side=signal.side,
                prediction=prediction,
                required_edge=signal.required_edge,
            )
            _event(
                events,
                "paper_order_scheduled",
                order_id=next_order_id,
                signal_date=date_str,
                intended_fill="next observed close",
                side="BUY" if signal.side > 0 else "SELL",
                prediction=prediction,
            )
            next_order_id += 1

    # A position opened on the final observed close would be truncated; the
    # loop only schedules orders for which both fill and exit observations exist.
    equity_frame = pd.DataFrame(equity_rows)
    trades_frame = pd.DataFrame(trades)
    metrics = calculate_metrics(equity_frame, trades_frame, cfg, model, total_fees)
    breaker_event = next((event for event in events if event["event"] == "risk_circuit_breaker"), None)
    metrics["drawdown_circuit_breaker_triggered"] = breaker_event is not None
    metrics["drawdown_circuit_breaker_date"] = breaker_event.get("date") if breaker_event else None
    return RunResult(metrics=metrics, equity=equity_frame, trades=trades_frame, events=events)


def calculate_metrics(
    equity: pd.DataFrame,
    trades: pd.DataFrame,
    config: PaperConfig,
    forecaster: WalkForwardForecaster,
    total_fees: float,
) -> dict[str, Any]:
    """Summarize simulated account outcomes; this is not an investment forecast."""
    values = equity["equity_usd"].astype(float)
    returns = values.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    max_drawdown = float(equity["drawdown_fraction"].min()) if not equity.empty else 0.0
    annual_vol = float(returns.std(ddof=1) * math.sqrt(252)) if len(returns) > 1 else 0.0
    sharpe = float(returns.mean() / returns.std(ddof=1) * math.sqrt(252)) if len(returns) > 1 and returns.std(ddof=1) > 0 else None
    net = trades["net_pnl_usd"].astype(float) if not trades.empty else pd.Series(dtype=float)
    wins = net[net > 0]
    losses = net[net < 0]
    gross_profit = float(wins.sum())
    gross_loss = abs(float(losses.sum()))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (None if gross_profit == 0 else "unbounded")
    start = float(values.iloc[0]) if not values.empty else config.initial_cash
    ending = float(values.iloc[-1]) if not values.empty else config.initial_cash
    return {
        "instrument": "EUR/USD reference rate (FRED DEXUSEU; USD per EUR)",
        "model": forecaster.model_kind,
        "period_start": str(equity["date"].iloc[0]) if not equity.empty else None,
        "period_end": str(equity["date"].iloc[-1]) if not equity.empty else None,
        "initial_virtual_cash_usd": config.initial_cash,
        "ending_virtual_equity_usd": ending,
        "total_return_percent": (ending / start - 1.0) * 100.0 if start else 0.0,
        "max_drawdown_percent": max_drawdown * 100.0,
        "annualized_daily_volatility_percent": annual_vol * 100.0,
        "descriptive_sharpe_ratio": sharpe,
        "closed_trades": int(len(trades)),
        "win_rate_percent": float((net > 0).mean() * 100.0) if len(net) else None,
        "profit_factor": profit_factor,
        "average_trade_net_usd": float(net.mean()) if len(net) else None,
        "simulated_fees_usd": float(total_fees),
        "peak_gross_leverage": float(equity["gross_leverage"].max()) if not equity.empty else 0.0,
        "model_refits": forecaster.fit_count,
        "risk_config": asdict(config.risk),
        "fill_assumptions": {
            "spread_pips_full": config.spread_pips,
            "slippage_pips_per_side": config.slippage_pips_per_side,
            "execution": "paper fill at next observed daily close; one-observation hold",
        },
        "warning": "Historical close-only simulation; assumptions omit executable quotes and do not establish a tradable edge or future profitability.",
    }
