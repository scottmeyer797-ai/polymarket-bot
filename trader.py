class Trader:

    def __init__(self, portfolio_manager):
        self.portfolio = portfolio_manager
        self.open_orders = []

    # ---------- EXECUTE TRADE ----------
    def execute(self, sized_trade):
        try:
            if sized_trade is None:
                return False

            market = getattr(sized_trade, "market", None)
            market_id = getattr(market, "market_id", None)

            side = getattr(sized_trade, "side", None)
            size = float(getattr(sized_trade, "position_size", 0))
            price = float(getattr(sized_trade, "limit_price", 0))

            # Validate inputs
            if not market_id or side not in ["YES", "NO"]:
                print(f"Invalid trade structure: {sized_trade}")
                return False

            if size <= 0 or price <= 0:
                print(f"Invalid trade values: size={size}, price={price}")
                return False

            # Prevent duplicate positions
            if hasattr(self.portfolio, "has_position_in_market"):
                if self.portfolio.has_position_in_market(market_id):
                    return False

            # Simulated execution
            position = {
                "market_id": market_id,
                "side": side,
                "size": size,
                "entry_price": price,
                "timestamp": self._now()
            }

            # Safe add
            if hasattr(self.portfolio, "add_position"):
                self.portfolio.add_position(position)

            print(f"[TRADE EXECUTED] {side} | {market_id} | size={size} | price={price}")

            return True

        except Exception as e:
            print(f"Execution error: {e}")
            return False

    # ---------- MOCK BEST ASK ----------
    def get_best_ask(self, token_id):
        try:
            if not token_id:
                return 0.0
            return 0.5  # placeholder
        except Exception as e:
            print(f"Best ask error: {e}")
            return 0.0

    # ---------- POSITION MANAGEMENT ----------
    def check_fills(self):
        try:
            return
        except Exception as e:
            print(f"Fill check error: {e}")

    def cancel_stale_orders(self):
        try:
            self.open_orders = []
        except Exception as e:
            print(f"Cancel error: {e}")

    # ---------- UTIL ----------
    def _now(self):
        try:
            import time
            return int(time.time())
        except:
            return 0
