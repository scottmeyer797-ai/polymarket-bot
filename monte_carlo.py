"""
monte_carlo.py — Monte Carlo trade validation with Student-t distribution.

IMPROVEMENT 2: Replaced Gaussian noise with Student-t (fat tails).
IMPROVEMENT 3: Slippage simulation integrated into EV calculation.
Degrees of freedom controlled by MONTE_CARLO_DF (default=3).
Low df = heavier tails = more conservative validation.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import config
import logger as log_mod

_log = log_mod.get_logger(__name__)


@dataclass
class MCResult:
    passes:         bool
    expected_value: float
    win_rate:       float
    ev_5th_pct:     float
    ev_95th_pct:    float
    iterations:     int
    reject_reason:  str = ""


class MonteCarloValidator:
    MIN_WIN_RATE   = 0.55
    MIN_5TH_PCT_EV = -5.0
    MIN_EV         = 0.0

    def __init__(
        self,
        iterations: int = None,
        sigma: float = None,
        df: float = None,
    ):
        self.iterations = max(100, min(iterations or config.MC_ITERATIONS, 1000))
        self.sigma      = sigma or config.MC_SIGMA
        # IMPROVEMENT 2: Student-t degrees of freedom (fat-tail distribution)
        self.df         = max(1.0, df or config.MONTE_CARLO_DF)

    def validate(
        self,
        model_prob:    float,
        market_price:  float,
        position_size: float,
        best_ask:      float | None = None,
    ) -> MCResult:
        """
        Simulate trade outcomes using Student-t distributed probability noise.

        Parameters
        ----------
        model_prob     : Our estimated fair probability.
        market_price   : Current market price (bid/ask mid).
        position_size  : Capital at risk in USDC.
        best_ask       : Actual best ask for slippage check (IMPROVEMENT 3).
        """
        rng = np.random.default_rng()

        # ── IMPROVEMENT 2: Student-t noise (fat tails vs Gaussian) ────────────
        # Standard-t scaled by sigma; df=3 captures sudden news jumps
        noise     = rng.standard_t(df=self.df, size=self.iterations) * self.sigma
        sim_probs = np.clip(model_prob + noise, 0.01, 0.99)

        # ── IMPROVEMENT 3: Slippage simulation ────────────────────────────────
        # Fill price = best_ask (or market_price if unavailable) + random slippage
        base_fill = best_ask if best_ask is not None else market_price
        # Simulate fill price with small positive slippage noise
        slippage_noise = np.abs(rng.standard_t(df=5, size=self.iterations)) * (self.sigma * 0.3)
        fill_prices    = np.clip(base_fill + slippage_noise, 0.01, 0.99)

        # EV: buy at fill_price, resolve at sim_prob (binary payout = 1.0 or 0.0)
        shares  = position_size / np.maximum(fill_prices, 0.01)
        ev_sim  = sim_probs * shares - position_size

        mean_ev  = float(np.mean(ev_sim))
        win_rate = float(np.mean(ev_sim > 0))
        ev_5th   = float(np.percentile(ev_sim, 5))
        ev_95th  = float(np.percentile(ev_sim, 95))

        reject_reason = ""
        if mean_ev <= self.MIN_EV:
            reject_reason = f"mean_ev={mean_ev:.3f} <= {self.MIN_EV}"
        elif win_rate < self.MIN_WIN_RATE:
            reject_reason = f"win_rate={win_rate:.2%} < {self.MIN_WIN_RATE:.0%}"
        elif ev_5th < self.MIN_5TH_PCT_EV:
            reject_reason = f"ev_5th={ev_5th:.2f} < {self.MIN_5TH_PCT_EV}"

        # IMPROVEMENT 4 hook: MIN_EXPECTED_RETURN check
        if not reject_reason and mean_ev < config.MIN_EXPECTED_RETURN:
            reject_reason = f"mean_ev={mean_ev:.3f} below MIN_EXPECTED_RETURN={config.MIN_EXPECTED_RETURN}"

        passes = reject_reason == ""

        _log.debug(
            f"MC[df={self.df}]: passes={passes} EV=${mean_ev:.3f} "
            f"win={win_rate:.1%} 5th=${ev_5th:.2f}",
            extra={
                "_mc_passes":   passes,
                "_mc_ev":       round(mean_ev, 4),
                "_mc_win_rate": round(win_rate, 4),
                "_mc_ev_5th":   round(ev_5th, 4),
                "_mc_df":       self.df,
            },
        )
        return MCResult(passes, mean_ev, win_rate, ev_5th, ev_95th,
                        self.iterations, reject_reason)
