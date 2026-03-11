"""
risk_manager.py — Position sizing + portfolio-level risk controls.

IMPROVEMENT 4: Circuit breaker — daily loss limit, max open positions.
IMPROVEMENT 3: Slippage check before approval.
IMPROVEMENT 8: Updated sizing formula: base_risk × confidence × (edge / threshold)
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

import config
import logger as log_mod
from edge_detector import EdgeResult

_log = log_mod.get_logger(__name__)


@dataclass
class SizedTrade:
    edge_result:   EdgeResult
    position_size: float
    limit_price:   float
    approved:      bool
    reject_reason: str = ""
    best_ask:      float = 0.0   # passed to MC for slippage simulation


class CircuitBreaker:
    """
    IMPROVEMENT 4: Tracks daily P&L and halts new trades if loss limit is hit.
    Resets at UTC midnight.
    """

    def __init__(self, max_daily_loss_pct: float = None, total_capital: float = None):
        self.max_daily_loss_pct = max_daily_loss_pct or config.MAX_DAILY_LOSS_PERCENT
        self.total_capital      = total_capital      or config.MAX_TOTAL_CAPITAL_DEPLOYED
        self._daily_pnl:   float = 0.0
        self._reset_day:   int   = datetime.now(timezone.utc).day
        self._tripped:     bool  = False

    def record_pnl(self, pnl: float) -> None:
        self._maybe_reset()
        self._daily_pnl += pnl
        loss_threshold   = -abs(self.max_daily_loss_pct * self.total_capital)
        if self._daily_pnl <= loss_threshold and not self._tripped:
            self._tripped = True
            pct = self._daily_pnl / max(self.total_capital, 1.0)
            log_mod.log_circuit_breaker(
                reason=f"daily_pnl={self._daily_pnl:.2f} <= threshold={loss_threshold:.2f}",
                daily_loss_pct=pct,
            )

    @property
    def is_tripped(self) -> bool:
        self._maybe_reset()
        return self._tripped

    def _maybe_reset(self) -> None:
        today = datetime.now(timezone.utc).day
        if today != self._reset_day:
            self._daily_pnl  = 0.0
            self._tripped    = False
            self._reset_day  = today
            _log.info("circuit_breaker_reset", extra={"_event": "cb_reset"})

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl


class RiskManager:
    def __init__(
        self,
        base_risk:             float = None,
        max_capital_per_trade: float = None,
        max_total_capital:     float = None,
        edge_threshold:        float = None,
        max_open_positions:    int   = None,
    ):
        self.base_risk             = base_risk             or config.BASE_RISK
        self.max_capital_per_trade = max_capital_per_trade or config.MAX_CAPITAL_PER_TRADE
        self.max_total_capital     = max_total_capital     or config.MAX_TOTAL_CAPITAL_DEPLOYED
        self.edge_threshold        = edge_threshold        or config.EDGE_THRESHOLD
        self.max_open_positions    = max_open_positions    or config.MAX_OPEN_POSITIONS
        self.circuit_breaker       = CircuitBreaker()

    def size_trade(
        self,
        result:           EdgeResult,
        deployed_capital: float,
        open_positions:   int,
        best_ask:         float = 0.0,
    ) -> SizedTrade:
        """
        Approve and size a trade.

        IMPROVEMENT 4: Circuit breaker check.
        IMPROVEMENT 3: Slippage check.
        IMPROVEMENT 8: New sizing formula.
        """
        # ── IMPROVEMENT 4: Circuit breaker ────────────────────────────────────
        if self.circuit_breaker.is_tripped:
            return SizedTrade(result, 0.0, 0.0, False,
                              "circuit_breaker_tripped: daily loss limit hit",
                              best_ask)

        # ── IMPROVEMENT 4: Max open positions ─────────────────────────────────
        if open_positions >= self.max_open_positions:
            return SizedTrade(result, 0.0, 0.0, False,
                              f"max_open_positions={self.max_open_positions} reached",
                              best_ask)

        # ── Capital headroom ──────────────────────────────────────────────────
        remaining = self.max_total_capital - deployed_capital
        if remaining <= 0:
            return SizedTrade(result, 0.0, 0.0, False,
                              "max_total_capital_deployed exhausted", best_ask)

        # ── IMPROVEMENT 8: Updated position sizing formula ────────────────────
        # position_size = base_risk × confidence × (edge / threshold)
        edge_ratio = result.edge / max(self.edge_threshold, 1e-9)
        raw_size   = self.base_risk * result.confidence * edge_ratio
        size       = round(min(raw_size, self.max_capital_per_trade, remaining), 2)
        size       = max(size, 0.01)

        # ── IMPROVEMENT 3: Slippage protection ───────────────────────────────
        if best_ask > 0:
            expected_fill  = result.market_prob
            slippage       = (best_ask - expected_fill) / max(expected_fill, 0.001)
            if slippage > config.MAX_SLIPPAGE_PERCENT:
                return SizedTrade(
                    result, 0.0, 0.0, False,
                    f"slippage={slippage:.3%} > MAX_SLIPPAGE_PERCENT={config.MAX_SLIPPAGE_PERCENT:.3%}",
                    best_ask,
                )

        limit_price = round(min(result.market_prob + 0.001, 0.99), 4)

        _log.debug(
            f"Sized[{result.signal_type}]: {result.market.market_id[:8]}... "
            f"side={result.side} size=${size:.2f} limit={limit_price:.4f} "
            f"conf={result.confidence:.3f}",
        )
        return SizedTrade(result, size, limit_price, True, "", best_ask)

    def record_closed_pnl(self, pnl: float) -> None:
        """Feed realised P&L into the circuit breaker."""
        self.circuit_breaker.record_pnl(pnl)

    @property
    def daily_pnl(self) -> float:
        return self.circuit_breaker.daily_pnl

    @property
    def circuit_breaker_tripped(self) -> bool:
        return self.circuit_breaker.is_tripped
