"""
config.py — Global configuration (SAFE + STRATEGY READY)
"""

import os


# ---------- CORE BOT SETTINGS ----------
SCAN_INTERVAL_SEC = int(os.getenv("SCAN_INTERVAL_SEC", 15))  # loop speed (safe default)

MAX_TOTAL_CAPITAL_DEPLOYED = float(os.getenv("MAX_TOTAL_CAPITAL_DEPLOYED", 1000))
MAX_CONCURRENT_POSITIONS   = int(os.getenv("MAX_CONCURRENT_POSITIONS", 5))


# ---------- TRADE SIZING ----------
BASE_POSITION_SIZE = float(os.getenv("BASE_POSITION_SIZE", 50))  # per trade

MIN_POSITION_SIZE  = float(os.getenv("MIN_POSITION_SIZE", 10))
MAX_POSITION_SIZE  = float(os.getenv("MAX_POSITION_SIZE", 200))


# ---------- RISK MANAGEMENT ----------
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", 200))
CIRCUIT_BREAKER_ENABLED = True


# ---------- STRATEGY SETTINGS (NEW EDGE) ----------

# Minimum confidence to take a trade
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", 0.55))

# Minimum edge required
MIN_EDGE = float(os.getenv("MIN_EDGE", 0.05))

# Retracement requirement (your rule)
REQUIRE_50_RETRACEMENT = True


# ---------- MARKET FILTERS ----------
MIN_MARKET_PRICE = 0.05   # avoid extreme odds
MAX_MARKET_PRICE = 0.95

MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 1000))


# ---------- BINANCE SETTINGS ----------
BINANCE_SYMBOL = os.getenv("BINANCE_SYMBOL", "BTCUSDT")

H4_INTERVAL  = "4h"
M15_INTERVAL = "15m"

CANDLE_LIMIT = 100


# ---------- FAILSAFE ----------
def validate_config():
    try:
        assert SCAN_INTERVAL_SEC > 0
        assert MAX_TOTAL_CAPITAL_DEPLOYED > 0
        assert MAX_CONCURRENT_POSITIONS > 0
        assert MIN_POSITION_SIZE > 0
        assert MAX_POSITION_SIZE >= MIN_POSITION_SIZE
    except Exception as e:
        print(f"Config validation warning: {e}")


# Run validation (safe)
validate_config()
