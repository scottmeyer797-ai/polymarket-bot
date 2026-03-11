"""
utils.py — Shared HTTP helpers with retry + corruption detection.

All API calls in the project go through safe_get / safe_post so that:
  • Transient failures are retried with exponential back-off
  • Corrupted / unexpected responses are detected and logged
  • A single import provides the full retry contract
"""

from __future__ import annotations

import time
from typing import Any

import requests

import config
import logger as log_mod

_log = log_mod.get_logger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent":    "polymarket-bot/1.0",
    "Accept":        "application/json",
    "Content-Type":  "application/json",
})


def _retry_call(fn, *args, **kwargs) -> Any | None:
    """
    Call fn(*args, **kwargs) up to API_MAX_RETRIES times.
    Uses exponential back-off on failure.
    """
    last_exc: Exception | None = None

    for attempt in range(1, config.API_MAX_RETRIES + 1):
        try:
            result = fn(*args, **kwargs)
            return result
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError) as exc:
            last_exc = exc
            sleep_for = config.API_RETRY_BACKOFF ** attempt
            _log.warning(
                f"Retryable error (attempt {attempt}/{config.API_MAX_RETRIES}): "
                f"{exc!r}  — sleeping {sleep_for:.1f}s"
            )
            time.sleep(sleep_for)
        except Exception as exc:
            # Non-retryable
            log_mod.log_error("Non-retryable request error", exc)
            return None

    log_mod.log_error(
        f"All {config.API_MAX_RETRIES} retries exhausted", last_exc
    )
    return None


def _parse_json(resp: requests.Response) -> Any | None:
    """Safely parse JSON, guarding against corrupt responses."""
    try:
        data = resp.json()
    except ValueError as exc:
        log_mod.log_error(
            f"Corrupt JSON response (status={resp.status_code})",
            exc,
            body_preview=resp.text[:200],
        )
        return None

    if not isinstance(data, (dict, list)):
        log_mod.log_error(
            f"Unexpected response type: {type(data).__name__}",
            body_preview=str(data)[:200],
        )
        return None

    return data


def safe_get(url: str, params: dict | None = None, timeout: int = 10, **kwargs) -> Any | None:
    """GET + retry + JSON parse."""
    def _call():
        resp = _SESSION.get(url, params=params, timeout=timeout, **kwargs)
        resp.raise_for_status()
        return _parse_json(resp)

    return _retry_call(_call)


def safe_post(url: str, body: dict, headers: dict | None = None, timeout: int = 15) -> Any | None:
    """POST + retry + JSON parse."""
    import json as _json

    def _call():
        resp = _SESSION.post(
            url,
            data=_json.dumps(body),
            headers=headers or {},
            timeout=timeout,
        )
        resp.raise_for_status()
        return _parse_json(resp)

    return _retry_call(_call)
