from __future__ import annotations

import os
import threading
import time
import csv
from datetime import datetime

from flask import Flask, jsonify

# --------------------------------------------------
# Flask Web Server (for Railway healthcheck)
# --------------------------------------------------

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


# --------------------------------------------------
# CSV Trade Logger
# --------------------------------------------------

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


# --------------------------------------------------
# BOT THREAD
# --------------------------------------------------

def run_bot():

    try:

        # Import bot modules INSIDE the thread
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

        scanner = MarketScanner()
        liq_filt = LiquidityFilter()
        edge_calc = EdgeCalculator()
        portfolio = Portfolio()
        risk_mgr = RiskManager()
        sizer = TradeSizer()
        mc_val = MonteCarloValidator()
        trader = Trader()

        cycle = 0

        while True:

            cycle += 1
            cycle_start = time.monotonic()

            try:

                all_markets = scanner.get_markets()

                bot_status["markets_scanned"] = len(all_markets)

                liquid_markets = liq_filt.filter(all_markets)

                candidates = edge_calc.evaluate(liquid_markets)

                bot_status["candidates_found"] = len(candidates)

            except Exception as exc:

                log_mod.log_error("Cycle error", exc)

            elapsed = time.monotonic() - cycle_start

            bot_status["cycles"] += 1
            bot_status["last_cycle_time"] = round(elapsed, 3)

            time.sleep(config.SCAN_INTERVAL_SEC)

    except Exception as e:

        print("BOT CRASHED:", e)


# --------------------------------------------------
# Start Bot Background Thread
# --------------------------------------------------

def start_bot():

    thread = threading.Thread(target=run_bot)
    thread.daemon = True
    thread.start()


start_bot()


# --------------------------------------------------
# Local Development
# --------------------------------------------------

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 8080))

    app.run(
        host="0.0.0.0",
        port=port
    )
