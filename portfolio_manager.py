"""
portfolio_manager.py — Tracks open positions, deployed capital, and PnL.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Optional
import config
import logger as log_mod

_log = log_mod.get_logger(__name__)


@dataclass
class Position:
    position_id:  str
    market_id:    str
    side:         str
    token_id:     str
    size:         float
    entry_price:  float
    filled_price: float
    filled:       bool  = False
    closed:       bool  = False
    open_time:    float = field(default_factory=time.time)
    close_time:   float = 0.0
    exit_price:   float = 0.0
    pnl:          float = 0.0
    order_id:     str   = ""

    @property
    def age_seconds(self) -> float:
        return time.time() - self.open_time

    @property
    def is_stale(self) -> bool:
        return not self.filled and self.age_seconds > config.ORDER_STALE_SEC


class PortfolioManager:
    def __init__(self):
        self._positions: dict[str, Position] = {}
        self._realized_pnl: float = 0.0

    @property
    def open_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if not p.closed]

    @property
    def filled_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if p.filled and not p.closed]

    @property
    def deployed_capital(self) -> float:
        return sum(p.size for p in self.filled_positions)

    @property
    def open_position_count(self) -> int:
        return len(self.open_positions)

    @property
    def realized_pnl(self) -> float:
        return self._realized_pnl

    @property
    def unrealized_pnl(self) -> float:
        return sum(
            (p.filled_price - p.entry_price) * (p.size / max(p.entry_price, 0.01))
            for p in self.filled_positions
        )

    def has_position_in_market(self, market_id: str) -> bool:
        return any(p.market_id == market_id for p in self.open_positions)

    def add_position(self, position: Position) -> None:
        self._positions[position.position_id] = position
        _log.info(
            f"Position opened: {position.position_id} "
            f"market={position.market_id[:8]}... side={position.side} "
            f"size=${position.size:.2f} entry={position.entry_price:.4f}"
        )

    def mark_filled(self, position_id: str, fill_price: float) -> None:
        p = self._positions.get(position_id)
        if p:
            p.filled       = True
            p.filled_price = fill_price
            _log.info(f"Position filled: {position_id} at {fill_price:.4f}")

    def close_position(self, position_id: str, exit_price: float) -> None:
        p = self._positions.get(position_id)
        if not p:
            return
        shares          = p.size / max(p.entry_price, 0.01)
        p.pnl           = (exit_price - p.entry_price) * shares
        p.exit_price    = exit_price
        p.close_time    = time.time()
        p.closed        = True
        self._realized_pnl += p.pnl
        log_mod.log_trade("position_closed", p.market_id, p.side,
                          0.0, 0.0, p.size, p.entry_price, p.pnl,
                          exit_price=exit_price)

    def cancel_position(self, position_id: str) -> Optional[Position]:
        p = self._positions.get(position_id)
        if p:
            p.closed = True
            _log.info(f"Position cancelled (stale): {position_id}")
        return p

    def get_stale_positions(self) -> list[Position]:
        return [p for p in self.open_positions if p.is_stale]

    def summary(self) -> dict:
        return {
            "open_positions":   self.open_position_count,
            "deployed_capital": round(self.deployed_capital, 2),
            "realized_pnl":     round(self._realized_pnl, 2),
            "unrealized_pnl":   round(self.unrealized_pnl, 2),
        }
