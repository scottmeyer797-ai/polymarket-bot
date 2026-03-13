"""
config.py — Central configuration for Polymarket trading bot.
"""

# --------------------------------------------------
# Scan Settings
# --------------------------------------------------

SCAN_INTERVAL_SEC = 30


# --------------------------------------------------
# Liquidity Filter Settings
# --------------------------------------------------
# These were lowered to match real Polymarket market conditions.
# This will allow more markets through the filter without
# accepting illiquid garbage markets.

MIN_MARKET_LIQUIDITY = 800      # previously likely too high
MIN_VOLUME_24H = 200            # allow smaller but active markets
MAX_SPREAD = 0.08               # allow wider spreads (Polymarket often 0.03–0.07)


# --------------------------------------------------
# Edge Detection Settings
# --------------------------------------------------
# Real inefficiencies are usually small in prediction markets.
# Lowering these allows the model to detect more opportunities.

EDGE_THRESHOLD = 0.01           # 1% edge
CONFIDENCE_THRESHOLD = 0.45     # lower confidence requirement


# --------------------------------------------------
# Trade Sizing
# --------------------------------------------------

MAX_POSITION_SIZE = 100
MIN_POSITION_SIZE = 5


# --------------------------------------------------
# Risk Controls
# --------------------------------------------------

MAX_OPEN_POSITIONS = 10
MAX_DAILY_LOSS = -200


# --------------------------------------------------
# Monte Carlo Settings
# --------------------------------------------------

MC_SIMULATIONS = 500


# --------------------------------------------------
# Logging
# --------------------------------------------------

LOG_LEVEL = "INFO"
