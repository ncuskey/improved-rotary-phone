"""
BookScouter API client for fetching buyback offers from multiple vendors.

BookScouter aggregates buyback prices from 14+ vendors including BooksRun,
TextbookRush, eCampus, and others. This replaces the single-vendor BooksRun API.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    amazon_sales_rank: Optional[int] = None  # Lower rank = more popular/higher demand
    raw: Dict[str, Any] = field(default_factory=dict)


def fetch_offers(
    isbn: str,
    *,
    api_key: str,
    use_recent: bool = False,
    fetch_amazon_rank: bool = True,
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
        fetch_amazon_rank: If True, also fetch metadata to get Amazon Sales Rank.
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

    # Optionally fetch metadata to get Amazon Sales Rank
    amazon_rank = None
    if fetch_amazon_rank:
        try:
            metadata = fetch_metadata(
                isbn,
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
                session=session
            )
            if metadata:
                # Parse AmazonSalesRank - can be int or string
                rank_value = metadata.get("AmazonSalesRank")
                if rank_value:
                    try:
                        amazon_rank = int(rank_value)
                    except (ValueError, TypeError):
                        pass  # Ignore invalid rank values
        except BookScouterAPIError:
            # Don't fail the whole request if metadata fetch fails
            pass

    # Parse the response
    return _parse_response(payload, amazon_rank=amazon_rank)


def _parse_response(
    payload: Dict[str, Any],
    amazon_rank: Optional[int] = None
) -> Optional[BookScouterResult]:
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
        amazon_sales_rank=amazon_rank,
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


def fetch_offers_batch(
    isbns: List[str],
    *,
    api_key: str,
    use_recent: bool = False,
    fetch_amazon_rank: bool = True,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = DEFAULT_TIMEOUT,
    max_workers: int = 10,
) -> Dict[str, Optional[BookScouterResult]]:
    """
    Fetch buyback offers for multiple ISBNs in parallel.

    This function uses ThreadPoolExecutor to make concurrent API requests,
    significantly improving performance when fetching data for many books.

    Args:
        isbns: List of ISBN-10 or ISBN-13 to look up
        api_key: BookScouter API key
        use_recent: If True, use recentPrices endpoint (fresh data, slower)
        fetch_amazon_rank: If True, also fetch metadata for Amazon Sales Rank
        base_url: Base URL for BookScouter API
        timeout: Request timeout in seconds per request
        max_workers: Maximum number of concurrent requests (default: 10)

    Returns:
        Dict mapping ISBN to BookScouterResult (or None if not found/failed)

    Example:
        >>> results = fetch_offers_batch(
        ...     ["9780441013593", "9780765326355"],
        ...     api_key="your_key"
        ... )
        >>> for isbn, result in results.items():
        ...     if result:
        ...         print(f"{isbn}: ${result.best_price}")
    """
    session = requests.Session()
    results: Dict[str, Optional[BookScouterResult]] = {}

    def fetch_single(isbn: str) -> tuple[str, Optional[BookScouterResult]]:
        """Helper function to fetch a single ISBN's data."""
        try:
            result = fetch_offers(
                isbn,
                api_key=api_key,
                use_recent=use_recent,
                fetch_amazon_rank=fetch_amazon_rank,
                base_url=base_url,
                timeout=timeout,
                session=session,
            )
            return (isbn, result)
        except BookScouterAPIError:
            # Return None for failed requests instead of raising
            return (isbn, None)

    # Execute all requests in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_single, isbn): isbn for isbn in isbns}

        for future in as_completed(futures):
            isbn, result = future.result()
            results[isbn] = result

    session.close()
    return results


def fetch_metadata_batch(
    isbns: List[str],
    *,
    api_key: str,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = DEFAULT_TIMEOUT,
    max_workers: int = 10,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Fetch book metadata for multiple ISBNs in parallel.

    This is useful when you only need metadata (including Amazon Sales Rank)
    without the pricing data.

    Args:
        isbns: List of ISBN-10 or ISBN-13 to look up
        api_key: BookScouter API key
        base_url: Base URL for BookScouter API
        timeout: Request timeout in seconds per request
        max_workers: Maximum number of concurrent requests (default: 10)

    Returns:
        Dict mapping ISBN to metadata dict (or None if not found/failed)
    """
    session = requests.Session()
    results: Dict[str, Optional[Dict[str, Any]]] = {}

    def fetch_single(isbn: str) -> tuple[str, Optional[Dict[str, Any]]]:
        """Helper function to fetch a single ISBN's metadata."""
        try:
            metadata = fetch_metadata(
                isbn,
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
                session=session,
            )
            return (isbn, metadata)
        except BookScouterAPIError:
            # Return None for failed requests instead of raising
            return (isbn, None)

    # Execute all requests in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_single, isbn): isbn for isbn in isbns}

        for future in as_completed(futures):
            isbn, metadata = future.result()
            results[isbn] = metadata

    session.close()
    return results
