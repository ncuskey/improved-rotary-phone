"""Client for the BooksRun SELL pricing API."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

import requests
from requests import Response, Session
from requests.exceptions import RequestException

API_URL_TEMPLATE = "https://booksrun.com/api/price/sell/{isbn}"
DEFAULT_CURRENCY = "USD"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (LotHelper)",
    "Accept": "application/json",
}
MAX_ATTEMPTS = 3
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
BACKOFF_BASE_SECONDS = 0.8
RAW_ERROR_LIMIT = 500


class BooksRunConfigurationError(ValueError):
    """Raised when BooksRun configuration is invalid."""


def get_booksrun_key() -> str:
    """Return the configured BooksRun API key or raise a helpful error."""
    try:
        key = os.environ["BOOKSRUN_KEY"].strip()
    except KeyError as exc:  # pragma: no cover - exercised via ValueError branch
        raise BooksRunConfigurationError(
            "BOOKSRUN_KEY environment variable is required. "
            "Set it via export BOOKSRUN_KEY=... or .env."
        ) from exc

    # Normalize values like '?key=XYZ' or 'key=XYZ' copied from docs/snippets
    key_lower = key.lower()
    if key_lower.startswith("?key=") or key_lower.startswith("key="):
        key = key.split("=", 1)[1].split("&", 1)[0].strip()

    if not key:
        raise BooksRunConfigurationError(
            "BOOKSRUN_KEY is configured but empty. "
            "Provide a valid BooksRun API key."
        )

    return key


def _coerce_price(value: Any) -> Optional[float]:
    """Safely convert raw API price values to floats."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_error_result(isbn: str, http_status: int, raw_payload: str) -> Dict[str, Any]:
    return {
        "isbn": isbn,
        "status": "error",
        "http_status": http_status,
        "average": None,
        "good": None,
        "new": None,
        "currency": DEFAULT_CURRENCY,
        "raw_json": raw_payload[:RAW_ERROR_LIMIT],
    }


def _parse_success_payload(isbn: str, response: Response) -> Dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        body = response.text or ""
        return _build_error_result(isbn, response.status_code, body)

    result = cast_dict(data.get("result", {}))
    status = str(result.get("status", "error")).lower()
    normalized_status = "success" if status == "success" else "error"
    text = cast_dict(result.get("text", {}))

    average = _coerce_price(text.get("Average")) if normalized_status == "success" else None
    good = _coerce_price(text.get("Good")) if normalized_status == "success" else None
    new = _coerce_price(text.get("New")) if normalized_status == "success" else None

    currency = (
        result.get("currency")
        or text.get("currency")
        or DEFAULT_CURRENCY
    )
    if not isinstance(currency, str):
        currency = DEFAULT_CURRENCY

    raw_json = json.dumps(data, separators=(",", ":"), sort_keys=True)

    return {
        "isbn": isbn,
        "status": normalized_status,
        "http_status": response.status_code,
        "average": average,
        "good": good,
        "new": new,
        "currency": currency,
        "raw_json": raw_json,
    }


def cast_dict(value: Any) -> Dict[str, Any]:
    """Return ``value`` if it is a dict, otherwise an empty dict."""
    return value if isinstance(value, dict) else {}


def get_sell_quote(isbn: str, session: Optional[Session] = None) -> Dict[str, Any]:
    """Fetch a BooksRun SELL quote for ``isbn``.

    Parameters
    ----------
    isbn:
        The ISBN string to query.
    session:
        Optional ``requests.Session`` for connection reuse.
    """

    key = get_booksrun_key()
    owns_session = session is None
    http_status = 0
    response: Optional[Response] = None
    raw_payload = ""

    if owns_session:
        session = requests.Session()

    assert session is not None  # for type checkers

    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = session.get(
                    API_URL_TEMPLATE.format(isbn=isbn),
                    params={"key": key},
                    headers=HEADERS,
                    timeout=10,
                )
                http_status = response.status_code
            except RequestException as exc:
                http_status = 0
                raw_payload = str(exc)
                if attempt == MAX_ATTEMPTS:
                    return _build_error_result(isbn, http_status, raw_payload)
                time.sleep(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
                continue

            if http_status in RETRY_STATUS_CODES and attempt < MAX_ATTEMPTS:
                time.sleep(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
                continue

            if http_status == 403:
                body = response.text or ""
                return _build_error_result(isbn, http_status, body)

            break
        else:  # pragma: no cover - loop always breaks or returns
            return _build_error_result(isbn, http_status, raw_payload)

        assert response is not None  # guarded by loop
        if http_status >= 500 or http_status in {429}:
            # Exhausted retries with error status.
            body = response.text or ""
            return _build_error_result(isbn, http_status, body)

        return _parse_success_payload(isbn, response)
    finally:
        if owns_session:
            session.close()
