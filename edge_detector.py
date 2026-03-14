"""
edge_detector.py — Edge detection engine, data-gathering mode.

Model change: shrinkage alpha reduced to near-zero so model probability
closely tracks market price. Edge is now detected purely from:
  - spread inefficiency (yes + no != 1.0)
  - mean reversion from extremes
  - cross-market contradiction scores

This ensures candidates flow through for dry-run data collection.
Thresholds are read from config so they can be tuned via Railway variables
without redeploying.
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

        cross_scores   = cross_market_scores or {}
        candidates:      list[EdgeResult] = []
        below_edge     = 0
        below_conf     = 0
        all_edges:       list[float] = []

        for market in markets:
            cross_score = cross_scores.get(market.market_id, 0.0)
            result      = self._evaluate(market, cross_score)

            all_edges.append(abs(result.edge))

            if abs(result.edge) < self.edge_threshold:
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

        # Always-visible diagnostic summary
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

        return sorted(candidates, key=lambda r: abs(r.edge) * r.confidence, reverse=True)

    def _evaluate(self, market: Market, cross_score: float = 0.0) -> EdgeResult:
        yes_price = market.yes_price
        no_price  = market.no_price

        # ── Edge source 1: spread inefficiency ────────────────────────────────
        # If yes + no != 1.0, one side is mispriced. Buy the underpriced side.
        total       = yes_price + no_price
        spread_edge = 1.0 - total   # positive = both underpriced, negative = overpriced

        # ── Edge source 2: mean reversion from extremes ────────────────────────
        # Prices near 0 or 1 tend to overshoot — model fades them slightly
        reversion_yes = self._reversion_adjustment(yes_price)
        model_yes     = float(np.clip(yes_price + reversion_yes, 0.01, 0.99))
        model_no      = 1.0 - model_yes

        edge_yes = (model_yes - yes_price) + (spread_edge * 0.5)
        edge_no  = (model_no  - no_price)  + (spread_edge * 0.5)

        if abs(edge_yes) >= abs(edge_no):
            side, market_prob, model_prob, edge = "YES", yes_price, model_yes, edge_yes
        else:
            side, market_prob, model_prob, edge = "NO",  no_price,  model_no,  edge_no

        # ── Confidence ─────────────────────────────────────────────────────────
        liq_score    = self._liquidity_score(market)
        spread_score = max(0.0, 1.0 - market.spread / max(config.MAX_SPREAD, 1e-9))
        mom_score    = self._momentum_score(market)
        mr_score     = self._mean_reversion_score(yes_price)
        cm_score     = min(cross_score, 1.0)

        # Simplified confidence — base score from liquidity + spread,
        # boosted by momentum and cross-market signal
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
            edge=edge,
            confidence=confidence,
            price_volatility=abs(model_prob - 0.50) * 2,
            spread_score=spread_score,
            momentum_score=mom_score,
            mean_reversion_score=mr_score,
            cross_market_score=cm_score,
            signal_type=sig_type,
        )

    @staticmethod
    def _reversion_adjustment(price: float) -> float:
        """Nudge extreme prices back toward fair value."""
        if price >= 0.90:
            return -(price - 0.90) * 0.30
        if price <= 0.10:
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
