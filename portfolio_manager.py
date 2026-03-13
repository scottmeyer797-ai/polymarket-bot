"""
portfolio_manager.py — Tracks open positions, deployed capital, and PnL.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Dict, List

from polymarket_bot import config
from polymarket_bot import logging as log_mod

_log = log_mod.get_logger(__name__)


# --------------------------------------------------
# POSITION OBJECT
# --------------------------------------------------

@dataclass
class Position:

    position_id: str
    market_id: str
    side: str
    token_id: str
    size: float
    entry_price: float
    filled_price: float
    order_id: str

    filled: bool = False
    closed: bool = False

    open_time: float = field(default_factory=time.time)
    close_time: float = 0.0

    exit_price: float = 0.0
    pnl: float = 0.0

    # ---------------------------------------------

    @property
    def age_seconds(self) -> float:
        return time.time() - self.open_time

    @property
    def is_stale(self) -> bool:

        return (
            not self.filled
            and self.age_seconds > config.ORDER_STALE_SEC
        )


# --------------------------------------------------
# PORTFOLIO MANAGER
# --------------------------------------------------

class PortfolioManager:

    def __init__(self):

        self._positions: Dict[str, Position] = {}

        self._realized_pnl: float = 0.0

    # --------------------------------------------------

    def open_positions(self) -> List[Position]:

        return [
            p for p in self._positions.values()
            if not p.closed
        ]

    def filled_positions(self) -> List[Position]:

        return [
            p for p in self._positions.values()
            if p.filled and not p.closed
        ]

    # --------------------------------------------------

    @property
    def deployed_capital(self) -> float:

        return sum(
            p.size for p in self.filled_positions()
        )

    @property
    def open_position_count(self) -> int:

        return len(self.open_positions())

    @property
    def realized_pnl(self) -> float:

        return self._realized_pnl

    # --------------------------------------------------

    def has_position_in_market(self, market_id: str) -> bool:

        for p in self.open_positions():

            if p.market_id == market_id:

                return True

        return False

    # --------------------------------------------------

    def add_position(self, position: Position) -> None:

        if position.position_id in self._positions:

            _log.warning(
                f"Duplicate position ignored: {position.position_id}"
            )
            return

        self._positions[position.position_id] = position

        _log.info(
            f"Position opened | "
            f"market={position.market_id[:8]} "
            f"side={position.side} "
            f"size=${position.size:.2f} "
            f"entry={position.entry_price:.4f}"
        )

    # --------------------------------------------------

    def mark_filled(self, position_id: str, fill_price: float) -> None:

        p = self._positions.get(position_id)

        if not p:
            return

        p.filled = True
        p.filled_price = fill_price

        _log.info(
            f"Position filled | id={position_id[:8]} "
            f"price={fill_price:.4f}"
        )

    # --------------------------------------------------

    def close_position(
        self,
        position_id: str,
        exit_price: float
    ) -> None:

        p = self._positions.get(position_id)

        if not p:
            return

        shares = p.size / max(p.entry_price, 0.0001)

        pnl = (exit_price - p.entry_price) * shares

        p.pnl = pnl
        p.exit_price = exit_price
        p.close_time = time.time()
        p.closed = True

        self._realized_pnl += pnl

        log_mod.log_trade(
            action="position_closed",
            market_id=p.market_id,
            side=p.side,
            size=p.size,
            entry_price=p.entry_price,
            pnl=pnl,
            exit_price=exit_price
        )

    # --------------------------------------------------

    def cancel_position(
        self,
        position_id: str
    ) -> Optional[Position]:

        p = self._positions.get(position_id)

        if p:

            p.closed = True

            _log.info(
                f"Position cancelled (stale) | id={position_id[:8]}"
            )

        return p

    # --------------------------------------------------

    def get_stale_positions(self) -> List[Position]:

        return [

            p for p in self.open_positions()

            if p.is_stale

        ]

    # --------------------------------------------------

    def summary(self) -> dict:

        return {

            "open_positions": self.open_position_count,
            "deployed_capital": round(self.deployed_capital, 2),
            "realized_pnl": round(self._realized_pnl, 2),
        }
