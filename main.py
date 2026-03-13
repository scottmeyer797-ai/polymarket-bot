from __future__ import annotations

import os
import signal
import sys
import time
import threading
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


@app.route("/health")
def health():
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
# BOT IMPORTS
# -------------------------------------------------------------------

from polymarket_bot import config
from polymarket_bot import logging as log_mod
from polymarket_bot.market_scanner import MarketScanner
from polymarket_bot.liquidity_filter import LiquidityFilter
from polymarket_bot.edge_calculator import EdgeCalculator
from polymarket_bot.portfolio import Portfolio
from polymarket_bot.risk_manager import RiskManager
from polymarket_bot.trade_sizer import TradeSizer
from polymarket_bot.monte_carlo_validator import MonteCarloValidator
from polymarket_bot.trader import Trader

_log = log_mod.get_logger()

_running = True


# -------------------------------------------------------------------
# BOT RUN LOOP
# -------------------------------------------------------------------

def run():

    scanner = MarketScanner()
    liq_filt = LiquidityFilter()
    edge_calc = EdgeCalculator()
    portfolio = Portfolio()
    risk_mgr = RiskManager()
    sizer = TradeSizer()
    mc_val = MonteCarloValidator()
    trader = Trader()

    cached_cross_scores = {}

    cycle = 0

    while _running:

        cycle += 1

        cycle_start = time.monotonic()

        try:

            cross_signals_count = _run_cycle(
                cycle,
                scanner,
                liq_filt,
                edge_calc,
                portfolio,
                risk_mgr,
                sizer,
                mc_val,
                trader,
                cached_cross_scores,
            )

        except Exception as exc:

            log_mod.log_error(f"Unhandled error in cycle {cycle}", exc)
            cross_signals_count = 0

        elapsed = time.monotonic() - cycle_start

        bot_status["cycles"] += 1
        bot_status["cross_signals"] = cross_signals_count
        bot_status["open_positions"] = portfolio.open_position_count
        bot_status["deployed_capital"] = portfolio.deployed_capital
        bot_status["daily_pnl"] = risk_mgr.daily_pnl
        bot_status["last_cycle_time"] = round(elapsed, 3)

        sleep = max(0.0, config.SCAN_INTERVAL_SEC - elapsed)

        if _running:
            time.sleep(sleep)


# -------------------------------------------------------------------
# RUN SINGLE SCAN CYCLE
# -------------------------------------------------------------------

def _run_cycle(
    cycle,
    scanner,
    liq_filt,
    edge_calc,
    portfolio,
    risk_mgr,
    sizer,
    mc_val,
    trader,
    cached_cross_scores,
):

    if risk_mgr.circuit_breaker_tripped:

        trader.check_fills()
        trader.cancel_stale_orders()
        _check_exits(portfolio, risk_mgr, trader)

        return 0

    all_markets = scanner.get_markets()

    bot_status["markets_scanned"] = len(all_markets)

    liquid_markets = liq_filt.filter(all_markets)

    candidates = edge_calc.evaluate(
        liquid_markets,
        cross_market_scores=cached_cross_scores,
    )

    bot_status["candidates_found"] = len(candidates)

    cross_signals_count = 0

    for er in candidates:

        if portfolio.has_position_in_market(er.market.market_id):
            continue

        sized = sizer.size(er)

        if not sized.approved:
            continue

        mc = mc_val.validate(er)

        if not mc.passes:
            continue

        ok = trader.execute(sized)

        if ok:

            log_trade_csv(
                "open",
                er.market.market_id,
                er.side,
                sized.position_size,
                sized.entry_price
            )

    _check_exits(portfolio, risk_mgr, trader)

    return cross_signals_count


# -------------------------------------------------------------------
# EXIT CHECKER
# -------------------------------------------------------------------

def _check_exits(portfolio, risk_mgr, trader):

    for pos in portfolio.open_positions():

        current_price = trader.get_market_price(pos.market_id, pos.side)

        if current_price is None:
            continue

        pnl = (current_price - pos.entry_price) * (
            pos.size / max(pos.entry_price, 0.001)
        )

        should_exit, reason = _exit_signal(pos, current_price, pnl)

        if not should_exit:
            continue

        risk_mgr.record_closed_pnl(pnl)

        log_trade_csv(
            "close",
            pos.market_id,
            pos.side,
            pos.size,
            current_price,
            pnl
        )

        portfolio.cancel_position(pos.position_id)


# -------------------------------------------------------------------
# EXIT SIGNAL LOGIC
# -------------------------------------------------------------------

def _exit_signal(pos, current_price, pnl):

    pnl_pct = pnl / max(pos.size, 0.001)

    if pnl_pct >= 0.20:
        return True, "take_profit"

    if pnl_pct <= -0.10:
        return True, "stop_loss"

    if current_price >= 0.95 or current_price <= 0.05:
        return True, "resolution_proximity"

    return False, ""


# -------------------------------------------------------------------
# ENTRY POINT
# -------------------------------------------------------------------

if __name__ == "__main__":

    threading.Thread(target=run_health_server, daemon=True).start()

    try:
        run()
    except KeyboardInterrupt:
        _log.info("KeyboardInterrupt — exiting.")
        sys.exit(0)
