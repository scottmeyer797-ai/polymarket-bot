from flask import Flask
import threading

app = Flask(__name__)

@app.route("/health")
def health():
    return "ok", 200

main.py — Single-threaded event loop for the Polymarket trading bot.

IMPROVEMENT 1: Removed all background threads. Everything runs sequentially
in one loop with timed sub-tasks, eliminating race conditions and reducing
CPU context-switch overhead.

Loop structure (every SCAN_INTERVAL_SEC seconds):
  1. scan markets
  2. liquidity filter
  3. cross-market detection          (every 3rd cycle)
  4. edge detection (+ cross scores)
  5. monte carlo + risk sizing
  6. slippage check + trade execution
  7. fill check + stale order cleanup (every cycle)
  8. position exit monitoring         (every cycle)
  9. portfolio summary log            (every 10th cycle)
"""
from __future__ import annotations

import signal
import sys
import time

import config
import logger as log_mod
from cross_market_detector import CrossMarketDetector, CrossMarketSignal
from edge_detector import EdgeDetector, EdgeResult
from liquidity_filter import LiquidityFilter
from market_scanner import Market, MarketScanner
from monte_carlo import MonteCarloValidator
from portfolio_manager import PortfolioManager
from risk_manager import RiskManager
from trader import Trader

_log     = log_mod.get_logger(__name__)
_running = True


def _shutdown(signum, frame):
    global _running
    _log.info(f"Shutdown signal {signum} — stopping after current cycle.")
    _running = False


signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT,  _shutdown)


# ─────────────────────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────────────────────

def run():
    _log.info(
        "Polymarket Bot starting",
        extra={
            "_dry_run":            config.DRY_RUN,
            "_edge_threshold":     config.EDGE_THRESHOLD,
            "_confidence_thresh":  config.CONFIDENCE_THRESHOLD,
            "_max_capital":        config.MAX_TOTAL_CAPITAL_DEPLOYED,
            "_scan_interval":      config.SCAN_INTERVAL_SEC,
            "_mc_df":              config.MONTE_CARLO_DF,
            "_max_slippage":       config.MAX_SLIPPAGE_PERCENT,
            "_max_daily_loss_pct": config.MAX_DAILY_LOSS_PERCENT,
            "_cross_edge_thresh":  config.CROSS_MARKET_EDGE_THRESHOLD,
        },
    )
    if config.DRY_RUN:
        _log.info("*** DRY RUN MODE — no real orders will be placed ***")

    # ── Instantiate modules ───────────────────────────────────────────────────
    scanner    = MarketScanner()
    liq_filt   = LiquidityFilter()
    edge_det   = EdgeDetector()
    cross_det  = CrossMarketDetector()
    mc_val     = MonteCarloValidator()
    portfolio  = PortfolioManager()
    risk_mgr   = RiskManager()
    trader     = Trader(portfolio)

    cycle             = 0
    cached_cross_scores: dict[str, float] = {}

    while _running:
        cycle      += 1
        cycle_start = time.monotonic()

        try:
            cross_signals_count = _run_cycle(
                cycle, scanner, liq_filt, edge_det, cross_det,
                mc_val, portfolio, risk_mgr, trader,
                cached_cross_scores,
            )
        except Exception as exc:
            log_mod.log_error(f"Unhandled error in cycle {cycle}", exc)
            cross_signals_count = 0

        # ── Portfolio summary every 10 cycles (~100 s) ────────────────────────
        if cycle % 10 == 0:
            summary = portfolio.summary()
            _log.info(
                "portfolio_summary",
                extra={
                    "_summary":          summary,
                    "_cb_tripped":       risk_mgr.circuit_breaker_tripped,
                    "_daily_pnl":        round(risk_mgr.daily_pnl, 4),
                    "_cross_signals":    cross_signals_count,
                },
            )

        elapsed = time.monotonic() - cycle_start
        sleep   = max(0.0, config.SCAN_INTERVAL_SEC - elapsed)
        if _running:
            time.sleep(sleep)

    _log.info("Bot stopped cleanly.")


# ─────────────────────────────────────────────────────────────────────────────
# Single cycle — all steps sequential, no threads
# ─────────────────────────────────────────────────────────────────────────────

def _run_cycle(
    cycle:               int,
    scanner:             MarketScanner,
    liq_filt:            LiquidityFilter,
    edge_det:            EdgeDetector,
    cross_det:           CrossMarketDetector,
    mc_val:              MonteCarloValidator,
    portfolio:           PortfolioManager,
    risk_mgr:            RiskManager,
    trader:              Trader,
    cached_cross_scores: dict[str, float],
) -> int:
    """
    Execute one full scan → trade cycle.
    Returns the number of cross-market signals found.
    """

    # ── IMPROVEMENT 4: Skip if circuit breaker is tripped ─────────────────────
    if risk_mgr.circuit_breaker_tripped:
        _log.warning(
            "circuit_breaker_tripped_no_new_trades",
            extra={"_daily_pnl": round(risk_mgr.daily_pnl, 4)},
        )
        # Still run fill checks and stale cleanup
        trader.check_fills()
        trader.cancel_stale_orders()
        _check_exits(portfolio, risk_mgr, trader)
        return 0

    # ── Step 1: Market scan ───────────────────────────────────────────────────
    all_markets    = scanner.get_markets()
    liquid_markets = liq_filt.filter(all_markets)

    # ── Step 2: Cross-market detection (every 3rd cycle) ─────────────────────
    # IMPROVEMENT 1: was a background thread, now inline every 3rd cycle
    cross_signals_count = 0
    if cycle % 3 == 0 and liquid_markets:
        cross_signals = cross_det.detect(liquid_markets)
        cross_signals_count = len(cross_signals)
        # Merge scores into cache
        cached_cross_scores.clear()
        for sig in cross_signals:
            mid = sig.market_a.market_id
            # Take the max score if market appears in multiple signals
            cached_cross_scores[mid] = max(
                cached_cross_scores.get(mid, 0.0),
                sig.contradiction_score,
            )

    # ── Step 3: Single-market edge detection (with cross-market scores) ───────
    # IMPROVEMENT 6: pass cross scores for enhanced confidence calculation
    candidates = edge_det.detect(liquid_markets, cross_market_scores=cached_cross_scores)

    log_mod.log_scan(
        markets_found    = len(all_markets),
        markets_filtered = len(all_markets) - len(liquid_markets),
        candidates       = len(candidates),
        cross_signals    = cross_signals_count,
    )

    if candidates:
        deployed = portfolio.deployed_capital
        opens    = portfolio.open_position_count

        for er in candidates:
            if not _running:
                break
            if portfolio.has_position_in_market(er.market.market_id):
                log_mod.log_skipped_trade(
                    er.market.market_id, er.side,
                    "already_have_position",
                    er.edge, er.confidence, er.signal_type,
                )
                continue

            # ── Step 4: Fetch live best_ask for slippage check ────────────────
            token_idx = 0 if er.side == "YES" else 1
            token_id  = (er.market.token_ids[token_idx]
                         if token_idx < len(er.market.token_ids) else "")
            best_ask  = trader.get_best_ask(token_id) if token_id else 0.0

            # ── Step 5: Risk sizing + slippage + circuit breaker ──────────────
            sized = risk_mgr.size_trade(er, deployed, opens, best_ask=best_ask)
            if not sized.approved:
                log_mod.log_skipped_trade(
                    er.market.market_id, er.side, sized.reject_reason,
                    er.edge, er.confidence, er.signal_type,
                )
                continue

            # ── Step 6: Monte Carlo validation ───────────────────────────────
            mc = mc_val.validate(
                model_prob    = er.model_prob,
                market_price  = er.market_prob,
                position_size = sized.position_size,
                best_ask      = best_ask if best_ask > 0 else None,
            )
            if not mc.passes:
                log_mod.log_skipped_trade(
                    er.market.market_id, er.side,
                    f"monte_carlo_rejected: {mc.reject_reason}",
                    er.edge, er.confidence, er.signal_type,
                )
                continue

            # ── Step 7: Execute ───────────────────────────────────────────────
            ok = trader.execute(sized)
            if ok:
                deployed += sized.position_size
                opens    += 1

            if deployed >= config.MAX_TOTAL_CAPITAL_DEPLOYED:
                break

    # ── Step 8: Fill checks + stale cleanup (every cycle) ────────────────────
    trader.check_fills()
    trader.cancel_stale_orders()

    # ── Step 9: Position exit monitoring (every cycle) ────────────────────────
    _check_exits(portfolio, risk_mgr, trader)

    return cross_signals_count


def _check_exits(
    portfolio: PortfolioManager,
    risk_mgr:  RiskManager,
    trader:    Trader,
) -> None:
    """
    IMPROVEMENT 1: Replaces the position-monitor background thread.
    Runs synchronously each cycle.
    """
    for pos in list(portfolio.open_positions):
        if not pos.filled:
            continue
        # Fetch current price for the token
        current_price = _get_current_price(pos.token_id)
        if current_price is None:
            continue

        pnl_pct = (current_price - pos.entry_price) / max(pos.entry_price, 0.001)

        should_exit, exit_reason = _exit_signal(pos, current_price, pnl_pct)
        if not should_exit:
            continue

        pnl = (current_price - pos.entry_price) * (pos.size / max(pos.entry_price, 0.001))
        risk_mgr.record_closed_pnl(pnl)

        log_mod.log_trade(
            action      = "position_closed",
            market_id   = pos.market_id,
            side        = pos.side,
            edge        = 0.0,
            confidence  = 0.0,
            size        = pos.size,
            entry_price = pos.entry_price,
            exit_price  = current_price,
            pnl         = pnl,
            exit_reason = exit_reason,
        )
        portfolio.cancel_position(pos.position_id)


def _exit_signal(pos, current_price: float, pnl_pct: float) -> tuple[bool, str]:
    """Simple rule-based exit logic."""
    if pnl_pct >= config.MAX_SLIPPAGE_PERCENT * 3:       # crude TP proxy
        return True, f"take_profit pnl={pnl_pct:.2%}"
    if pnl_pct <= -0.10:                                  # 10% stop loss
        return True, f"stop_loss pnl={pnl_pct:.2%}"
    if current_price >= 0.95 or current_price <= 0.05:
        return True, f"resolution_proximity price={current_price:.3f}"
    age_sec = time.time() - getattr(pos, "opened_at", time.time())
    if age_sec > 72 * 3600:
        return True, f"max_age {age_sec/3600:.1f}h"
    return False, ""


def _get_current_price(token_id: str) -> float | None:
    """Fetch live mid price. Returns None on failure."""
    from utils import safe_get
    try:
        url  = f"{config.POLYMARKET_API_BASE}/mid-point"
        resp = safe_get(url, params={"token_id": token_id}, timeout=8)
        if resp:
            return float(resp.get("mid", 0) or 0) or None
    except Exception:
        pass
    return None


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        _log.info("KeyboardInterrupt — exiting.")
        sys.exit(0)
def run_health_server():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_health_server).start()
