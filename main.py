"""
main.py — Flask dashboard + single-threaded bot loop.

Fixes applied:
  - Removed broken `from polymarket_bot import ...` package imports
  - Corrected module names to match actual flat file structure
  - Wired bot_status to real module output values
  - Bot thread failure no longer silently zeros all metrics
"""
from __future__ import annotations

import csv
import os
import threading
import time
from datetime import datetime

from flask import Flask, jsonify

# ─── Flask app ────────────────────────────────────────────────────────────────

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


@app.route("/dashboard")
def dashboard():
    return """<!DOCTYPE html>
<html>
<head>
    <title>Polymarket Bot</title>
    <meta charset="utf-8">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #0d0d0d; color: #e0e0e0; font-family: 'Segoe UI', Arial, sans-serif; padding: 32px; }
        h1 { color: #66ccff; font-size: 1.6rem; margin-bottom: 24px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
        .card {
            background: #1a1a1a; border: 1px solid #2a2a2a;
            border-radius: 10px; padding: 18px 20px;
        }
        .card .label { font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 0.05em; }
        .card .value { font-size: 1.4rem; font-weight: 600; margin-top: 6px; color: #fff; }
        .card.green .value { color: #4caf50; }
        .card.red   .value { color: #f44336; }
        .card.blue  .value { color: #66ccff; }
        .status-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
                      background: #f44336; margin-right: 8px; }
        .status-dot.on { background: #4caf50; }
        #error-bar { display: none; background: #3a1a1a; border: 1px solid #f44336;
                     color: #f44336; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; }
        .updated { font-size: 0.75rem; color: #555; margin-top: 20px; }
    </style>
</head>
<body>
    <h1>&#x1F4C8; Polymarket Trading Bot</h1>
    <div id="error-bar"></div>
    <div class="grid" id="grid"></div>
    <div class="updated" id="updated"></div>

<script>
const FIELDS = [
    { key: "running",          label: "Bot Running",        fmt: v => v ? "YES" : "NO",     cls: v => v ? "green" : "red" },
    { key: "cycles",           label: "Total Cycles",       fmt: v => v,                    cls: _ => "blue" },
    { key: "markets_scanned",  label: "Markets Scanned",    fmt: v => v,                    cls: _ => "" },
    { key: "liquid_markets",   label: "Liquid Markets",     fmt: v => v,                    cls: _ => "" },
    { key: "candidates_found", label: "Edge Candidates",    fmt: v => v,                    cls: _ => "" },
    { key: "cross_signals",    label: "Cross Signals",      fmt: v => v,                    cls: _ => "" },
    { key: "open_positions",   label: "Open Positions",     fmt: v => v,                    cls: _ => "blue" },
    { key: "deployed_capital", label: "Deployed ($)",       fmt: v => "$" + v.toFixed(2),   cls: _ => "blue" },
    { key: "realized_pnl",     label: "Realised PnL ($)",   fmt: v => "$" + v.toFixed(2),   cls: v => v >= 0 ? "green" : "red" },
    { key: "daily_pnl",        label: "Daily PnL ($)",      fmt: v => "$" + v.toFixed(2),   cls: v => v >= 0 ? "green" : "red" },
    { key: "circuit_breaker",  label: "Circuit Breaker",    fmt: v => v ? "TRIPPED" : "OK", cls: v => v ? "red" : "green" },
    { key: "last_cycle_secs",  label: "Last Cycle (s)",     fmt: v => v.toFixed(3) + "s",   cls: _ => "" },
];

async function load() {
    try {
        const r = await fetch('/api/status');
        if (!r.ok) throw new Error("HTTP " + r.status);
        const d = await r.json();

        const errBar = document.getElementById('error-bar');
        if (d.error) {
            errBar.style.display = 'block';
            errBar.textContent = '⚠ ' + d.error;
        } else {
            errBar.style.display = 'none';
        }

        const grid = document.getElementById('grid');
        grid.innerHTML = FIELDS.map(f => {
            const val = d[f.key] ?? 0;
            const cls = f.cls(val);
            return `<div class="card ${cls}">
                <div class="label">${f.label}</div>
                <div class="value">${f.fmt(val)}</div>
            </div>`;
        }).join('');

        document.getElementById('updated').textContent =
            'Last updated: ' + (d.last_updated || new Date().toISOString());
    } catch(e) {
        document.getElementById('error-bar').style.display = 'block';
        document.getElementById('error-bar').textContent = '⚠ Could not reach /api/status — ' + e.message;
    }
}

load();
setInterval(load, 5000);
</script>
</body>
</html>"""


# ─── CSV trade logger ─────────────────────────────────────────────────────────

def log_trade_csv(action, market_id, side, size, price, pnl=None):
    file_exists = os.path.isfile("trade_log.csv")
    with open("trade_log.csv", "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "action", "market_id",
                             "side", "size", "price", "pnl"])
        writer.writerow([datetime.utcnow().isoformat(),
                         action, market_id, side, size, price, pnl])


# ─── Bot thread ───────────────────────────────────────────────────────────────

def run_bot():
    """
    Single bot loop. Imports are flat (no polymarket_bot package prefix).
    All actual module names match the files on disk.
    """
    try:
        # ── Flat imports — files live alongside main.py ────────────────────────
        import config
        import logger as log_mod
        from market_scanner import MarketScanner
        from liquidity_filter import LiquidityFilter
        from cross_market_detector import CrossMarketDetector
        from edge_detector import EdgeDetector
        from monte_carlo import MonteCarloValidator
        from risk_manager import RiskManager
        from portfolio_manager import PortfolioManager
        from trader import Trader

        _log = log_mod.get_logger(__name__)

        scanner   = MarketScanner()
        liq_filt  = LiquidityFilter()
        cross_det = CrossMarketDetector()
        edge_det  = EdgeDetector()
        mc_val    = MonteCarloValidator()
        portfolio = PortfolioManager()
        risk_mgr  = RiskManager()
        trader    = Trader(portfolio)

        bot_status["running"] = True
        bot_status["error"]   = ""

        # ── Verify correct module versions are loaded ──────────────────────
        import hashlib, inspect
        ed_src = inspect.getsource(EdgeDetector)
        ed_hash = hashlib.md5(ed_src.encode()).hexdigest()[:8]
        has_new = "spread_edge" in ed_src
        print(f"EDGE_DETECTOR_HASH={ed_hash} has_new_spread_logic={has_new}", flush=True)
        _log.info(f"edge_detector version check: hash={ed_hash} spread_logic={has_new}",
                  extra={"_event": "version_check", "_ed_hash": ed_hash, "_has_spread_logic": has_new})

        # ── Force clear any stale pyc ──────────────────────────────────────
        import shutil, pathlib
        for p in pathlib.Path(".").rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)

        _log.info("Bot thread started successfully.")

        cached_cross_scores: dict[str, float] = {}
        cycle = 0

        while True:
            cycle      += 1
            cycle_start = time.monotonic()

            try:
                # ── Scan ──────────────────────────────────────────────────────
                all_markets    = scanner.get_markets()
                liquid_markets = liq_filt.filter(all_markets)

                # ── Cross-market (every 3rd cycle) ────────────────────────────
                cross_count = 0
                if cycle % 3 == 0 and liquid_markets:
                    cross_signals = cross_det.detect(liquid_markets)
                    cross_count   = len(cross_signals)
                    cached_cross_scores.clear()
                    for sig in cross_signals:
                        mid = sig.market_a.market_id
                        cached_cross_scores[mid] = max(
                            cached_cross_scores.get(mid, 0.0),
                            sig.contradiction_score,
                        )

                # ── Edge detection ────────────────────────────────────────────
                candidates = edge_det.detect(
                    liquid_markets,
                    cross_market_scores=cached_cross_scores,
                )

                # ── Trade cycle ───────────────────────────────────────────────
                deployed = portfolio.deployed_capital
                opens    = portfolio.open_position_count

                for er in candidates:
                    if portfolio.has_position_in_market(er.market.market_id):
                        continue

                    token_idx = 0 if er.side == "YES" else 1
                    token_id  = (er.market.token_ids[token_idx]
                                 if token_idx < len(er.market.token_ids) else "")
                    best_ask  = trader.get_best_ask(token_id) if token_id else 0.0

                    sized = risk_mgr.size_trade(er, deployed, opens, best_ask=best_ask)
                    if not sized.approved:
                        log_mod.log_skipped_trade(
                            er.market.market_id, er.side, sized.reject_reason,
                            er.edge, er.confidence, er.signal_type,
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
                            er.market.market_id, er.side,
                            f"monte_carlo: {mc.reject_reason}",
                            er.edge, er.confidence, er.signal_type,
                        )
                        continue

                    ok = trader.execute(sized)
                    if ok:
                        deployed += sized.position_size
                        opens    += 1
                        log_trade_csv(
                            "order_placed", er.market.market_id,
                            er.side, sized.position_size, sized.limit_price,
                        )

                    if deployed >= config.MAX_TOTAL_CAPITAL_DEPLOYED:
                        break

                # ── Fills + cleanup ───────────────────────────────────────────
                trader.check_fills()
                trader.cancel_stale_orders()

                # ── Update shared status dict ─────────────────────────────────
                summary = portfolio.summary()
                bot_status.update({
                    "cycles":           cycle,
                    "markets_scanned":  len(all_markets),
                    "liquid_markets":   len(liquid_markets),
                    "candidates_found": len(candidates),
                    "cross_signals":    cross_count,
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
                err_msg = f"{type(exc).__name__}: {exc}"
                bot_status["error"] = err_msg
                log_mod.log_error("Cycle error", exc)

            elapsed = time.monotonic() - cycle_start
            time.sleep(max(0.0, config.SCAN_INTERVAL_SEC - elapsed))

    except Exception as e:
        # Capture startup crash — visible in dashboard error bar
        err_msg = f"BOT STARTUP FAILED: {type(e).__name__}: {e}"
        bot_status["running"] = False
        bot_status["error"]   = err_msg
        print(err_msg)


# ─── Start ────────────────────────────────────────────────────────────────────

def start_bot():
    t = threading.Thread(target=run_bot, name="bot", daemon=True)
    t.start()


start_bot()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
