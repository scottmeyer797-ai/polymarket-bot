"""
edge_detector.py — Edge detection engine, data-gathering mode.

Edge sources (in order of reliability):
  1. Spread gap: yes_price + no_price < 1.0 means both sides are underpriced.
     Buy the cheaper side. Edge = (1.0 - total) / 2
  2. Overpriced spread: yes + no > 1.0 means the house takes vig.
     Fade the more overpriced side.
  3. Extreme reversion: prices above 0.90 or below 0.10 are faded.

With EDGE_THRESHOLD=0.001 virtually every market with any spread
inefficiency will produce a candidate for dry-run data collection.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
import numpy as np
from market_scanner import Market
import config
import logger as log_mod

_log = log_mod.get_logger(__name__)


@dataclass
class EdgeResult:
    market:               Market
    side:                 str
    market_prob:          float
    model_prob:           float
    edge:                 float
    confidence:           float
    price_volatility:     float
    spread_score:         float
    momentum_score:       float = 0.0
    mean_reversion_score: float = 0.0
    cross_market_score:   float = 0.0
    signal_type:          str   = "single_market"


class EdgeDetector:

    def __init__(
        self,
        edge_threshold:       float = None,
        confidence_threshold: float = None,
    ):
        self.edge_threshold       = edge_threshold       or config.EDGE_THRESHOLD
        self.confidence_threshold = confidence_threshold or config.CONFIDENCE_THRESHOLD

    def detect(
        self,
        markets:             list[Market],
        cross_market_scores: dict[str, float] | None = None,
    ) -> list[EdgeResult]:

        cross_scores = cross_market_scores or {}
        candidates:  list[EdgeResult] = []
        below_edge   = 0
        below_conf   = 0
        all_edges:   list[float] = []

        for market in markets:
            cross_score = cross_scores.get(market.market_id, 0.0)
            result      = self._evaluate(market, cross_score)
            all_edges.append(result.edge)

            if result.edge < self.edge_threshold:
                below_edge += 1
                continue

            if result.confidence < self.confidence_threshold:
                below_conf += 1
                continue

            candidates.append(result)
            _log.info(
                f"Edge[{result.signal_type}]: {market.market_id[:8]}... "
                f"side={result.side} edge={result.edge:.4f} "
                f"conf={result.confidence:.3f}",
                extra={
                    "_event":       "edge_found",
                    "_market_id":   market.market_id,
                    "_side":        result.side,
                    "_edge":        round(result.edge, 4),
                    "_confidence":  round(result.confidence, 4),
                    "_signal_type": result.signal_type,
                },
            )

        max_edge  = round(max(all_edges), 6)  if all_edges else 0.0
        mean_edge = round(sum(all_edges) / len(all_edges), 6) if all_edges else 0.0
        _log.info(
            f"EdgeDetector: {len(markets)} evaluated | "
            f"below_edge={below_edge} below_conf={below_conf} | "
            f"candidates={len(candidates)} | "
            f"max_edge={max_edge} mean_edge={mean_edge} | "
            f"thresholds: edge>={self.edge_threshold} conf>={self.confidence_threshold}",
            extra={
                "_event":          "edge_summary",
                "_evaluated":      len(markets),
                "_below_edge":     below_edge,
                "_below_conf":     below_conf,
                "_candidates":     len(candidates),
                "_max_edge":       max_edge,
                "_mean_edge":      mean_edge,
                "_edge_threshold": self.edge_threshold,
                "_conf_threshold": self.confidence_threshold,
            },
        )

        return sorted(candidates, key=lambda r: r.edge * r.confidence, reverse=True)

    def _evaluate(self, market: Market, cross_score: float = 0.0) -> EdgeResult:
        yes = market.yes_price
        no  = market.no_price
        total = yes + no

        # ── Primary edge: spread gap ──────────────────────────────────────────
        # total < 1.0 → both sides underpriced, buy cheaper side
        # total > 1.0 → both sides overpriced, fade more overpriced side
        gap = 1.0 - total  # positive = underpriced, negative = overpriced

        # Fair value for each side assuming gap is split equally
        fair_yes = yes + gap / 2.0
        fair_no  = no  + gap / 2.0

        # Edge for each side
        edge_yes = fair_yes - yes  # = gap/2 always
        edge_no  = fair_no  - no   # = gap/2 always

        # ── Secondary edge: extreme reversion ─────────────────────────────────
        rev_yes = self._reversion_adj(yes)
        rev_no  = self._reversion_adj(no)

        edge_yes += rev_yes
        edge_no  += rev_no

        # Pick the better side
        if edge_yes >= edge_no:
            side         = "YES"
            market_prob  = yes
            model_prob   = float(np.clip(yes + edge_yes, 0.01, 0.99))
            edge         = edge_yes
        else:
            side         = "NO"
            market_prob  = no
            model_prob   = float(np.clip(no + edge_no, 0.01, 0.99))
            edge         = edge_no

        # Only trade positive edge
        edge = max(edge, 0.0)

        # ── Confidence ─────────────────────────────────────────────────────────
        liq_score    = self._liquidity_score(market)
        spread_score = max(0.0, 1.0 - market.spread / max(config.MAX_SPREAD, 1e-9))
        mom_score    = self._momentum_score(market)
        mr_score     = self._mean_reversion_score(yes)
        cm_score     = min(cross_score, 1.0)

        confidence = float(np.clip(
            0.35 * liq_score
            + 0.25 * spread_score
            + 0.20 * mom_score
            + 0.10 * mr_score
            + 0.10 * cm_score,
            0.0, 1.0
        ))

        sig_type = "cross_market" if cm_score >= 0.5 else "single_market"

        return EdgeResult(
            market=market,
            side=side,
            market_prob=market_prob,
            model_prob=model_prob,
            edge=round(edge, 6),
            confidence=round(confidence, 4),
            price_volatility=abs(model_prob - 0.50) * 2,
            spread_score=spread_score,
            momentum_score=mom_score,
            mean_reversion_score=mr_score,
            cross_market_score=cm_score,
            signal_type=sig_type,
        )

    @staticmethod
    def _reversion_adj(price: float) -> float:
        """Fade prices in extreme zones."""
        if price > 0.90:
            return -(price - 0.90) * 0.30
        if price < 0.10:
            return  (0.10 - price) * 0.30
        return 0.0

    @staticmethod
    def _liquidity_score(market: Market) -> float:
        return float(np.clip(
            math.log10(max(market.liquidity, 1.0)) / math.log10(50_000),
            0.0, 1.0
        ))

    @staticmethod
    def _momentum_score(market: Market) -> float:
        distance   = abs(market.yes_price - 0.50)
        vol_factor = min(
            math.log10(max(market.volume_24h, 1.0)) / math.log10(100_000),
            1.0
        )
        return float(np.clip(distance * vol_factor * 2.0, 0.0, 1.0))

    @staticmethod
    def _mean_reversion_score(yes_price: float) -> float:
        return float(np.clip(abs(yes_price - 0.50) / 0.40, 0.0, 1.0))
