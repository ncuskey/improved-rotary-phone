
from __future__ import annotations

import json
from typing import Any, Iterable, Mapping, Optional

import requests  # type: ignore[reportMissingImports]

from .models import BooksRunOffer

DEFAULT_BASE_URL = "https://booksrun.com"
DEFAULT_TIMEOUT = 15


class BooksRunAPIError(RuntimeError):
    """Raised when the BooksRun API returns an unexpected response."""


_CONDITION_MAP = {
    "new": "new",
    "brand new": "new",
    "like new": "like_new",
    "likenew": "like_new",
    "very good": "very_good",
    "verygood": "very_good",
    "vg": "very_good",
    "good": "good",
    "g": "good",
    "acceptable": "acceptable",
    "acc": "acceptable",
    "poor": "poor",
    "fair": "acceptable",
}


def normalise_condition(condition: Optional[str]) -> str:
    if not condition:
        return "good"
    key = condition.strip().lower()
    return _CONDITION_MAP.get(key, "good")


def fetch_offer(
    isbn: str,
    *,
    api_key: str,
    affiliate_id: Optional[str] = None,
    condition: Optional[str] = None,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = DEFAULT_TIMEOUT,
    session: Optional[requests.Session] = None,
) -> Optional[BooksRunOffer]:
    if not api_key:
        raise ValueError("api_key is required for BooksRun lookups")

    # Normalize api_key values like '?key=XYZ' or 'key=XYZ'
    ak = api_key.strip()
    ak_lower = ak.lower()
    if ak_lower.startswith("?key=") or ak_lower.startswith("key="):
        api_key = ak.split("=", 1)[1].split("&", 1)[0].strip()

    # Normalize affiliate_id values like '?afk=123' or 'afk=123'
    if affiliate_id:
        afk = str(affiliate_id).strip()
        afk_lower = afk.lower()
        if afk_lower.startswith("?afk=") or afk_lower.startswith("afk="):
            affiliate_id = afk.split("=", 1)[1].split("&", 1)[0].strip()

    cond = normalise_condition(condition)
    root = base_url.rstrip("/")
    # Use simple SELL price endpoint per requirement:
    # https://booksrun.com/api/price/sell/{isbn}?key=API_KEY
    url = f"{root}/api/price/sell/{isbn}"
    params = {
        "key": api_key,
    }
    if affiliate_id:
        params["afk"] = affiliate_id

    headers = {"Accept": "application/json", "User-Agent": "ISBN-Lot-Optimizer/1.0"}

    try:
        if session is not None:
            response = session.get(url, params=params, headers=headers, timeout=timeout)
        else:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.RequestException as exc:  # pragma: no cover - network failure
        raise BooksRunAPIError(f"BooksRun request failed: {exc}") from exc

    if response.status_code == 404:
        return None
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:  # pragma: no cover - propagated upstream
        raise BooksRunAPIError(
            f"BooksRun error {response.status_code}: {response.text[:200]}"
        ) from exc

    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise BooksRunAPIError("BooksRun response was not valid JSON") from exc

    # Prefer simple /api/price/sell payload shape like:
    # {"result":{"status":"success","text":{"Average":0,"Good":0,"New":0},"currency":"USD"}}
    if isinstance(payload, Mapping):
        result = payload.get("result")
        if isinstance(result, Mapping):
            text = result.get("text")
            if isinstance(text, Mapping):
                cash = _to_float(text.get("Good"))
                # Store credit is not available in this payload; leave as None
                credit = None
                currency = result.get("currency")

                if cash is not None or credit is not None:
                    offer = BooksRunOffer(
                        isbn=isbn,
                        condition=cond,
                        cash_price=cash,
                        store_credit=credit,
                        currency=currency if isinstance(currency, str) else None,
                        url=None,
                        updated_at=None,
                        raw=dict(result),
                    )
                    return offer

    # Fallback to generic parser for other API shapes
    offer = _parse_offer_payload(payload)
    if offer is None:
        return None

    offer.isbn = isbn
    offer.condition = cond
    return offer


def _parse_offer_payload(payload: Any) -> Optional[BooksRunOffer]:
    """Attempt to extract cash and credit offers from BooksRun payload."""
    if not isinstance(payload, Mapping):
        return None

    block: Any = payload
    for key in ("result", "results", "response", "data"):
        candidate = block.get(key)
        if isinstance(candidate, Mapping):
            block = candidate
            break

    offers_container = None
    for key in ("offers", "offer", "sell", "buyback", "quote"):
        candidate = block.get(key)
        if isinstance(candidate, Mapping):
            offers_container = candidate
            break

    if offers_container is None:
        offers_container = block

    cash_price = _search_price(offers_container, ("cash", "buy", "payout"))
    credit_price = _search_price(offers_container, ("credit", "store", "trade"))
    currency = _search_currency(offers_container) or block.get("currency")
    link = block.get("url") or block.get("link")
    updated = (
        block.get("updated_at")
        or block.get("updated")
        or block.get("timestamp")
        or payload.get("timestamp")
    )

    return BooksRunOffer(
        isbn="",
        condition="",
        cash_price=cash_price,
        store_credit=credit_price,
        currency=currency if isinstance(currency, str) else None,
        url=link if isinstance(link, str) else None,
        updated_at=str(updated) if updated is not None else None,
        raw=dict(block),
    )


def _search_price(data: Any, keywords: Iterable[str]) -> Optional[float]:
    keywords_lower = tuple(k.lower() for k in keywords)
    queue = [data]
    while queue:
        current = queue.pop(0)
        if isinstance(current, Mapping):
            for key, value in current.items():
                key_lower = str(key).lower()
                if isinstance(value, (list, tuple)):
                    queue.extend(value)
                elif isinstance(value, Mapping):
                    queue.append(value)
                else:
                    if any(marker in key_lower for marker in keywords_lower):
                        price = _to_float(value)
                        if price is not None:
                            return price
            continue
        if isinstance(current, (list, tuple)):
            queue.extend(current)
    return None


def _search_currency(data: Any) -> Optional[str]:
    queue = [data]
    while queue:
        current = queue.pop(0)
        if isinstance(current, Mapping):
            for key, value in current.items():
                key_lower = str(key).lower()
                if key_lower in {"currency", "curr", "iso_currency"} and isinstance(value, str):
                    return value
                if isinstance(value, Mapping):
                    queue.append(value)
                elif isinstance(value, (list, tuple)):
                    queue.extend(value)
    return None


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip().replace("$", "")
        try:
            return float(stripped)
        except ValueError:
            return None
    return None
