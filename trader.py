"""
trader.py — Order execution layer for Polymarket CLOB
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

import requests

import config
import logger as log_mod
from portfolio_manager import PortfolioManager as Portfolio, Position
from risk_manager import SizedTrade
from utils import safe_get, safe_post

_log = log_mod.get_logger(__name__)

_ORDER_URL  = f"{config.POLYMARKET_API_BASE}/order"
_CANCEL_URL = f"{config.POLYMARKET_API_BASE}/order"
_STATUS_URL = f"{config.POLYMARKET_API_BASE}/order"
_BOOK_URL   = f"{config.POLYMARKET_API_BASE}/book"


class Trader:

    def __init__(self, portfolio: Portfolio):

        self.portfolio = portfolio
        self._placed_orders: set[str] = set()

    # --------------------------------------------------
    # MARKET DATA
    # --------------------------------------------------

    def get_best_ask(self, token_id: str) -> float:

        try:

            resp = safe_get(
                _BOOK_URL,
                params={"token_id": token_id},
                timeout=8
            )

            if resp and resp.get("asks"):

                return float(resp["asks"][0].get("price", 0))

        except Exception:
            pass

        return 0.0

    # --------------------------------------------------
    # TRADE EXECUTION
    # --------------------------------------------------

    def execute(self, trade: SizedTrade) -> bool:

        if not trade.approved:

            er = trade.edge_result

            log_mod.log_skipped_trade(
                market_id=er.market.market_id,
                side=er.side,
                reason=trade.reject_reason,
                edge=er.edge,
                confidence=er.confidence,
                signal_type=er.signal_type,
            )

            return False

        er = trade.edge_result
        market = er.market
        side = er.side

        token_idx = 0 if side == "YES" else 1

        if token_idx >= len(market.token_ids):

            _log.error(
                f"Token ID missing for {market.market_id} side={side}"
            )

            return False

        token_id = market.token_ids[token_idx]

        if self.portfolio.has_position_in_market(market.market_id):

            log_mod.log_skipped_trade(
                market_id=market.market_id,
                side=side,
                reason="duplicate_position",
                edge=er.edge,
                confidence=er.confidence,
                signal_type=er.signal_type,
            )

            return False

        # ---------------------------
        # SLIPPAGE CHECK
        # ---------------------------

        best_ask = self.get_best_ask(token_id)

        if best_ask and best_ask > trade.limit_price * 1.02:

            _log.info(
                f"Skipping trade due to slippage: "
                f"best_ask={best_ask} limit={trade.limit_price}"
            )

            return False

        position_id = str(uuid.uuid4())

        order_body = self._build_order(
            token_id,
            "BUY",
            trade.position_size,
            trade.limit_price,
            position_id
        )

        log_mod.log_trade(
            action="order_placed" if not config.DRY_RUN else "dry_run",
            market_id=market.market_id,
            side=side,
            edge=er.edge,
            confidence=er.confidence,
            size=trade.position_size,
            entry_price=trade.limit_price,
            signal_type=er.signal_type,
            token_id=token_id,
            best_ask=best_ask,
        )

        if config.DRY_RUN:

            self._register_position(
                position_id,
                "dry-run-" + position_id[:8],
                market.market_id,
                side,
                token_id,
                trade.position_size,
                trade.limit_price
            )

            return True

        order_id = self._post_order(order_body)

        if not order_id:

            _log.error(f"Order placement failed for {market.market_id}")

            return False

        self._placed_orders.add(order_id)

        self._register_position(
            position_id,
            order_id,
            market.market_id,
            side,
            token_id,
            trade.position_size,
            trade.limit_price
        )

        return True

    # --------------------------------------------------
    # ORDER MANAGEMENT
    # --------------------------------------------------

    def check_fills(self):

        for pos in self.portfolio.open_positions():

            if pos.filled:
                continue

            if pos.order_id.startswith("dry-run"):
                continue

            filled, fill_price = self._get_fill_status(pos.order_id)

            if filled:

                self.portfolio.mark_filled(
                    pos.position_id,
                    fill_price
                )

    def cancel_stale_orders(self):

        for pos in self.portfolio.get_stale_positions():

            if pos.order_id.startswith("dry-run"):

                self.portfolio.cancel_position(pos.position_id)
                continue

            if self._cancel_order(pos.order_id):

                self.portfolio.cancel_position(pos.position_id)

                _log.info(
                    f"Cancelled stale order {pos.order_id}"
                )

    # --------------------------------------------------
    # ORDER BUILDING
    # --------------------------------------------------

    @staticmethod
    def _build_order(token_id, side, size, limit_price, position_id):

        shares = round(size / max(limit_price, 0.0001), 4)

        return {

            "tokenID": token_id,
            "side": side,
            "type": "LIMIT",
            "size": str(shares),
            "price": str(round(limit_price, 4)),
            "expiration": "0",
            "nonce": position_id,
        }

    # --------------------------------------------------
    # AUTH SIGNATURE
    # --------------------------------------------------

    def _sign_headers(self, body):

        if not config.POLYMARKET_API_KEY:
            return {}

        ts = str(int(time.time() * 1000))

        body_str = json.dumps(body, separators=(",", ":"))

        signature = hmac.new(
            config.POLYMARKET_SECRET.encode(),
            (ts + body_str).encode(),
            hashlib.sha256
        ).hexdigest()

        return {

            "POLY-ADDRESS": config.WALLET_ADDRESS,
            "POLY-SIGNATURE": signature,
            "POLY-TIMESTAMP": ts,
            "POLY-API-KEY": config.POLYMARKET_API_KEY,
            "POLY-PASSPHRASE": config.POLYMARKET_PASSPHRASE,
        }

    # --------------------------------------------------
    # API CALLS
    # --------------------------------------------------

    def _post_order(self, body):

        headers = {
            "Content-Type": "application/json",
            **self._sign_headers(body)
        }

        try:

            resp = safe_post(
                _ORDER_URL,
                body,
                headers=headers,
                timeout=15
            )

            if resp and resp.get("orderID"):

                return str(resp["orderID"])

            _log.error(f"Unexpected order response: {resp}")

        except Exception as exc:

            log_mod.log_error("_post_order failed", exc)

        return None

    def _get_fill_status(self, order_id):

        try:

            resp = safe_get(
                f"{_STATUS_URL}/{order_id}",
                timeout=10
            )

            if resp and resp.get("status") in ("MATCHED", "FILLED"):

                return True, float(resp.get("price", 0) or 0)

        except Exception as exc:

            log_mod.log_error(
                "_get_fill_status failed",
                exc,
                order_id=order_id
            )

        return False, 0.0

    def _cancel_order(self, order_id):

        try:

            resp = requests.delete(
                f"{_CANCEL_URL}/{order_id}",
                headers=self._sign_headers({}),
                timeout=10
            )

            return resp.status_code in (200, 204)

        except Exception as exc:

            log_mod.log_error(
                "_cancel_order failed",
                exc,
                order_id=order_id
            )

        return False

    # --------------------------------------------------
    # PORTFOLIO
    # --------------------------------------------------

    def _register_position(
        self,
        position_id,
        order_id,
        market_id,
        side,
        token_id,
        size,
        limit_price,
    ):

        pos = Position(

            position_id=position_id,
            market_id=market_id,
            side=side,
            token_id=token_id,
            size=size,
            entry_price=limit_price,
            filled_price=0.0,
            order_id=order_id,
        )

        self.portfolio.add_position(pos)
