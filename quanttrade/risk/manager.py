"""Risk-management engine.

Enforces a layered set of professional risk controls as a *pre-trade* gate and a
*continuous* portfolio monitor:

Pre-trade (per order):
    * per-position size cap (% of equity)
    * gross-exposure cap
    * sector-exposure cap

Portfolio (continuous):
    * maximum daily loss  -> trading halt for the day
    * maximum drawdown    -> trading halt
    * circuit breaker      -> halt on rapid intraday loss

The manager never places orders; it approves/blocks them and raises
:class:`RiskLimitBreached` (or returns a structured decision) so the execution
layer stays in control.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..core.enums import OrderSide
from ..core.exceptions import RiskLimitBreached
from ..core.logging_config import get_logger
from ..models import Order, Position

logger = get_logger(__name__)


@dataclass
class RiskLimits:
    max_daily_loss_pct: float = 0.03
    max_drawdown_pct: float = 0.20
    max_position_pct: float = 0.10
    max_gross_exposure_pct: float = 1.5
    max_sector_pct: float = 0.30
    max_correlation: float = 0.85
    circuit_breaker_pct: float = 0.05  # intraday loss that trips a hard halt

    @classmethod
    def from_config(cls, cfg) -> "RiskLimits":
        g = cfg.get
        return cls(
            max_daily_loss_pct=g("risk.max_daily_loss_pct", 0.03),
            max_drawdown_pct=g("risk.max_drawdown_pct", 0.20),
            max_position_pct=g("risk.max_position_pct", 0.10),
            max_gross_exposure_pct=g("risk.max_gross_exposure_pct", 1.5),
            max_sector_pct=g("risk.max_sector_pct", 0.30),
            max_correlation=g("risk.max_correlation", 0.85),
        )


@dataclass
class RiskDecision:
    approved: bool
    reasons: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:  # truthiness == approved
        return self.approved


class RiskManager:
    """Stateful risk gate + portfolio monitor."""

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()
        self._day: date | None = None
        self._day_start_equity: float = 0.0
        self._high_water_mark: float = 0.0
        self.halted: bool = False
        self.halt_reason: str = ""

    # --- lifecycle ------------------------------------------------------
    def start_day(self, equity: float, today: date | None = None) -> None:
        self._day = today or date.today()
        self._day_start_equity = equity
        if equity > self._high_water_mark:
            self._high_water_mark = equity
        self.halted = False
        self.halt_reason = ""

    def update_equity(self, equity: float) -> None:
        """Continuous monitor -- trips halts on daily-loss / drawdown breaches."""
        if self._day_start_equity == 0:
            self._day_start_equity = equity
        self._high_water_mark = max(self._high_water_mark, equity)

        daily_pl = (equity - self._day_start_equity) / max(self._day_start_equity, 1e-9)
        drawdown = (equity - self._high_water_mark) / max(self._high_water_mark, 1e-9)

        if daily_pl <= -self.limits.max_daily_loss_pct:
            self._halt(f"Max daily loss breached: {daily_pl:.2%}")
        elif daily_pl <= -self.limits.circuit_breaker_pct and not self.halted:
            self._halt(f"Circuit breaker tripped: {daily_pl:.2%} intraday loss")
        if drawdown <= -self.limits.max_drawdown_pct:
            self._halt(f"Max drawdown breached: {drawdown:.2%}")

    def _halt(self, reason: str) -> None:
        if not self.halted:
            logger.error("TRADING HALTED -- %s", reason)
        self.halted = True
        self.halt_reason = reason

    # --- pre-trade gate -------------------------------------------------
    def check_order(
        self,
        order: Order,
        price: float,
        equity: float,
        positions: dict[str, Position],
        *,
        raise_on_breach: bool = False,
    ) -> RiskDecision:
        reasons: list[str] = []

        if self.halted:
            reasons.append(f"trading halted: {self.halt_reason}")
            return self._finish(RiskDecision(False, reasons), raise_on_breach)

        notional = order.quantity * price
        if equity > 0 and order.side == OrderSide.BUY:
            # Per-position cap (existing exposure + new order).
            existing = abs(positions.get(order.symbol, Position(order.symbol)).market_value)
            pos_pct = (existing + notional) / equity
            if pos_pct > self.limits.max_position_pct:
                reasons.append(
                    f"position cap: {pos_pct:.1%} > {self.limits.max_position_pct:.1%}"
                )

            # Gross-exposure cap.
            gross = sum(abs(p.market_value) for p in positions.values()) + notional
            if gross / equity > self.limits.max_gross_exposure_pct:
                reasons.append(
                    f"gross exposure: {gross / equity:.1%} > "
                    f"{self.limits.max_gross_exposure_pct:.1%}"
                )

            # Sector cap.
            sector = order.metadata.get("sector", "unknown")
            sector_val = sum(
                abs(p.market_value) for p in positions.values() if p.sector == sector
            ) + notional
            if sector != "unknown" and sector_val / equity > self.limits.max_sector_pct:
                reasons.append(
                    f"sector '{sector}': {sector_val / equity:.1%} > "
                    f"{self.limits.max_sector_pct:.1%}"
                )

        decision = RiskDecision(approved=not reasons, reasons=reasons)
        return self._finish(decision, raise_on_breach)

    def _finish(self, decision: RiskDecision, raise_on_breach: bool) -> RiskDecision:
        if not decision.approved:
            logger.warning("Order blocked: %s", "; ".join(decision.reasons))
            if raise_on_breach:
                raise RiskLimitBreached("pre_trade", "; ".join(decision.reasons))
        return decision
