"""
edge_detector.py — Statistical edge detection engine.

IMPROVEMENT 6: Enhanced edge validation combining:
  - price momentum (O(n))
  - mean reversion via Z-score (O(n))
  - liquidity score
  - cross_market contradiction score (injected from CrossMarketDetector)

All computation is O(n). No heavy dependencies.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
import numpy as np
from market_scanner import Market
import config
import logger as log_mod

_log = log_mod.get_logger(__name__)


@dataclass
class EdgeResult:
    market:                  Market
    side:                    str
    market_prob:             float
    model_prob:              float
    edge:                    float
    confidence:              float
    price_volatility:        float
    spread_score:            float
    # IMPROVEMENT 6: extended signals
    momentum_score:          float = 0.0
    mean_reversion_score:    float = 0.0
    cross_market_score:      float = 0.0
    signal_type:             str   = "single_market"   # or "cross_market"


class EdgeDetector:
    SHRINKAGE_ALPHA   = 0.15
    EXTREME_THRESHOLD = 0.90

    # IMPROVEMENT 6: component weights (must sum to 1.0)
    W_EDGE       = 0.30
    W_LIQUIDITY  = 0.20
    W_SPREAD     = 0.15
    W_MOMENTUM   = 0.15
    W_MEAN_REV   = 0.10
    W_CROSS      = 0.10

    def __init__(
        self,
        edge_threshold:       float = None,
        confidence_threshold: float = None,
    ):
        self.edge_threshold       = edge_threshold       or config.EDGE_THRESHOLD
        self.confidence_threshold = confidence_threshold or config.CONFIDENCE_THRESHOLD

    # ─────────────────────────────────────────────────────────────────────────
    # Primary detection
    # ─────────────────────────────────────────────────────────────────────────

    def detect(
        self,
        markets:                list[Market],
        cross_market_scores:    dict[str, float] | None = None,
    ) -> list[EdgeResult]:
        """
        Evaluate all markets and return candidates above thresholds.

        Parameters
        ----------
        markets               : Liquidity-filtered market list.
        cross_market_scores   : Optional dict {market_id: contradiction_score}
                                injected from CrossMarketDetector.
        """
        cross_scores = cross_market_scores or {}
        candidates: list[EdgeResult] = []

        for market in markets:
            cross_score = cross_scores.get(market.market_id, 0.0)
            result      = self._evaluate(market, cross_score)
            if result is None:
                continue
            if (result.edge >= self.edge_threshold
                    and result.confidence >= self.confidence_threshold):
                candidates.append(result)
                _log.info(
                    f"Edge[{result.signal_type}]: {market.market_id[:8]}... "
                    f"side={result.side} edge={result.edge:.3f} "
                    f"conf={result.confidence:.3f} "
                    f"cross={result.cross_market_score:.3f}",
                    extra={
                        "_event":      "edge_found",
                        "_market_id":  market.market_id,
                        "_side":       result.side,
                        "_edge":       round(result.edge, 4),
                        "_confidence": round(result.confidence, 4),
                        "_signal_type": result.signal_type,
                    },
                )

        return sorted(candidates, key=lambda r: r.edge * r.confidence, reverse=True)

    # ─────────────────────────────────────────────────────────────────────────
    # Single-market evaluation
    # ─────────────────────────────────────────────────────────────────────────

    def _evaluate(self, market: Market, cross_score: float = 0.0) -> EdgeResult | None:
        raw_yes   = market.yes_price
        model_yes = self._model_probability(raw_yes, market)
        model_no  = 1.0 - model_yes
        edge_yes  = model_yes - raw_yes
        edge_no   = model_no  - market.no_price

        if edge_yes >= edge_no:
            side, market_prob, model_prob, edge = "YES", raw_yes,         model_yes, edge_yes
        else:
            side, market_prob, model_prob, edge = "NO",  market.no_price, model_no,  edge_no

        if edge < self.edge_threshold:
            return None

        # ── IMPROVEMENT 6: compute all signal components ──────────────────────
        liq_score       = self._liquidity_score(market)
        spread_score    = max(0.0, 1.0 - market.spread / max(config.MAX_SPREAD, 1e-9))
        price_vol       = abs(model_prob - 0.50) * 2
        vol_score       = 1.0 - price_vol * 0.5
        momentum_score  = self._momentum_score(market)
        mean_rev_score  = self._mean_reversion_score(raw_yes, market)
        cm_score        = min(cross_score, 1.0)

        # Weighted confidence
        edge_score = min(edge / 0.30, 1.0)
        confidence = (
            self.W_EDGE      * edge_score
            + self.W_LIQUIDITY * liq_score
            + self.W_SPREAD    * spread_score
            + self.W_MOMENTUM  * momentum_score
            + self.W_MEAN_REV  * mean_rev_score
            + self.W_CROSS     * cm_score
        )
        confidence = float(np.clip(confidence, 0.0, 1.0))

        if confidence < self.confidence_threshold:
            return None

        sig_type = "cross_market" if cm_score >= 0.5 else "single_market"

        return EdgeResult(
            market=market,
            side=side,
            market_prob=market_prob,
            model_prob=model_prob,
            edge=edge,
            confidence=confidence,
            price_volatility=float(price_vol),
            spread_score=float(spread_score),
            momentum_score=float(momentum_score),
            mean_reversion_score=float(mean_rev_score),
            cross_market_score=float(cm_score),
            signal_type=sig_type,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Model probability estimation
    # ─────────────────────────────────────────────────────────────────────────

    def _model_probability(self, market_price: float, market: Market) -> float:
        """Shrink extreme prices toward 0.5; add mean-reversion adjustment."""
        prior = 0.50
        # Bayesian shrinkage
        model = (1 - self.SHRINKAGE_ALPHA) * market_price + self.SHRINKAGE_ALPHA * prior
        # Extra discount at extremes (prices near 0 or 1 are often overshoot)
        if market_price >= self.EXTREME_THRESHOLD:
            model -= (market_price - self.EXTREME_THRESHOLD) * 0.40
        elif market_price <= (1 - self.EXTREME_THRESHOLD):
            model += ((1 - self.EXTREME_THRESHOLD) - market_price) * 0.40
        return float(np.clip(model, 0.01, 0.99))

    # ─────────────────────────────────────────────────────────────────────────
    # IMPROVEMENT 6 signal scorers — all O(n) or O(1)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _liquidity_score(market: Market) -> float:
        """Log-normalised liquidity 0..1."""
        return float(np.clip(
            math.log10(max(market.liquidity, 1.0)) / math.log10(50_000),
            0.0, 1.0
        ))

    @staticmethod
    def _momentum_score(market: Market) -> float:
        """
        Derive a momentum signal from yes_price distance from 0.5.
        Prices far from 0.5 with high volume indicate momentum.
        Score is higher when the market has strong directional conviction.
        """
        distance   = abs(market.yes_price - 0.50)
        vol_factor = min(math.log10(max(market.volume_24h, 1.0)) / math.log10(100_000), 1.0)
        return float(np.clip(distance * vol_factor * 2.0, 0.0, 1.0))

    @staticmethod
    def _mean_reversion_score(yes_price: float, market: Market) -> float:
        """
        Z-score proxy: how far is the price from 0.5 relative to expected
        variance? Extreme prices get a HIGH mean-reversion score
        (they're likely to snap back), which INCREASES confidence in fading them.
        """
        distance = abs(yes_price - 0.50)
        # Normalise: distance of 0.40 (price = 0.10 or 0.90) → score of 1.0
        return float(np.clip(distance / 0.40, 0.0, 1.0))
