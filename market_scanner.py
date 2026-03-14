"""
market_scanner.py — Fetches and caches active Polymarket markets
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, List

import config
import logger as log_mod
from utils import safe_get

_log = log_mod.get_logger(__name__)


# --------------------------------------------------
# MARKET OBJECT
# --------------------------------------------------

@dataclass
class Market:

    market_id: str
    condition_id: str
    question: str

    token_ids: List[str]

    yes_price: float
    no_price: float

    spread: float

    liquidity: float
    volume_24h: float

    active: bool

    end_date_iso: str = ""

    extra: dict[str, Any] = field(default_factory=dict)

    # ---------------------------------------------

    @property
    def mid_yes(self) -> float:

        return self.yes_price

    def __repr__(self):

        return (
            f"Market({self.market_id[:8]} "
            f"YES={self.yes_price:.3f} "
            f"spread={self.spread:.4f} "
            f"liq=${self.liquidity:.0f})"
        )


# --------------------------------------------------
# SCANNER
# --------------------------------------------------

class MarketScanner:

    def __init__(self):

        self._cache: List[Market] = []

        self._cache_time: float = 0.0

        self._cache_ttl = 60  # seconds

    # --------------------------------------------------

    def get_markets(self) -> List[Market]:

        now = time.monotonic()

        if now - self._cache_time < self._cache_ttl:

            return self._cache

        try:

            markets = self._fetch_markets()

            self._cache = markets

            self._cache_time = now

            _log.info(
                f"Scanner refreshed: {len(markets)} markets"
            )

        except Exception as exc:

            log_mod.log_error(
                "market_scanner fetch failed",
                exc
            )

        return self._cache

    # --------------------------------------------------

    def _fetch_markets(self) -> List[Market]:

        raw = self._gamma_markets()

        markets: List[Market] = []

        for item in raw:

            try:

                m = self._parse_gamma_market(item)

                if m:

                    markets.append(m)

            except Exception as exc:

                _log.debug(
                    f"Skipping malformed market: {exc}"
                )

        return markets

    # --------------------------------------------------

    def _gamma_markets(self) -> List[dict]:

        results: List[dict] = []

        offset = 0
        limit = 100

        while True:

            url = (
                f"{config.GAMMA_API_BASE}/markets"
                f"?active=true&closed=false"
                f"&limit={limit}&offset={offset}"
            )

            data = safe_get(url, timeout=15)

            if isinstance(data, list):

                batch = data

            elif isinstance(data, dict):

                batch = data.get("markets", [])

            else:

                break

            if not batch:

                break

            results.extend(batch)

            if len(batch) < limit:

                break

            offset += limit

            # safety cap
            if offset >= 5000:

                break

        return results

    # --------------------------------------------------

    def _parse_gamma_market(self, item: dict) -> Market | None:

        if not item.get("active"):
            return None

        if item.get("closed"):
            return None

        market_id = str(item.get("id", ""))
        condition_id = str(item.get("conditionId", ""))

        if not market_id or not condition_id:

            return None

        question = str(item.get("question", ""))

        # ------------------------------------------
        # TOKEN IDS
        # ------------------------------------------

        token_ids = item.get("clobTokenIds")

        if not token_ids:

            tokens = item.get("tokens", [])

            token_ids = [
                t.get("token_id")
                for t in tokens
                if t.get("token_id")
            ]

        if not token_ids or len(token_ids) < 2:

            return None

        token_ids = [str(t) for t in token_ids[:2]]

        # ------------------------------------------
        # PRICES
        # ------------------------------------------

        tokens_raw = item.get("tokens", [])

        yes_price = 0.5
        no_price = 0.5

        if len(tokens_raw) >= 2:

            try:

                yes_price = float(
                    tokens_raw[0].get("price", 0.5)
                )

                no_price = float(
                    tokens_raw[1].get("price", 0.5)
                )

            except Exception:

                pass

        # clamp probabilities

        yes_price = max(0.01, min(0.99, yes_price))
        no_price = max(0.01, min(0.99, no_price))

        # ------------------------------------------
        # SPREAD
        # ------------------------------------------

        spread = abs((yes_price + no_price) - 1.0)

        # ------------------------------------------
        # LIQUIDITY
        # ------------------------------------------

        liquidity = float(
            item.get("liquidity", 0)
            or item.get("liquidityUSD", 0)
            or 0
        )

        volume_24h = float(
            item.get("volume24hr", 0)
            or item.get("volume", 0)
            or 0
        )

        # ------------------------------------------

        return Market(

            market_id=market_id,
            condition_id=condition_id,
            question=question,

            token_ids=token_ids,

            yes_price=yes_price,
            no_price=no_price,

            spread=spread,

            liquidity=liquidity,
            volume_24h=volume_24h,

            active=True,

            end_date_iso=item.get("endDate", ""),

            extra=item,
        )
