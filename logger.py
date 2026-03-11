"""
logger.py — Structured JSON logging.

IMPROVEMENT 7: Expanded trade logs with signal_type, entry/exit price,
PnL, and reason codes for skipped trades.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any

import config


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts":     datetime.now(timezone.utc).isoformat(),
            "level":  record.levelname,
            "module": record.module,
            "msg":    record.getMessage(),
        }
        for key, val in record.__dict__.items():
            if key.startswith("_"):
                payload[key[1:]] = val
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def get_logger(name: str = "polymarket_bot") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)
    fmt = _JSONFormatter()

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    if config.LOG_FILE:
        fh = RotatingFileHandler(
            config.LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    logger.propagate = False
    return logger


_log = get_logger()


# ── IMPROVEMENT 7: Full trade log ─────────────────────────────────────────────

def log_trade(
    action:       str,
    market_id:    str,
    side:         str,
    edge:         float,
    confidence:   float,
    size:         float,
    entry_price:  float,
    exit_price:   float | None  = None,
    pnl:          float | None  = None,
    signal_type:  str           = "single_market",
    **extra: Any,
) -> None:
    """
    Structured trade log entry.

    Fields logged:
      timestamp, market_id, signal_type, edge, confidence,
      position_size, entry_price, exit_price, pnl
    """
    _log.info(
        action,
        extra={
            "_action":      action,
            "_market_id":   market_id,
            "_side":        side,
            "_signal_type": signal_type,
            "_edge":        round(edge, 4),
            "_confidence":  round(confidence, 4),
            "_position_size": round(size, 4),
            "_entry_price": round(entry_price, 4),
            "_exit_price":  round(exit_price, 4)  if exit_price is not None else None,
            "_pnl":         round(pnl, 4)         if pnl        is not None else None,
            **{f"_{k}": v for k, v in extra.items()},
        },
    )


def log_skipped_trade(
    market_id:   str,
    side:        str,
    reason:      str,
    edge:        float   = 0.0,
    confidence:  float   = 0.0,
    signal_type: str     = "single_market",
) -> None:
    """IMPROVEMENT 7: Log every skipped trade with the rejection reason."""
    _log.info(
        "trade_skipped",
        extra={
            "_action":      "trade_skipped",
            "_market_id":   market_id,
            "_side":        side,
            "_signal_type": signal_type,
            "_skip_reason": reason,
            "_edge":        round(edge, 4),
            "_confidence":  round(confidence, 4),
        },
    )


def log_scan(
    markets_found:    int,
    markets_filtered: int,
    candidates:       int,
    cross_signals:    int = 0,
) -> None:
    _log.info(
        "scan_complete",
        extra={
            "_markets_found":    markets_found,
            "_markets_filtered": markets_filtered,
            "_candidates":       candidates,
            "_cross_signals":    cross_signals,
        },
    )


def log_circuit_breaker(reason: str, daily_loss_pct: float) -> None:
    """IMPROVEMENT 4: Log when circuit breaker activates."""
    _log.warning(
        "circuit_breaker_active",
        extra={
            "_event":           "circuit_breaker",
            "_reason":          reason,
            "_daily_loss_pct":  round(daily_loss_pct, 4),
        },
    )


def log_error(msg: str, exc: Exception | None = None, **extra: Any) -> None:
    _log.error(msg, exc_info=exc, extra={f"_{k}": v for k, v in extra.items()})
