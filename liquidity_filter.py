"""
liquidity_filter.py — Reject markets that do not meet liquidity requirements.

Fixed: filter rejection reasons now log at INFO level so they appear
in Railway logs and the dashboard can show liquid_markets > 0.
Spread check relaxed: Polymarket prices frequently don't sum to exactly 1.0.
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
        passed   = []
        rejected = 0
        reasons: dict[str, int] = {}

        for m in markets:
            ok, reason = self.passes(m)
            if ok:
                passed.append(m)
            else:
                rejected += 1
                # Bucket by reason type for the summary
                key = reason.split(" ")[0]  # e.g. "liquidity", "spread", "volume_24h"
                reasons[key] = reasons.get(key, 0) + 1

        # Log at INFO so it's always visible in Railway
        _log.info(
            f"LiquidityFilter: {len(passed)} passed / {rejected} rejected "
            f"from {len(markets)} markets | reasons: {reasons}",
            extra={
                "_event":           "liquidity_filter_summary",
                "_passed":          len(passed),
                "_rejected":        rejected,
                "_total":           len(markets),
                "_reject_reasons":  reasons,
            }
        )
        return passed
