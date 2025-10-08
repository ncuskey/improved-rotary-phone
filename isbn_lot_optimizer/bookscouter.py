"""
BookScouter API client for fetching buyback offers from multiple vendors.

BookScouter aggregates buyback prices from 14+ vendors including BooksRun,
TextbookRush, eCampus, and others. This replaces the single-vendor BooksRun API.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

import requests  # type: ignore[reportMissingImports]


DEFAULT_BASE_URL = "https://api.bookscouter.com/services/v1"
DEFAULT_TIMEOUT = 15


class BookScouterAPIError(RuntimeError):
    """Raised when the BookScouter API returns an unexpected response."""


@dataclass
class VendorOffer:
    """Represents a single vendor's buyback offer from BookScouter."""
    vendor_name: str
    vendor_id: str
    price: float
    updated_at: str  # Format: "YYYY-MM-DD HH:MM:SS"


@dataclass
class BookScouterResult:
    """Aggregated buyback offers from all vendors for a single ISBN."""
    isbn_10: str
    isbn_13: str
    offers: List[VendorOffer] = field(default_factory=list)
    best_price: float = 0.0
    best_vendor: Optional[str] = None
    total_vendors: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)


def fetch_offers(
    isbn: str,
    *,
    api_key: str,
    use_recent: bool = False,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = DEFAULT_TIMEOUT,
    session: Optional[requests.Session] = None,
) -> Optional[BookScouterResult]:
    """
    Fetch buyback offers for a single ISBN from BookScouter API.

    Args:
        isbn: ISBN-10 or ISBN-13 to look up
        api_key: BookScouter API key
        use_recent: If True, use recentPrices endpoint (fresh data, slower).
                   If False, use cachedPrices endpoint (cached data, faster).
        base_url: Base URL for BookScouter API
        timeout: Request timeout in seconds
        session: Optional requests.Session for connection pooling

    Returns:
        BookScouterResult with all vendor offers, or None if not found

    Raises:
        BookScouterAPIError: If the API request fails or returns invalid data
    """
    if not api_key:
        raise ValueError("api_key is required for BookScouter lookups")

    # Choose endpoint based on freshness requirement
    endpoint = "recentPrices" if use_recent else "cachedPrices"
    root = base_url.rstrip("/")
    url = f"{root}/{endpoint}/{isbn}"
    params = {"apiKey": api_key}
    headers = {
        "Accept": "application/json",
        "User-Agent": "ISBN-Lot-Optimizer/1.0"
    }

    try:
        if session is not None:
            response = session.get(url, params=params, headers=headers, timeout=timeout)
        else:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        raise BookScouterAPIError(f"BookScouter request failed: {exc}") from exc

    if response.status_code == 404:
        return None

    # Handle rate limiting (429) with a helpful message
    if response.status_code == 429:
        raise BookScouterAPIError(
            "BookScouter rate limit exceeded (60 calls/minute). "
            "Please increase BOOKSCOUTER_DELAY or wait before retrying."
        )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise BookScouterAPIError(
            f"BookScouter error {response.status_code}: {response.text[:200]}"
        ) from exc

    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise BookScouterAPIError("BookScouter response was not valid JSON") from exc

    # Parse the response
    return _parse_response(payload)


def _parse_response(payload: Dict[str, Any]) -> Optional[BookScouterResult]:
    """Parse BookScouter API response into BookScouterResult."""
    if not isinstance(payload, dict):
        return None

    status = payload.get("status")
    if status != "success":
        return None

    # Extract ISBN info
    isbn_data = payload.get("isbn", {})
    isbn_10 = isbn_data.get("Isbn10", "")
    isbn_13 = isbn_data.get("Isbn13", "")

    # Extract vendor offers (key name differs by endpoint)
    vendor_list = payload.get("cachedPrices") or payload.get("prices") or []

    if not isinstance(vendor_list, list):
        return None

    # Parse each vendor offer
    offers: List[VendorOffer] = []
    best_price = 0.0
    best_vendor = None

    for vendor_data in vendor_list:
        if not isinstance(vendor_data, dict):
            continue

        vendor_name = vendor_data.get("VendorName", "")
        vendor_id = str(vendor_data.get("VendorId", ""))
        price = float(vendor_data.get("Price", 0))
        updated_at = vendor_data.get("UpdatedOn", "")

        # Skip vendors with no offer
        if price <= 0:
            continue

        offers.append(VendorOffer(
            vendor_name=vendor_name,
            vendor_id=vendor_id,
            price=price,
            updated_at=updated_at
        ))

        # Track best offer
        if price > best_price:
            best_price = price
            best_vendor = vendor_name

    return BookScouterResult(
        isbn_10=isbn_10,
        isbn_13=isbn_13,
        offers=offers,
        best_price=best_price,
        best_vendor=best_vendor,
        total_vendors=len(offers),
        raw=payload
    )


def fetch_metadata(
    isbn: str,
    *,
    api_key: str,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = DEFAULT_TIMEOUT,
    session: Optional[requests.Session] = None,
) -> Optional[Dict[str, Any]]:
    """
    Fetch book metadata from BookScouter API.

    Returns dict with keys: Isbn10, Isbn13, Title, Author (list), Image,
    Published, Publisher, Binding, Edition, NumberOfPages, AmazonSalesRank, etc.

    This can be used as an alternative metadata source if needed.
    """
    if not api_key:
        raise ValueError("api_key is required for BookScouter lookups")

    root = base_url.rstrip("/")
    url = f"{root}/book/{isbn}"
    params = {"apiKey": api_key}
    headers = {
        "Accept": "application/json",
        "User-Agent": "ISBN-Lot-Optimizer/1.0"
    }

    try:
        if session is not None:
            response = session.get(url, params=params, headers=headers, timeout=timeout)
        else:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        raise BookScouterAPIError(f"BookScouter request failed: {exc}") from exc

    if response.status_code == 404:
        return None

    # Handle rate limiting (429) with a helpful message
    if response.status_code == 429:
        raise BookScouterAPIError(
            "BookScouter rate limit exceeded (60 calls/minute). "
            "Please increase BOOKSCOUTER_DELAY or wait before retrying."
        )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise BookScouterAPIError(
            f"BookScouter error {response.status_code}: {response.text[:200]}"
        ) from exc

    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise BookScouterAPIError("BookScouter response was not valid JSON") from exc

    if payload.get("status") != "success":
        return None

    return payload.get("book")
