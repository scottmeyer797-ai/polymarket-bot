"""
liquidity_filter.py — Reject markets that do not meet liquidity requirements.
"""
from __future__ import annotations
from market_scanner import Market
import config
import logger as log_mod

_log = log_mod.get_logger(__name__)


class LiquidityFilter:
    def __init__(self, min_liquidity=config.MIN_MARKET_LIQUIDITY,
                 max_spread=config.MAX_SPREAD, min_volume=config.MIN_VOLUME_24H):
        self.min_liquidity = min_liquidity
        self.max_spread    = max_spread
        self.min_volume    = min_volume

    def passes(self, market: Market) -> tuple[bool, str]:
        if market.liquidity < self.min_liquidity:
            return False, f"liquidity ${market.liquidity:.0f} < ${self.min_liquidity:.0f}"
        if market.spread > self.max_spread:
            return False, f"spread {market.spread:.3f} > {self.max_spread:.3f}"
        if market.volume_24h < self.min_volume:
            return False, f"volume_24h ${market.volume_24h:.0f} < ${self.min_volume:.0f}"
        if not (0.01 <= market.yes_price <= 0.99):
            return False, f"yes_price {market.yes_price:.3f} out of range"
        return True, ""

    def filter(self, markets: list[Market]) -> list[Market]:
        passed, rejected = [], 0
        for m in markets:
            ok, reason = self.passes(m)
            if ok:
                passed.append(m)
            else:
                rejected += 1
                _log.debug(f"Rejected {m.market_id[:8]}...: {reason}")
        _log.debug(f"LiquidityFilter: {len(passed)} passed, {rejected} rejected")
        return passed
