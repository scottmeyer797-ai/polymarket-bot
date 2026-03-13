from **future** import annotations

import os
import signal
import sys
import time
import threading
import csv
from datetime import datetime
from flask import Flask, jsonify

# ----------------------------------------------------------

# Flask server

# ----------------------------------------------------------

app = Flask(**name**)

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
return """ <html> <head> <title>Polymarket Bot Dashboard</title> <style>
body { background:#111; color:#eee; font-family:Arial; padding:40px }
h1 { color:#6cf }
.card { background:#1b1b1b; padding:20px; margin:10px; border-radius:8px } </style> </head> <body>

```
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
```

# ----------------------------------------------------------

# CSV trade logging

# ----------------------------------------------------------

def log_trade_csv(action, market_id, side, size, price, pnl=None):

```
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
```

# ----------------------------------------------------------

# Bot imports

# ----------------------------------------------------------

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

_log = log_mod.get_logger(**name**)
_running = True

# ----------------------------------------------------------

# graceful shutdown

# ----------------------------------------------------------

def _shutdown(signum, frame):
global _running
_log.info(f"Shutdown signal {signum}")
_running = False

signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT, _shutdown)

# ----------------------------------------------------------

# main bot loop

# ----------------------------------------------------------

def run():

```
scanner = MarketScanner()
liq_filt = LiquidityFilter()
edge_det = EdgeDetector()
cross_det = CrossMarketDetector()
mc_val = MonteCarloValidator()
portfolio = PortfolioManager()
risk_mgr = RiskManager()
trader = Trader(portfolio)

cached_cross_scores = {}

while _running:

    start = time.monotonic()

    markets = scanner.get_markets()
    bot_status["markets_scanned"] = len(markets)

    liquid = liq_filt.filter(markets)

    cross = cross_det.detect(liquid)
    bot_status["cross_signals"] = len(cross)

    for sig in cross:
        cached_cross_scores[sig.market_a.market_id] = sig.contradiction_score

    candidates = edge_det.detect(liquid, cross_market_scores=cached_cross_scores)
    bot_status["candidates_found"] = len(candidates)

    bot_status["cycles"] += 1

    elapsed = time.monotonic() - start
    bot_status["last_cycle_time"] = round(elapsed, 3)

    time.sleep(max(0, config.SCAN_INTERVAL_SEC - elapsed))
```

# ----------------------------------------------------------

# background thread launcher

# ----------------------------------------------------------

def start_bot():

```
time.sleep(3)

try:
    _log.info("Starting trading bot thread")
    run()
except Exception as e:
    _log.error(f"Bot crashed: {e}")
```

# ----------------------------------------------------------

# entry point

# ----------------------------------------------------------

if **name** == "**main**":

```
bot_thread = threading.Thread(target=start_bot, daemon=True)
bot_thread.start()

port = int(os.environ.get("PORT", 8080))

print(f"Starting Flask server on port {port}")

app.run(host="0.0.0.0", port=port)
```
