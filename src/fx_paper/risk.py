"""Deterministic risk controls for a USD-denominated local paper ledger."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    risk_fraction: float = 0.0025
    max_leverage: float = 1.0
    daily_loss_limit: float = 0.02
    max_drawdown_limit: float = 0.05
    min_stress_move: float = 0.0025
    stress_vol_multiple: float = 2.0

    def __post_init__(self) -> None:
        if not 0 < self.risk_fraction <= 0.01:
            raise ValueError("risk_fraction must be in (0, 0.01]")
        if not 0 < self.max_leverage <= 1.0:
            raise ValueError("max_leverage must be in (0, 1.0]; leverage above 1x is disabled")
        if not 0 < self.daily_loss_limit < 1 or not 0 < self.max_drawdown_limit < 1:
            raise ValueError("loss limits must be fractions between 0 and 1")
        if self.min_stress_move <= 0 or self.stress_vol_multiple <= 0:
            raise ValueError("stress move settings must be positive")


class RiskManager:
    """Size hypothetical units and fail closed when account limits are hit."""

    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or RiskConfig()
        self.halted = False

    def observe_equity(self, *, equity: float, peak_equity: float) -> str | None:
        """Latch the drawdown breaker on every account observation."""
        if self.halted:
            return None
        if equity <= 0 or peak_equity <= 0:
            self.halted = True
            return "non-positive account value; halted"
        drawdown = equity / peak_equity - 1.0
        if drawdown <= -self.config.max_drawdown_limit:
            self.halted = True
            return "maximum drawdown limit reached; halted"
        return None

    def size_order(
        self,
        *,
        equity: float,
        peak_equity: float,
        day_start_equity: float,
        price: float,
        volatility: float,
    ) -> tuple[float, str]:
        """Return EUR units and a block/allow explanation for a new paper fill."""
        if self.halted:
            return 0.0, "drawdown circuit breaker is latched; manual review required"
        if day_start_equity <= 0 or price <= 0:
            self.halted = True
            return 0.0, "non-positive account or market value; halted"
        breaker_reason = self.observe_equity(equity=equity, peak_equity=peak_equity)
        if breaker_reason:
            return 0.0, breaker_reason
        daily_return = equity / day_start_equity - 1.0
        if daily_return <= -self.config.daily_loss_limit:
            return 0.0, "daily loss limit reached; new entries blocked"
        stress_move = max(self.config.min_stress_move, self.config.stress_vol_multiple * max(volatility, 0.0))
        risk_budget = equity * self.config.risk_fraction
        risk_limited_units = risk_budget / (price * stress_move)
        leverage_limited_units = equity * self.config.max_leverage / price
        units = min(risk_limited_units, leverage_limited_units)
        if units <= 0:
            return 0.0, "risk sizing produced zero units"
        return units, "approved within paper risk and gross-notional limits"
