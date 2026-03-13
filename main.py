from __future__ import annotations

import os
import signal
import sys
import time
import threading
from flask import Flask
import csv
from datetime import datetime
from flask import Flask, jsonify

# -------------------------------------------------------------------
# Flask Health Server (required for Railway)
# -------------------------------------------------------------------

app = Flask(__name__)

bot_status = {
    "cycles": 0,
    "markets_scanned": 0,
    "candidates_found": 0,
    "cross_signals": 0,
    "open_positions": 0,
    "deployed_capital": 0.0,
    "daily_pnl": 0.0,
    "last_cycle_time": 0.0
}

@app.route("/")
def home():
    return "Polymarket Bot Running", 200
@@ -22,12 +35,97 @@
    return "ok", 200


@app.route("/api/status")
def api_status():
    return jsonify(bot_status)


@app.route("/dashboard")
def dashboard():
    return """
    <html>
    <head>
        <title>Polymarket Bot Dashboard</title>
        <style>
            body { background:#111; color:#eee; font-family:Arial; padding:40px }
            h1 { color:#6cf }
            .card { background:#1b1b1b; padding:20px; margin:10px; border-radius:8px }
        </style>
    </head>
    <body>

    <h1>Polymarket Trading Bot</h1>

    <div id="stats"></div>

    <script>

    async function load(){

        const r = await fetch('/api/status')
        const data = await r.json()

        let html = ""

        for (const [k,v] of Object.entries(data)){

            html += `<div class="card"><b>${k}</b>: ${v}</div>`

        }

        document.getElementById("stats").innerHTML = html
    }

    load()
    setInterval(load, 5000)

    </script>

    </body>
    </html>
    """


def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    print(f"Health server starting on port {port}")
    app.run(host="0.0.0.0", port=port)


# -------------------------------------------------------------------
# CSV Trade Logger
# -------------------------------------------------------------------

def log_trade_csv(action, market_id, side, size, price, pnl=None):

    file_exists = os.path.isfile("trade_log.csv")

    with open("trade_log.csv", "a", newline="") as f:

        writer = csv.writer(f)

        if not file_exists:
            writer.writerow([
                "timestamp",
                "action",
                "market_id",
                "side",
                "size",
                "price",
                "pnl"
            ])

        writer.writerow([
            datetime.utcnow().isoformat(),
            action,
            market_id,
            side,
            size,
            price,
            pnl
        ])


# -------------------------------------------------------------------
# Bot Imports
# -------------------------------------------------------------------
@@ -67,6 +165,7 @@
# -------------------------------------------------------------------

def run():

    _log.info(
        "Polymarket Bot starting",
        extra={
@@ -75,10 +174,6 @@
            "_confidence_thresh": config.CONFIDENCE_THRESHOLD,
            "_max_capital": config.MAX_TOTAL_CAPITAL_DEPLOYED,
            "_scan_interval": config.SCAN_INTERVAL_SEC,
            "_mc_df": config.MONTE_CARLO_DF,
            "_max_slippage": config.MAX_SLIPPAGE_PERCENT,
            "_max_daily_loss_pct": config.MAX_DAILY_LOSS_PERCENT,
            "_cross_edge_thresh": config.CROSS_MARKET_EDGE_THRESHOLD,
        },
    )

@@ -103,6 +198,7 @@
        cycle_start = time.monotonic()

        try:

            cross_signals_count = _run_cycle(
                cycle,
                scanner,
@@ -115,23 +211,21 @@
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

        bot_status["cycles"] += 1
        bot_status["cross_signals"] = cross_signals_count
        bot_status["open_positions"] = portfolio.open_position_count
        bot_status["deployed_capital"] = portfolio.deployed_capital
        bot_status["daily_pnl"] = risk_mgr.daily_pnl
        bot_status["last_cycle_time"] = round(elapsed, 3)

        sleep = max(0.0, config.SCAN_INTERVAL_SEC - elapsed)

        if _running:
@@ -157,20 +251,10 @@
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
    all_markets = scanner.get_markets()

        return 0
    bot_status["markets_scanned"] = len(all_markets)

    all_markets = scanner.get_markets()
    liquid_markets = liq_filt.filter(all_markets)

    cross_signals_count = 0
@@ -197,12 +281,7 @@
        cross_market_scores=cached_cross_scores,
    )

    log_mod.log_scan(
        markets_found=len(all_markets),
        markets_filtered=len(all_markets) - len(liquid_markets),
        candidates=len(candidates),
        cross_signals=cross_signals_count,
    )
    bot_status["candidates_found"] = len(candidates)

    if candidates:

@@ -211,20 +290,7 @@

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
@@ -245,16 +311,6 @@
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
@@ -265,22 +321,20 @@
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

                log_trade_csv(
                    "open",
                    er.market.market_id,
                    er.side,
                    sized.position_size,
                    best_ask
                )

                deployed += sized.position_size
                opens += 1

@@ -311,50 +365,41 @@
        if current_price is None:
            continue

        pnl_pct = (current_price - pos.entry_price) / max(pos.entry_price, 0.001)
        pnl = (current_price - pos.entry_price) * (
            pos.size / max(pos.entry_price, 0.001)
        )

        should_exit, exit_reason = _exit_signal(pos, current_price, pnl_pct)
        should_exit, exit_reason = _exit_signal(pos, current_price, pnl)

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
        log_trade_csv(
            "close",
            pos.market_id,
            pos.side,
            pos.size,
            current_price,
            pnl
        )

        portfolio.cancel_position(pos.position_id)


def _exit_signal(pos, current_price, pnl_pct):
def _exit_signal(pos, current_price, pnl):

    pnl_pct = pnl / max(pos.size, 0.001)

    if pnl_pct >= config.MAX_SLIPPAGE_PERCENT * 3:
        return True, f"take_profit pnl={pnl_pct:.2%}"
    if pnl_pct >= 0.20:
        return True, "take_profit"

    if pnl_pct <= -0.10:
        return True, f"stop_loss pnl={pnl_pct:.2%}"
        return True, "stop_loss"

    if current_price >= 0.95 or current_price <= 0.05:
        return True, f"resolution_proximity price={current_price:.3f}"

    age_sec = time.time() - getattr(pos, "opened_at", time.time())

    if age_sec > 72 * 3600:
        return True, f"max_age {age_sec/3600:.1f}h"
        return True, "resolution_proximity"

    return False, ""

@@ -384,11 +429,10 @@

if __name__ == "__main__":

    # Start health server for Railway
    threading.Thread(target=run_health_server, daemon=True).start()

    try:
        run()
    except KeyboardInterrupt:
        _log.info("KeyboardInterrupt — exiting.")
        sys.exit(0)
