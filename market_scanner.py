"""
market_scanner.py — Fetches and caches active Polymarket markets.

Uses the Gamma REST API for market metadata.
Results are cached for SCAN_INTERVAL_SEC seconds to avoid hammering endpoints.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any
import config
import logger as log_mod
from utils import safe_get

_log = log_mod.get_logger(__name__)


@dataclass
class Market:
    market_id:    str
    condition_id: str
    question:     str
    token_ids:    list[str]
    yes_price:    float
    no_price:     float
    spread:       float
    liquidity:    float
    volume_24h:   float
    active:       bool
    end_date_iso: str = ""
    extra:        dict[str, Any] = field(default_factory=dict)

    @property
    def mid_yes(self) -> float:
        return self.yes_price

    def __repr__(self) -> str:
        return (
            f"Market({self.market_id[:8]}… "
            f"YES={self.yes_price:.2%} "
            f"spread={self.spread:.3f} "
            f"liq=${self.liquidity:.0f})"
        )


class MarketScanner:
    def __init__(self) -> None:
        self._cache:      list[Market] = []
        self._cache_time: float        = 0.0

    def get_markets(self) -> list[Market]:
        now = time.monotonic()
        if now - self._cache_time < config.SCAN_INTERVAL_SEC:
            return self._cache
        try:
            markets = self._fetch_markets()
            self._cache      = markets
            self._cache_time = now
            _log.info(f"Scanner refreshed: {len(markets)} active markets fetched")
        except Exception as exc:
            log_mod.log_error("market_scanner fetch failed", exc)
        return self._cache

    def _fetch_markets(self) -> list[Market]:
        raw = self._gamma_markets()
        markets: list[Market] = []
        for item in raw:
            try:
                m = self._parse_gamma_market(item)
                if m is not None:
                    markets.append(m)
            except Exception as exc:
                _log.debug(f"Skipping malformed market entry: {exc}")
        return markets

    def _gamma_markets(self) -> list[dict]:
        results: list[dict] = []
        offset = 0
        limit  = 100
        while True:
            url = (
                f"{config.GAMMA_API_BASE}/markets"
                f"?active=true&closed=false&limit={limit}&offset={offset}"
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
            if offset >= 2000:
                break
        return results

    def _parse_gamma_market(self, item: dict) -> Market | None:
        if not item.get("active", False):
            return None
        if item.get("closed", False):
            return None
        market_id    = item.get("id", "")
        condition_id = item.get("conditionId", "")
        question     = item.get("question", "")
        if not market_id or not condition_id:
            return None
        token_ids = item.get("clobTokenIds") or []
        if not token_ids:
            tokens = item.get("tokens", [])
            token_ids = [t.get("token_id", "") for t in tokens if t.get("token_id")]
        if len(token_ids) < 2:
            return None
        tokens_raw = item.get("tokens", [])
        yes_price = 0.5
        no_price  = 0.5
        if len(tokens_raw) >= 2:
            try:
                yes_price = float(tokens_raw[0].get("price", 0.5))
                no_price  = float(tokens_raw[1].get("price", 0.5))
            except (ValueError, TypeError):
                pass
        spread = abs(yes_price + no_price - 1.0)
        liquidity  = float(item.get("liquidity",  0) or 0)
        volume_24h = float(item.get("volume24hr", 0) or item.get("volume", 0) or 0)
        return Market(
            market_id    = str(market_id),
            condition_id = str(condition_id),
            question     = str(question),
            token_ids    = [str(t) for t in token_ids],
            yes_price    = yes_price,
            no_price     = no_price,
            spread       = spread,
            liquidity    = liquidity,
            volume_24h   = volume_24h,
            active       = True,
            end_date_iso = item.get("endDate", ""),
            extra        = item,
        )
