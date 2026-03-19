import requests
import time

class MarketScanner:

    def __init__(self, polymarket_client, opportunity_engine):
        self.polymarket_client = polymarket_client
        self.opportunity_engine = opportunity_engine

    # ---------- BINANCE DATA ----------
    def get_binance_candles(self, symbol="BTCUSDT", interval="15m", limit=100):
        url = "https://api.binance.com/api/v3/klines"

        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }

        try:
            response = requests.get(url, params=params, timeout=5)

            if response.status_code != 200:
                print(f"Binance bad status: {response.status_code}")
                return []

            data = response.json()

            candles = []
            for k in data:
                candles.append({
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5])
                })

            return candles

        except Exception as e:
            print(f"Binance error: {e}")
            return []

    # ---------- MAIN SCAN ----------
    def scan_markets(self):
        try:
            markets = self.polymarket_client.get_markets()
        except Exception as e:
            print(f"Error fetching markets: {e}")
            return []

        opportunities = []

        # Pull candles once
        h4_candles = self.get_binance_candles(interval="4h", limit=100)
        m15_candles = self.get_binance_candles(interval="15m", limit=100)

        if not h4_candles or not m15_candles:
            print("No candle data available")
            return []

        for market in markets:
            try:
                polymarket_price = market.get("price")

                if polymarket_price is None:
                    continue

                opportunity = self.opportunity_engine.find_opportunity(
                    h4_candles,
                    m15_candles,
                    polymarket_price
                )

                if opportunity:
                    opportunity["market_id"] = market.get("id")
                    opportunity["question"] = market.get("question")
                    opportunities.append(opportunity)

            except Exception as e:
                print(f"Market processing error: {e}")
                continue

        return opportunities

    # ---------- SAFE LOOP ----------
    def run_once(self):
        try:
            opportunities = self.scan_markets()

            if opportunities:
                print(f"Found {len(opportunities)} opportunities:")
                for opp in opportunities:
                    print(opp)
            else:
                print("No opportunities found")

        except Exception as e:
            print(f"Run error: {e}")

    def run(self, interval=10):
        while True:
            self.run_once()
            time.sleep(interval)
