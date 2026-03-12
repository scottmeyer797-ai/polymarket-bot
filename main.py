from __future__ import annotations

import os
import signal
import sys
import time
import threading
from flask import Flask

# -------------------------------------------------------------------
# Flask Health Server (required for Railway)
# -------------------------------------------------------------------

app = Flask(__name__)

@app.route("/")
def home():
    return "Polymarket Bot Running", 200

@app.route("/health")
def health():
    return "ok", 200


def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    print(f"Health server starting on port {port}")
    app.run(host="0.0.0.0", port=port)


# -------------------------------------------------------------------
# Bot Imports
# -------------------------------------------------------------------

import config
import logger as log_mod
from cross_market_detector import CrossMarketDetector
from edge_detector import EdgeDetector
from liquidity_filter import LiquidityFilter
from market_scanner import MarketScanner
from monte_carlo import MonteCarloValidator
from portfolio_manager import PortfolioManager
from risk_manager import RiskManager
from trader import Trader


_log = log_mod.get_logger(__name__)
_running = True


# -------------------------------------------------------------------
# Graceful shutdown
# -------------------------------------------------------------------

def _shutdown(signum, frame):
    global _running
    _log.info(f"Shutdown signal {signum} — stopping after current cycle.")
    _running = False


signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT, _shutdown)


# -------------------------------------------------------------------
# Main bot loop
# -------------------------------------------------------------------

def run():
    _log.info(
        "Polymarket Bot starting",
        extra={
            "_dry_run": config.DRY_RUN,
            "_edge_threshold": config.EDGE_THRESHOLD,
            "_confidence_thresh": config.CONFIDENCE_THRESHOLD,
            "_max_capital": config.MAX_TOTAL_CAPITAL_DEPLOYED,
            "_scan_interval": config.SCAN_INTERVAL_SEC,
            "_mc_df": config.MONTE_CARLO_DF,
            "_max_slippage": config.MAX_SLIPPAGE_PERCENT,
            "_max_daily_loss_pct": config.MAX_DAILY_LOSS_PERCENT,
            "_cross_edge_thresh": config.CROSS_MARKET_EDGE_THRESHOLD,
        },
    )

    if config.DRY_RUN:
        _log.info("*** DRY RUN MODE — no real orders will be placed ***")

    scanner = MarketScanner()
    liq_filt = LiquidityFilter()
    edge_det = EdgeDetector()
    cross_det = CrossMarketDetector()
    mc_val = MonteCarloValidator()
    portfolio = PortfolioManager()
    risk_mgr = RiskManager()
    trader = Trader(portfolio)

    cycle = 0
    cached_cross_scores: dict[str, float] = {}

    while _running:

        cycle += 1
        cycle_start = time.monotonic()

        try:
            cross_signals_count = _run_cycle(
                cycle,
                scanner,
                liq_filt,
                edge_det,
                cross_det,
                mc_val,
                portfolio,
                risk_mgr,
                trader,
                cached_cross_scores,
            )
        except Exception as exc:
            log_mod.log_error(f"Unhandled error in cycle {cycle}", exc)
            cross_signals_count = 0

        if cycle % 10 == 0:
            summary = portfolio.summary()
            _log.info(
                "portfolio_summary",
                extra={
                    "_summary": summary,
                    "_cb_tripped": risk_mgr.circuit_breaker_tripped,
                    "_daily_pnl": round(risk_mgr.daily_pnl, 4),
                    "_cross_signals": cross_signals_count,
                },
            )

        elapsed = time.monotonic() - cycle_start
        sleep = max(0.0, config.SCAN_INTERVAL_SEC - elapsed)

        if _running:
            time.sleep(sleep)

    _log.info("Bot stopped cleanly.")


# -------------------------------------------------------------------
# Cycle execution
# -------------------------------------------------------------------

def _run_cycle(
    cycle,
    scanner,
    liq_filt,
    edge_det,
    cross_det,
    mc_val,
    portfolio,
    risk_mgr,
    trader,
    cached_cross_scores,
):

    if risk_mgr.circuit_breaker_tripped:

        _log.warning(
            "circuit_breaker_tripped_no_new_trades",
            extra={"_daily_pnl": round(risk_mgr.daily_pnl, 4)},
        )

        trader.check_fills()
        trader.cancel_stale_orders()
        _check_exits(portfolio, risk_mgr, trader)

        return 0

    all_markets = scanner.get_markets()
    liquid_markets = liq_filt.filter(all_markets)

    cross_signals_count = 0

    if cycle % 3 == 0 and liquid_markets:

        cross_signals = cross_det.detect(liquid_markets)

        cross_signals_count = len(cross_signals)

        cached_cross_scores.clear()

        for sig in cross_signals:

            mid = sig.market_a.market_id

            cached_cross_scores[mid] = max(
                cached_cross_scores.get(mid, 0.0),
                sig.contradiction_score,
            )

    candidates = edge_det.detect(
        liquid_markets,
        cross_market_scores=cached_cross_scores,
    )

    log_mod.log_scan(
        markets_found=len(all_markets),
        markets_filtered=len(all_markets) - len(liquid_markets),
        candidates=len(candidates),
        cross_signals=cross_signals_count,
    )

    if candidates:

        deployed = portfolio.deployed_capital
        opens = portfolio.open_position_count

        for er in candidates:

            if not _running:
                break

            if portfolio.has_position_in_market(er.market.market_id):

                log_mod.log_skipped_trade(
                    er.market.market_id,
                    er.side,
                    "already_have_position",
                    er.edge,
                    er.confidence,
                    er.signal_type,
                )

                continue

            token_idx = 0 if er.side == "YES" else 1

            token_id = (
                er.market.token_ids[token_idx]
                if token_idx < len(er.market.token_ids)
                else ""
            )

            best_ask = trader.get_best_ask(token_id) if token_id else 0.0

            sized = risk_mgr.size_trade(
                er,
                deployed,
                opens,
                best_ask=best_ask,
            )

            if not sized.approved:

                log_mod.log_skipped_trade(
                    er.market.market_id,
                    er.side,
                    sized.reject_reason,
                    er.edge,
                    er.confidence,
                    er.signal_type,
                )

                continue

            mc = mc_val.validate(
                model_prob=er.model_prob,
                market_price=er.market_prob,
                position_size=sized.position_size,
                best_ask=best_ask if best_ask > 0 else None,
            )

            if not mc.passes:

                log_mod.log_skipped_trade(
                    er.market.market_id,
                    er.side,
                    f"monte_carlo_rejected: {mc.reject_reason}",
                    er.edge,
                    er.confidence,
                    er.signal_type,
                )

                continue

            ok = trader.execute(sized)

            if ok:

                deployed += sized.position_size
                opens += 1

            if deployed >= config.MAX_TOTAL_CAPITAL_DEPLOYED:
                break

    trader.check_fills()
    trader.cancel_stale_orders()

    _check_exits(portfolio, risk_mgr, trader)

    return cross_signals_count


# -------------------------------------------------------------------
# Position monitoring
# -------------------------------------------------------------------

def _check_exits(portfolio, risk_mgr, trader):

    for pos in list(portfolio.open_positions):

        if not pos.filled:
            continue

        current_price = _get_current_price(pos.token_id)

        if current_price is None:
            continue

        pnl_pct = (current_price - pos.entry_price) / max(pos.entry_price, 0.001)

        should_exit, exit_reason = _exit_signal(pos, current_price, pnl_pct)

        if not should_exit:
            continue

        pnl = (current_price - pos.entry_price) * (
            pos.size / max(pos.entry_price, 0.001)
        )

        risk_mgr.record_closed_pnl(pnl)

        log_mod.log_trade(
            action="position_closed",
            market_id=pos.market_id,
            side=pos.side,
            edge=0.0,
            confidence=0.0,
            size=pos.size,
            entry_price=pos.entry_price,
            exit_price=current_price,
            pnl=pnl,
            exit_reason=exit_reason,
        )

        portfolio.cancel_position(pos.position_id)


def _exit_signal(pos, current_price, pnl_pct):

    if pnl_pct >= config.MAX_SLIPPAGE_PERCENT * 3:
        return True, f"take_profit pnl={pnl_pct:.2%}"

    if pnl_pct <= -0.10:
        return True, f"stop_loss pnl={pnl_pct:.2%}"

    if current_price >= 0.95 or current_price <= 0.05:
        return True, f"resolution_proximity price={current_price:.3f}"

    age_sec = time.time() - getattr(pos, "opened_at", time.time())

    if age_sec > 72 * 3600:
        return True, f"max_age {age_sec/3600:.1f}h"

    return False, ""


def _get_current_price(token_id):

    from utils import safe_get

    try:

        url = f"{config.POLYMARKET_API_BASE}/mid-point"

        resp = safe_get(url, params={"token_id": token_id}, timeout=8)

        if resp:
            return float(resp.get("mid", 0) or 0) or None

    except Exception:
        pass

    return None


# -------------------------------------------------------------------
# Entry point
# -------------------------------------------------------------------

if __name__ == "__main__":

    # Start health server for Railway
    threading.Thread(target=run_health_server, daemon=True).start()

    try:
        run()
    except KeyboardInterrupt:
        _log.info("KeyboardInterrupt — exiting.")
        sys.exit(0)
