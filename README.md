# Polymarket Trading Bot — v2

Statistical arbitrage bot for Polymarket prediction markets.
Single-threaded, lightweight, deployable on Railway at **$5–15/month**.

---

## What Changed in v2

| # | Improvement | File(s) Modified |
|---|-------------|-----------------|
| 1 | Single-threaded event loop — no background threads | `main.py` |
| 2 | Student-t Monte Carlo (fat-tail distribution) | `monte_carlo.py`, `config.py` |
| 3 | Slippage protection vs live best ask | `trader.py`, `risk_manager.py`, `config.py` |
| 4 | Circuit breaker: daily loss limit + max open positions | `risk_manager.py`, `main.py`, `logger.py`, `config.py` |
| 5 | Cross-market contradiction detection | **`cross_market_detector.py` (new)**, `main.py` |
| 6 | Enhanced edge confidence: momentum + Z-score + cross score | `edge_detector.py` |
| 7 | Expanded structured logging with signal_type, PnL, skip reasons | `logger.py`, `trader.py` |
| 8 | Updated sizing: `base_risk × confidence × (edge / threshold)` | `risk_manager.py` |
| 9 | Performance guardrails: 10s scan, ≤500 MB RAM, <10% CPU | `main.py` (sequential loop) |

---

## Architecture

```
main.py                   ← Single event loop (no threads)
 │
 ├── MarketScanner         ← Gamma + CLOB API with caching
 ├── LiquidityFilter       ← Reject thin/wide markets
 ├── CrossMarketDetector   ← [NEW] Find probability contradictions
 ├── EdgeDetector          ← Fair-value model (5 signals)
 ├── MonteCarloValidator   ← Student-t EV simulation
 ├── RiskManager           ← Sizing + circuit breaker + slippage
 ├── Trader                ← Order placement + fill tracking
 └── PortfolioManager      ← P&L tracking + persistence
```

---

## Quick Start

```bash
git clone <repo> polymarket-bot && cd polymarket-bot
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # DRY_RUN=true by default
python main.py
```

---

## Railway Deployment

```bash
railway login && railway init
# Add all .env.example variables in Railway dashboard → Variables
git push && railway up
```

---

## New Environment Variables (v2)

| Variable | Default | Description |
|----------|---------|-------------|
| `MONTE_CARLO_DF` | `3` | Student-t degrees of freedom. Lower = fatter tails |
| `MAX_SLIPPAGE_PERCENT` | `0.03` | Max allowed slippage vs live best ask |
| `MAX_DAILY_LOSS_PERCENT` | `0.05` | Circuit breaker: fraction of total capital |
| `MIN_EXPECTED_RETURN` | `0.0` | Minimum MC mean EV to trade |
| `CROSS_MARKET_EDGE_THRESHOLD` | `0.10` | Min contradiction score for cross-market signal |

---

## Edge Model (v2)

Confidence = weighted sum of 6 components:

| Component | Weight | Source |
|-----------|--------|--------|
| Edge magnitude | 30% | `model_prob - market_prob` |
| Liquidity score | 20% | Log-normalised pool depth |
| Spread score | 15% | `1 - spread / MAX_SPREAD` |
| Price momentum | 15% | Distance × volume factor |
| Mean reversion | 10% | Z-score distance from 0.5 |
| Cross-market | 10% | Contradiction score from `CrossMarketDetector` |

---

## Monte Carlo (v2)

Uses **Student-t distribution** (default `df=3`).

Compared to Gaussian:
- Heavier tails model sudden news events
- More conservative: requires stronger edge to pass
- `df=3` ≈ common financial returns distribution
- Increase `MONTE_CARLO_DF` to reduce tail weight (df→∞ = Gaussian)

---

## Circuit Breaker

If cumulative daily P&L falls below `MAX_DAILY_LOSS_PERCENT × MAX_TOTAL_CAPITAL_DEPLOYED`:
- Bot stops opening new positions
- Fill checks and stale order cleanup continue
- Resets automatically at UTC midnight

---

## Cross-Market Detection

`cross_market_detector.py` scans liquid markets for:

1. **Complement pairs** — `P(A) + P(not-A)` should ≈ 1.0
2. **Correlated pairs** — Related markets diverging beyond threshold

Markets are clustered by shared keywords (election, crypto, sports, etc.).
Contradiction scores feed into EdgeDetector's confidence calculation.

---

## Log Format (v2)

Every trade log includes:
```json
{
  "ts": "2025-01-15T14:23:01Z",
  "msg": "order_placed",
  "action": "order_placed",
  "market_id": "0xabc...",
  "signal_type": "cross_market",
  "side": "YES",
  "edge": 0.12,
  "confidence": 0.74,
  "position_size": 18.5,
  "entry_price": 0.41,
  "exit_price": null,
  "pnl": null,
  "best_ask": 0.42
}
```

Skipped trades log their reason:
```json
{
  "msg": "trade_skipped",
  "skip_reason": "slippage=0.045 > MAX_SLIPPAGE_PERCENT=0.030",
  "market_id": "0xdef...",
  "edge": 0.09
}
```

---

## Disclaimer

For research and educational use. Prediction markets carry significant risk. Always run `DRY_RUN=true` first.
