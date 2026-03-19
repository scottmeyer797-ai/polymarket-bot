"""
main.py — Flask dashboard + single-threaded bot loop.
"""
from __future__ import annotations

import csv
import os
import threading
import time
from datetime import datetime

from flask import Flask, jsonify

app = Flask(__name__)

bot_status = {
    "running":          False,
    "cycles":           0,
    "markets_scanned":  0,
    "liquid_markets":   0,
    "candidates_found": 0,
    "cross_signals":    0,
    "open_positions":   0,
    "deployed_capital": 0.0,
    "realized_pnl":     0.0,
    "daily_pnl":        0.0,
    "circuit_breaker":  False,
    "last_cycle_secs":  0.0,
    "last_updated":     "",
    "error":            "",
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


# ---------------- CSV LOG ----------------
def log_trade_csv(action, market_id, side, size, price, pnl=None):
    file_exists = os.path.isfile("trade_log.csv")
    with open("trade_log.csv", "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "action", "market_id", "side", "size", "price", "pnl"])
        writer.writerow([datetime.utcnow().isoformat(), action, market_id, side, size, price, pnl])


# ---------------- BOT ----------------
def run_bot():
    try:
        import config
        import logger as log_mod
        from market_scanner import MarketScanner
        from opportunity_engine import OpportunityEngine
        from risk_manager import RiskManager
        from portfolio_manager import PortfolioManager
        from trader import Trader

        _log = log_mod.get_logger(__name__)

        # INIT
        opportunity_engine = OpportunityEngine()
        scanner   = MarketScanner(None, opportunity_engine)
        portfolio = PortfolioManager()
        risk_mgr  = RiskManager()
        trader    = Trader(portfolio)

        bot_status["running"] = True
        bot_status["error"]   = ""

        _log.info("Bot thread started (NEW STRATEGY).")

        cycle = 0

        while True:
            cycle += 1
            cycle_start = time.monotonic()

            try:
                opportunities = scanner.scan_markets()

                deployed = portfolio.deployed_capital
                opens    = portfolio.open_position_count

                for opp in opportunities:
                    market_id = opp.get("market_id")

                    if portfolio.has_position_in_market(market_id):
                        continue

                    # Convert to expected structure
                    class SimpleEdge:
                        def __init__(self, opp):
                            self.market = type("M", (), {
                                "market_id": market_id,
                                "token_ids": ["", ""]
                            })
                            self.side = "YES" if opp["type"] == "BUY_YES" else "NO"
                            self.edge = 0.1
                            self.confidence = 0.6
                            self.signal_type = "trend_bos"
                            self.model_prob = 0.6
                            self.market_prob = opp["entry_price"]

                    er = SimpleEdge(opp)

                    sized = risk_mgr.size_trade(er, deployed, opens, best_ask=0.0)

                    if not sized.approved:
                        continue

                    ok = trader.execute(sized)

                    if ok:
                        deployed += sized.position_size
                        opens += 1
                        log_trade_csv(
                            "order_placed",
                            market_id,
                            er.side,
                            sized.position_size,
                            sized.limit_price,
                        )

                    if deployed >= config.MAX_TOTAL_CAPITAL_DEPLOYED:
                        break

                trader.check_fills()
                trader.cancel_stale_orders()

                summary = portfolio.summary()

                bot_status.update({
                    "cycles":           cycle,
                    "markets_scanned":  len(opportunities),
                    "liquid_markets":   len(opportunities),
                    "candidates_found": len(opportunities),
                    "cross_signals":    0,
                    "open_positions":   summary["open_positions"],
                    "deployed_capital": summary["deployed_capital"],
                    "realized_pnl":     summary["realized_pnl"],
                    "daily_pnl":        round(risk_mgr.daily_pnl, 4),
                    "circuit_breaker":  risk_mgr.circuit_breaker_tripped,
                    "last_cycle_secs":  round(time.monotonic() - cycle_start, 3),
                    "last_updated":     datetime.utcnow().isoformat() + "Z",
                    "error":            "",
                })

            except Exception as exc:
                bot_status["error"] = f"{type(exc).__name__}: {exc}"
                _log.error(f"Cycle error: {exc}")

            elapsed = time.monotonic() - cycle_start
            time.sleep(max(0.0, config.SCAN_INTERVAL_SEC - elapsed))

    except Exception as e:
        bot_status["running"] = False
        bot_status["error"]   = f"STARTUP ERROR: {e}"
        print(f"Startup error: {e}", flush=True)


def start_bot():
    try:
        t = threading.Thread(target=run_bot, name="bot", daemon=True)
        t.start()
    except Exception as e:
        print(f"Bot thread failed to start: {e}", flush=True)


# SAFE START
start_bot()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
