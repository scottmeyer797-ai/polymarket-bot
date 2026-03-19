class OpportunityEngine:

    def __init__(self):
        pass

    # ---------- MAIN ENTRY ----------
    def find_opportunity(self, h4_candles, m15_candles, polymarket_price):
        try:
            if not h4_candles or not m15_candles:
                return None

            trend = self.get_h4_trend(h4_candles)
            bos   = self.detect_m15_bos(m15_candles)

            if not trend or not bos:
                return None

            if trend != bos:
                return None

            if not self.is_valid_retracement(h4_candles, m15_candles):
                return None

            return {
                "type": "BUY_YES" if trend == "BULLISH" else "BUY_NO",
                "entry_price": polymarket_price,
                "confidence": 0.6
            }

        except Exception as e:
            print(f"Opportunity error: {e}")
            return None

    # ---------- H4 TREND ----------
    def get_h4_trend(self, candles):
        try:
            if len(candles) < 10:
                return None

            highs = [c["high"] for c in candles[-10:]]
            lows  = [c["low"] for c in candles[-10:]]

            if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
                return "BULLISH"

            if highs[-1] < highs[-2] and lows[-1] < lows[-2]:
                return "BEARISH"

            return None

        except:
            return None

    # ---------- M15 BOS ----------
    def detect_m15_bos(self, candles):
        try:
            if len(candles) < 5:
                return None

            last_high = max(c["high"] for c in candles[-5:-1])
            last_low  = min(c["low"] for c in candles[-5:-1])

            current = candles[-1]

            if current["close"] > last_high:
                return "BULLISH"

            if current["close"] < last_low:
                return "BEARISH"

            return None

        except:
            return None

    # ---------- 50% RETRACEMENT ----------
    def is_valid_retracement(self, h4_candles, m15_candles):
        try:
            if len(h4_candles) < 20:
                return False

            swing_high = max(c["high"] for c in h4_candles[-20:])
            swing_low  = min(c["low"] for c in h4_candles[-20:])

            midpoint = (swing_high + swing_low) / 2

            current_price = m15_candles[-1]["close"]

            # Must retrace at least 50%
            if swing_high > swing_low:
                if current_price > midpoint and current_price < swing_high:
                    return True
                if current_price < midpoint and current_price > swing_low:
                    return True

            return False

        except:
            return False
