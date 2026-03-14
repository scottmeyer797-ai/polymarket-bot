"""
config.py — Central configuration for Polymarket trading bot.
All values are kept from the working version, with the tuned
liquidity/edge settings preserved from your edits.

CACHE BUST: v3 — forces __pycache__ invalidation on redeploy
"""

import os
from dotenv import load_dotenv
load_dotenv()

def _f(k, d):
    try: return float(os.environ[k])
    except: return d

def _i(k, d):
    try: return int(os.environ[k])
    except: return d

def _s(k, d=""):
    return os.environ.get(k, d)

def _b(k, d=False):
    return os.environ.get(k, str(d)).lower() in ("1", "true", "yes")

# ── API endpoints ──────────────────────────────────────────────────────────────
POLYMARKET_API_BASE   = _s("POLYMARKET_API_BASE",  "https://clob.polymarket.com")
GAMMA_API_BASE        = _s("GAMMA_API_BASE",        "https://gamma-api.polymarket.com")

# ── Wallet / Auth ──────────────────────────────────────────────────────────────
PRIVATE_KEY           = _s("PRIVATE_KEY")
WALLET_ADDRESS        = _s("WALLET_ADDRESS")
POLYMARKET_API_KEY    = _s("POLYMARKET_API_KEY")
POLYMARKET_SECRET     = _s("POLYMARKET_SECRET")
POLYMARKET_PASSPHRASE = _s("POLYMARKET_PASSPHRASE")

# ── Scanning ───────────────────────────────────────────────────────────────────
SCAN_INTERVAL_SEC     = _i("SCAN_INTERVAL_SEC",    30)
ORDER_STALE_SEC       = _i("ORDER_STALE_SEC",      120)
API_MAX_RETRIES       = _i("API_MAX_RETRIES",      4)
API_RETRY_BACKOFF     = _f("API_RETRY_BACKOFF",    2.0)

# ── Liquidity filter ───────────────────────────────────────────────────────────
MIN_MARKET_LIQUIDITY  = _f("MIN_MARKET_LIQUIDITY", 800.0)
MIN_VOLUME_24H        = _f("MIN_VOLUME_24H",        200.0)
MAX_SPREAD            = _f("MAX_SPREAD",            0.08)

# ── Edge detection ─────────────────────────────────────────────────────────────
EDGE_THRESHOLD        = _f("EDGE_THRESHOLD",        0.001)
CONFIDENCE_THRESHOLD  = _f("CONFIDENCE_THRESHOLD",  0.10)

# ── Capital ────────────────────────────────────────────────────────────────────
BASE_RISK                  = _f("BASE_RISK",                   10.0)
MAX_CAPITAL_PER_TRADE      = _f("MAX_CAPITAL_PER_TRADE",       100.0)
MAX_TOTAL_CAPITAL_DEPLOYED = _f("MAX_TOTAL_CAPITAL_DEPLOYED",  200.0)

# ── Risk controls ──────────────────────────────────────────────────────────────
MAX_OPEN_POSITIONS         = _i("MAX_OPEN_POSITIONS",          10)
MAX_DAILY_LOSS_PERCENT     = _f("MAX_DAILY_LOSS_PERCENT",      0.05)
MAX_SLIPPAGE_PERCENT       = _f("MAX_SLIPPAGE_PERCENT",        0.03)
MIN_EXPECTED_RETURN        = _f("MIN_EXPECTED_RETURN",         0.0)

# ── Monte Carlo ────────────────────────────────────────────────────────────────
MC_ITERATIONS         = _i("MC_ITERATIONS",         500)
MC_SIGMA              = _f("MC_SIGMA",               0.05)
MONTE_CARLO_DF        = _f("MONTE_CARLO_DF",         3.0)

# ── Cross-market ───────────────────────────────────────────────────────────────
CROSS_MARKET_EDGE_THRESHOLD = _f("CROSS_MARKET_EDGE_THRESHOLD", 0.10)

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_LEVEL             = _s("LOG_LEVEL",  "INFO")
LOG_FILE              = _s("LOG_FILE",   "bot.log")

# ── Mode ───────────────────────────────────────────────────────────────────────
DRY_RUN               = _b("DRY_RUN",   True)
