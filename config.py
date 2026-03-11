"""config.py — Central configuration. All params via environment variables."""
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
    return os.environ.get(k, str(d)).lower() in ("1","true","yes")

# ── API endpoints ─────────────────────────────────────────────────────────────
POLYMARKET_API_BASE   = _s("POLYMARKET_API_BASE",  "https://clob.polymarket.com")
GAMMA_API_BASE        = _s("GAMMA_API_BASE",        "https://gamma-api.polymarket.com")

# ── Wallet / Auth ─────────────────────────────────────────────────────────────
PRIVATE_KEY           = _s("PRIVATE_KEY")
WALLET_ADDRESS        = _s("WALLET_ADDRESS")
POLYMARKET_API_KEY    = _s("POLYMARKET_API_KEY")
POLYMARKET_SECRET     = _s("POLYMARKET_SECRET")
POLYMARKET_PASSPHRASE = _s("POLYMARKET_PASSPHRASE")

# ── Capital ───────────────────────────────────────────────────────────────────
MAX_CAPITAL_PER_TRADE      = _f("MAX_CAPITAL_PER_TRADE",      25.0)
MAX_TOTAL_CAPITAL_DEPLOYED = _f("MAX_TOTAL_CAPITAL_DEPLOYED", 200.0)
BASE_RISK                  = _f("BASE_RISK",                   10.0)

# ── Edge & confidence ─────────────────────────────────────────────────────────
EDGE_THRESHOLD             = _f("EDGE_THRESHOLD",              0.08)
CONFIDENCE_THRESHOLD       = _f("CONFIDENCE_THRESHOLD",        0.60)
MIN_EXPECTED_RETURN        = _f("MIN_EXPECTED_RETURN",         0.0)   # IMPROVEMENT 4

# ── Liquidity ─────────────────────────────────────────────────────────────────
MIN_MARKET_LIQUIDITY       = _f("MIN_MARKET_LIQUIDITY",        500.0)
MAX_SPREAD                 = _f("MAX_SPREAD",                  0.06)
MIN_VOLUME_24H             = _f("MIN_VOLUME_24H",              1000.0)

# ── Monte Carlo ───────────────────────────────────────────────────────────────
MC_ITERATIONS              = _i("MC_ITERATIONS",               1000)
MC_SIGMA                   = _f("MC_SIGMA",                    0.05)
MONTE_CARLO_DF             = _f("MONTE_CARLO_DF",              3.0)   # IMPROVEMENT 2: Student-t df

# ── Slippage protection ───────────────────────────────────────────────────────
MAX_SLIPPAGE_PERCENT       = _f("MAX_SLIPPAGE_PERCENT",        0.03)  # IMPROVEMENT 3

# ── Circuit breaker ───────────────────────────────────────────────────────────
MAX_DAILY_LOSS_PERCENT     = _f("MAX_DAILY_LOSS_PERCENT",      0.05)  # IMPROVEMENT 4: 5% daily loss
MAX_OPEN_POSITIONS         = _i("MAX_OPEN_POSITIONS",          10)    # IMPROVEMENT 4

# ── Cross-market ──────────────────────────────────────────────────────────────
CROSS_MARKET_EDGE_THRESHOLD = _f("CROSS_MARKET_EDGE_THRESHOLD", 0.10) # IMPROVEMENT 5

# ── Scanning ──────────────────────────────────────────────────────────────────
SCAN_INTERVAL_SEC          = _i("SCAN_INTERVAL_SEC",           10)
ORDER_STALE_SEC            = _i("ORDER_STALE_SEC",             120)
API_MAX_RETRIES            = _i("API_MAX_RETRIES",             4)
API_RETRY_BACKOFF          = _f("API_RETRY_BACKOFF",           2.0)

# ── Misc ──────────────────────────────────────────────────────────────────────
DRY_RUN                    = _b("DRY_RUN",                     True)
LOG_LEVEL                  = _s("LOG_LEVEL",                   "INFO")
LOG_FILE                   = _s("LOG_FILE",                    "bot.log")
