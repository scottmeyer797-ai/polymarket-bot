import requests
import time


class MarketScanner:

    def __init__(self, polymarket_client, opportunity_engine):
        self.opportunity_engine = opportunity_engine

    # ---------- POLYMARKET DATA ----------
    def get_polymarket_markets(self):
        try:
            url = "https://gamma-api.polymarket.com/markets"
            response = requests.get(url, timeout=5)

            if response.status_code != 200:
                print(f"Polymarket API error: {response.status_code}")
                return []

            data = response.json()

            markets = []

            for m in data:
                try:
                    if not m.get("active", False):
                        continue

                    outcomes = m.get("outcomes", [])

                    if len(outcomes) < 2:
                        continue

                    yes_price = float(outcomes[0].get("price", 0))
                    no_price  = float(outcomes[1].get("price", 0))

                    # Basic validation
                    if not (0 < yes_price < 1 and 0 < no_price < 1):
                        continue

                    markets.append({
                        "id": m.get("id"),
                        "question": m.get("question", ""),
                        "yes_price": yes_price,
                        "no_price": no_price
                    })

                except Exception:
                    continue

            return markets

        except Exception as e:
            print(f"Polymarket fetch error: {e}")
            return []

    # ---------- BINANCE DATA ----------
    def get_binance_candles(self, interval="15m", limit=100):
        try:
            url = "https://api.binance.com/api/v3/klines"
            params = {
                "symbol": "BTCUSDT",
                "interval": interval,
                "limit": limit
            }

            response = requests.get(url, params=params, timeout=5)

            if response.status_code != 200:
                return []

            data = response.json()

            candles = []
            for k in data:
                candles.append({
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4])
                })

            return candles

        except Exception as e:
            print(f"Binance error: {e}")
            return []

    # ---------- MAIN SCAN ----------
    def scan_markets(self):
        try:
            markets = self.get_polymarket_markets()

            h4 = self.get_binance_candles(interval="4h")
            m15 = self.get_binance_candles(interval="15m")

            if not markets or not h4 or not m15:
                return []

            opportunities = []

            for m in markets:
                try:
                    # Decide which side to evaluate
                    price = m["yes_price"]

                    opp = self.opportunity_engine.find_opportunity(
                        h4,
                        m15,
                        price
                    )

                    if opp:
                        opp["market_id"] = m["id"]
                        opp["question"] = m["question"]
                        opportunities.append(opp)

                except Exception:
                    continue

            return opportunities

        except Exception as e:
            print(f"Scan error: {e}")
            return []
