"""Transparent prediction-to-action rules for research-only paper orders."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Signal:
    side: int
    label: str
    predicted_return: float
    required_edge: float
    reason: str


def decide(
    predicted_return: float,
    *,
    round_trip_cost_bps: float,
    extra_edge_bps: float = 2.0,
) -> Signal:
    """Trade only if the forecast clears estimated costs plus a fixed buffer."""
    if round_trip_cost_bps < 0 or extra_edge_bps < 0:
        raise ValueError("costs and edge buffer must be non-negative")
    required = (round_trip_cost_bps + extra_edge_bps) / 10_000.0
    if predicted_return > required:
        return Signal(1, "LONG", predicted_return, required, "forecast exceeds estimated costs and edge buffer")
    if predicted_return < -required:
        return Signal(-1, "SHORT", predicted_return, required, "forecast is below negative estimated costs and edge buffer")
    return Signal(0, "NO_TRADE", predicted_return, required, "forecast does not clear the cost-adjusted threshold")
