from **future** import annotations

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

# -------------------------------------------------------------------

# CSV Trade Logger

# -------------------------------------------------------------------

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

_log = log_mod.get_logger(**name**)
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

```
_log.info(
    "Polymarket Bot starting",
    extra={
        "_dry_run": config.DRY_RUN,
        "_edge_threshold": config.EDGE_THRESHOLD,
        "_confidence_thresh": config.CONFIDENCE_THRESHOLD,
        "_max_capital": config.MAX_TOTAL_CAPITAL_DEPLOYED,
        "_scan_interval": config.SCAN_INTERVAL_SEC,
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

_log.info("Bot stopped cleanly.")
```

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

```
all_markets = scanner.get_markets()

bot_status["markets_scanned"] = len(all_markets)

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

bot_status["candidates_found"] = len(candidates)

if candidates:

    deployed = portfolio.deployed_capital
    opens = portfolio.open_position_count

    for er in candidates:

        if portfolio.has_position_in_market(er.market.market_id):
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
            continue

        mc = mc_val.validate(
            model_prob=er.model_prob,
            market_price=er.market_prob,
            position_size=sized.position_size,
            best_ask=best_ask if best_ask > 0 else None,
        )

        if not mc.passes:
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

        if deployed >= config.MAX_TOTAL_CAPITAL_DEPLOYED:
            break

trader.check_fills()
trader.cancel_stale_orders()

_check_exits(portfolio, risk_mgr, trader)

return cross_signals_count
```

# -------------------------------------------------------------------

# Position monitoring

# -------------------------------------------------------------------

def _check_exits(portfolio, risk_mgr, trader):

```
for pos in list(portfolio.open_positions):

    if not pos.filled:
        continue

    current_price = _get_current_price(pos.token_id)

    if current_price is None:
        continue

    pnl = (current_price - pos.entry_price) * (
        pos.size / max(pos.entry_price, 0.001)
    )

    should_exit, exit_reason = _exit_signal(pos, current_price, pnl)

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
```

def _exit_signal(pos, current_price, pnl):

```
pnl_pct = pnl / max(pos.size, 0.001)

if pnl_pct >= 0.20:
    return True, "take_profit"

if pnl_pct <= -0.10:
    return True, "stop_loss"

if current_price >= 0.95 or current_price <= 0.05:
    return True, "resolution_proximity"

return False, ""
```

def _get_current_price(token_id):

```
from utils import safe_get

try:

    url = f"{config.POLYMARKET_API_BASE}/mid-point"

    resp = safe_get(url, params={"token_id": token_id}, timeout=8)

    if resp:
        return float(resp.get("mid", 0) or 0) or None

except Exception:
    pass

return None
```

# -------------------------------------------------------------------

# Entry point

# -------------------------------------------------------------------

def start_bot():
"""Runs the trading bot loop."""
try:
run()
except Exception as e:
_log.error(f"Bot thread crashed: {e}")

if **name** == "**main**":

```
bot_thread = threading.Thread(target=start_bot, daemon=True)
bot_thread.start()

port = int(os.environ.get("PORT", 8080))
_log.info(f"Starting Flask health server on port {port}")

try:
    app.run(host="0.0.0.0", port=port)
except KeyboardInterrupt:
    _log.info("KeyboardInterrupt — shutting down.")
    sys.exit(0)
```
