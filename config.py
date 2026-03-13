"""
config.py — Central configuration for the Polymarket bot.
All parameters are loaded from environment variables with safe defaults.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ----------------------------------------------------
# Helper functions for environment variable parsing
# ----------------------------------------------------

def _f(key, default):
    """Read float from env."""
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _i(key, default):
    """Read int from env."""
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _s(key, default=""):
    """Read string from env."""
    return os.environ.get(key, default)


def _b(key, default=False):
    """Read boolean from env."""
    return os.environ.get(key, str(default)).lower() in ("1", "true", "yes")


# ----------------------------------------------------
# API Endpoints
# ----------------------------------------------------

POLYMARKET_API_BASE = _s("POLYMARKET_API_BASE", "https://clob.polymarket.com")
GAMMA_API_BASE = _s("GAMMA_API_BASE", "https://gamma-api.polymarket.com")


# ----------------------------------------------------
# Wallet / Authentication
# ----------------------------------------------------

PRIVATE_KEY = _s("PRIVATE_KEY")
WALLET_ADDRESS = _s("WALLET_ADDRESS")

POLYMARKET_API_KEY = _s("POLYMARKET_API_KEY")
POLYMARKET_SECRET = _s("POLYMARKET_SECRET")
POLYMARKET_PASSPHRASE = _s("POLYMARKET_PASSPHRASE")


# ----------------------------------------------------
# Capital Management
# ----------------------------------------------------

MAX_CAPITAL_PER_TRADE = _f("MAX_CAPITAL_PER_TRADE", 20.0)
MAX_TOTAL_CAPITAL_DEPLOYED = _f("MAX_TOTAL_CAPITAL_DEPLOYED", 200.0)
BASE_RISK = _f("BASE_RISK", 10.0)


# ----------------------------------------------------
# Edge & Confidence
# ----------------------------------------------------

EDGE_THRESHOLD = _f("EDGE_THRESHOLD", 0.05)
CONFIDENCE_THRESHOLD = _f("CONFIDENCE_THRESHOLD", 0.55)
MIN_EXPECTED_RETURN = _f("MIN_EXPECTED_RETURN", 0.01)


# ----------------------------------------------------
# Liquidity Filters
# ----------------------------------------------------

MIN_MARKET_LIQUIDITY = _f("MIN_MARKET_LIQUIDITY", 250.0)
MAX_SPREAD = _f("MAX_SPREAD", 0.08)
MIN_VOLUME_24H = _f("MIN_VOLUME_24H", 500.0)


# ----------------------------------------------------
# Monte Carlo Simulation
# ----------------------------------------------------

MC_ITERATIONS = _i("MC_ITERATIONS", 800)
MC_SIGMA = _f("MC_SIGMA", 0.05)
MONTE_CARLO_DF = _f("MONTE_CARLO_DF", 3.0)


# ----------------------------------------------------
# Slippage Protection
# ----------------------------------------------------

MAX_SLIPPAGE_PERCENT = _f("MAX_SLIPPAGE_PERCENT", 0.03)


# ----------------------------------------------------
# Circuit Breaker
# ----------------------------------------------------

MAX_DAILY_LOSS_PERCENT = _f("MAX_DAILY_LOSS_PERCENT", 0.05)
MAX_OPEN_POSITIONS = _i("MAX_OPEN_POSITIONS", 10)


# ----------------------------------------------------
# Cross-Market Arbitrage
# ----------------------------------------------------

CROSS_MARKET_EDGE_THRESHOLD = _f("CROSS_MARKET_EDGE_THRESHOLD", 0.07)


# ----------------------------------------------------
# Market Scanning
# ----------------------------------------------------

SCAN_INTERVAL_SEC = _i("SCAN_INTERVAL_SEC", 60)
ORDER_STALE_SEC = _i("ORDER_STALE_SEC", 180)

API_MAX_RETRIES = _i("API_MAX_RETRIES", 4)
API_RETRY_BACKOFF = _f("API_RETRY_BACKOFF", 2.0)


# ----------------------------------------------------
# Runtime Settings
# ----------------------------------------------------

DRY_RUN = _b("DRY_RUN", True)

LOG_LEVEL = _s("LOG_LEVEL", "INFO")
LOG_FILE = _s("LOG_FILE", "bot.log")
