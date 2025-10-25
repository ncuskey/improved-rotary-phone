from __future__ import annotations

import re
import statistics
import time
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple, TypedDict, cast

import requests
from requests.auth import _basic_auth_str

from shared.models import EbayMarketStats

EBAY_FINDING_URL = "https://svcs.ebay.com/services/search/FindingService/v1"

# --- eBay Browse API (app token + active comps) ---
BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
MARKETPLACE = os.getenv("EBAY_MARKETPLACE", "EBAY_US")

class _TokenCache(TypedDict):
    access_token: Optional[str]
    expires_at: float

_token_cache: _TokenCache = {"access_token": None, "expires_at": 0.0}

# Cache for Browse API results (1-hour TTL to reduce redundant API calls)
_browse_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
_BROWSE_CACHE_TTL = 3600  # 1 hour in seconds


def _retry_with_exponential_backoff(
    func: Any,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 10.0,
    backoff_factor: float = 2.0
) -> Any:
    """
    Retry a function with exponential backoff on rate limiting.

    Args:
        func: Function to retry (should return a requests.Response)
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
        backoff_factor: Multiplier for delay on each retry

    Returns:
        The successful response from func()

    Raises:
        The last exception if all retries fail
    """
    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            response = func()

            # Check for rate limiting responses
            if response.status_code in (429, 503):
                if attempt < max_retries:
                    # Rate limited - wait and retry
                    wait_time = min(delay, max_delay)
                    print(f"⚠️  Rate limited (HTTP {response.status_code}), retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries + 1})")
                    time.sleep(wait_time)
                    delay *= backoff_factor
                    continue
                else:
                    # Max retries reached
                    return response

            # Success or non-retryable error
            return response

        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                wait_time = min(delay, max_delay)
                print(f"⚠️  API call failed: {e}, retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries + 1})")
                time.sleep(wait_time)
                delay *= backoff_factor
            else:
                raise

    # Should never reach here, but just in case
    if last_exception:
        raise last_exception
    return None


def get_app_token() -> str:
    now = time.time()
    if _token_cache.get("access_token") and float(_token_cache.get("expires_at", 0)) - now > 120:
        return str(_token_cache["access_token"])
    cid = os.getenv("EBAY_CLIENT_ID")
    csec = os.getenv("EBAY_CLIENT_SECRET")
    if not cid or not csec:
        raise RuntimeError("EBAY_CLIENT_ID/EBAY_CLIENT_SECRET not set")
    basic = _basic_auth_str(cid, csec)
    r = requests.post(
        OAUTH_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Authorization": basic},
        data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
        timeout=20,
    )
    r.raise_for_status()
    js = r.json()
    _token_cache["access_token"] = js["access_token"]
    _token_cache["expires_at"] = now + float(js.get("expires_in", 7200))
    return str(_token_cache["access_token"])


def browse_active_by_isbn(
    isbn: str,
    limit: int = 50,
    marketplace: str = MARKETPLACE,
    include_signed: bool = False
) -> Dict[str, Any]:
    """
    Fetch active eBay listings by ISBN with smart filtering.

    Args:
        isbn: ISBN to search for
        limit: Maximum number of results to fetch
        marketplace: eBay marketplace ID
        include_signed: If False, filter out signed/autographed copies

    Returns:
        Dict with pricing stats and filtering metadata
    """
    # Check cache first (1-hour TTL)
    cache_key = f"{isbn}:{limit}:{marketplace}:{include_signed}"
    now = time.time()
    if cache_key in _browse_cache:
        cached_result, expires_at = _browse_cache[cache_key]
        if expires_at > now:
            # Cache hit - return cached result
            return cached_result

    # Cache miss - make API call with exponential backoff for rate limiting
    tok = get_app_token()

    # Wrap the API call in a lambda for retry logic
    r = _retry_with_exponential_backoff(
        lambda: requests.get(
            BROWSE_URL,
            params={"gtin": isbn, "limit": str(limit)},
            headers={"Authorization": f"Bearer {tok}", "X-EBAY-C-MARKETPLACE-ID": marketplace},
            timeout=30,
        )
    )

    if r.status_code != 200:
        return {"error": f"http_{r.status_code}", "body": r.text[:400], "source": "browse"}
    js: Dict[str, Any] = r.json()
    items = cast(List[Dict[str, Any]], js.get("itemSummaries", []) or [])

    # Keywords to filter out (case-insensitive)
    LOT_KEYWORDS = ["lot of", "set of", "bundle", "collection"]
    SIGNED_KEYWORDS = ["signed", "autographed", "signature"]

    prices: List[float] = []
    signed_count = 0
    lot_count = 0
    filtered_count = 0
    total_count = 0

    for it in items:
        if not isinstance(it, dict):
            continue
        total_count += 1

        # Extract title and price
        title = (it.get("title") or "").lower()
        p = it.get("price", {}).get("value")

        # Check for problematic keywords
        is_lot = any(keyword in title for keyword in LOT_KEYWORDS)
        is_signed = any(keyword in title for keyword in SIGNED_KEYWORDS)

        # Track occurrences
        if is_lot:
            lot_count += 1
        if is_signed:
            signed_count += 1

        # Filter logic
        should_exclude = False
        if is_lot:
            # Always filter out multi-book lots
            should_exclude = True
        elif is_signed and not include_signed:
            # Filter signed copies unless user indicated their book is signed
            should_exclude = True

        if should_exclude:
            filtered_count += 1
            continue

        # Add price if valid
        try:
            prices.append(float(p))  # type: ignore[arg-type]
        except Exception:
            pass

    stats: Dict[str, Any] = {
        "active_count": len(prices),
        "median_price": statistics.median(prices) if prices else None,
        "min_price": min(prices) if prices else None,
        "max_price": max(prices) if prices else None,
        # sold/complete unavailable without Insights; surface N/A clearly
        "sold_count": None,
        "completed_count": None,
        "sell_through": None,
        "source": "browse",
        # Filtering metadata
        "total_listings": total_count,
        "filtered_count": filtered_count,
        "signed_listings_detected": signed_count,
        "lot_listings_detected": lot_count,
        "include_signed": include_signed,
    }

    # Store in cache before returning
    _browse_cache[cache_key] = (stats, now + _BROWSE_CACHE_TTL)

    return stats


def fetch_market_stats_v2(isbn: str, include_sold_comps: bool = True) -> Dict[str, Any]:
    """
    Fetch market stats including active listings and sold comps.

    Args:
        isbn: ISBN to lookup
        include_sold_comps: If True, also fetch sold comps (Track A/B)

    Returns:
        Dict with active stats and optionally sold comps
    """
    try:
        stats = browse_active_by_isbn(isbn)

        # Add sold comps if requested
        if include_sold_comps:
            try:
                from .ebay_sold_comps import get_sold_comps
                sold = get_sold_comps(isbn)
                if sold:
                    stats["sold_comps_count"] = sold["count"]
                    stats["sold_comps_min"] = sold["min"]
                    stats["sold_comps_median"] = sold["median"]
                    stats["sold_comps_max"] = sold["max"]
                    stats["sold_comps_is_estimate"] = sold["is_estimate"]
                    stats["sold_comps_source"] = sold["source"]
                    stats["sold_comps_last_sold_date"] = sold.get("last_sold_date")
            except Exception:
                # Don't fail entire fetch if sold comps unavailable
                pass

        return stats
    except Exception as e:
        return {"error": str(e), "source": "browse"}


def collect_ebay_market_stats(
    isbns: Sequence[str],
    app_id: str,
    global_id: str = "EBAY-US",
    delay: float = 1.0,
    max_results: int = 20,
) -> Dict[str, EbayMarketStats]:
    if not isbns:
        return {}

    session = requests.Session()
    session.headers.update({
        "User-Agent": "ISBN-Lot-Optimizer/2.0 (market)",
        "Accept": "application/json",
    })

    stats: Dict[str, EbayMarketStats] = {}
    try:
        for idx, isbn in enumerate(isbns, start=1):
            try:
                result = query_ebay_market_snapshot(
                    session=session,
                    isbn=isbn,
                    app_id=app_id,
                    global_id=global_id,
                    max_results=max_results,
                )
            except Exception:
                result = None
            if result:
                stats[isbn] = result
            if delay:
                time.sleep(delay)
    finally:
        session.close()
    return stats


def _browse_active_by_isbn(isbn: str, limit: int = 50, include_signed: bool = False) -> Optional[Dict[str, Any]]:
    """
    Internal: Fetch active comps via eBay Browse API and return raw price list/currency.
    Returns None if no prices found or on HTTP error.
    Filters out multi-book lots and (optionally) signed copies.
    """
    # Keywords to filter out (case-insensitive)
    LOT_KEYWORDS = ["lot of", "set of", "bundle", "collection"]
    SIGNED_KEYWORDS = ["signed", "autographed", "signature"]

    tok = get_app_token()
    r = requests.get(
        BROWSE_URL,
        params={"gtin": isbn, "limit": str(limit)},
        headers={"Authorization": f"Bearer {tok}", "X-EBAY-C-MARKETPLACE-ID": MARKETPLACE},
        timeout=30,
    )
    if r.status_code != 200:
        return None
    js: Dict[str, Any] = r.json() or {}
    items = js.get("itemSummaries") or []
    prices: List[float] = []
    currency = None
    for it in items:
        if not isinstance(it, dict):
            continue

        # Extract title for filtering
        title = (it.get("title") or "").lower()

        # Check for problematic keywords
        is_lot = any(keyword in title for keyword in LOT_KEYWORDS)
        is_signed = any(keyword in title for keyword in SIGNED_KEYWORDS)

        # Filter logic
        if is_lot or (is_signed and not include_signed):
            continue

        pinfo = it.get("price") or {}
        p = pinfo.get("value")
        c = pinfo.get("currency")
        if p is not None:
            try:
                prices.append(float(p))
                currency = currency or c
            except Exception:
                pass
    if not prices:
        return None
    return {"prices": prices, "currency": currency, "raw": js}


def fetch_single_market_stat(
    isbn: str,
    app_id: str,
    global_id: str = "EBAY-US",
    max_results: int = 20,
) -> Optional[EbayMarketStats]:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "ISBN-Lot-Optimizer/2.0 (market-single)",
        "Accept": "application/json",
    })
    try:
        return query_ebay_market_snapshot(
            session=session,
            isbn=isbn,
            app_id=app_id,
            global_id=global_id,
            max_results=max_results,
        )
    finally:
        session.close()


def query_ebay_market_snapshot(
    session: requests.Session,
    isbn: str,
    app_id: str,
    global_id: str,
    max_results: int,
) -> Optional[EbayMarketStats]:
    active_response = call_ebay_finding(
        session=session,
        operation="findItemsByProduct",
        app_id=app_id,
        global_id=global_id,
        extra_params={
            "productId.@type": "ISBN",
            "productId": isbn,
            "paginationInput.entriesPerPage": str(max_results),
            "outputSelector": "SellerInfo",
        },
    )
    sold_response = call_ebay_finding(
        session=session,
        operation="findCompletedItems",
        app_id=app_id,
        global_id=global_id,
        extra_params={
            "productId.@type": "ISBN",
            "productId": isbn,
            "paginationInput.entriesPerPage": str(max_results),
            "outputSelector": "SellerInfo",
        },
    )

    if active_response is None and sold_response is None:
        # Fallback to Browse (active comps only)
        try:
            b = _browse_active_by_isbn(isbn, limit=max_results)
        except Exception:
            b = None
        if b:
            active_prices = b["prices"]
            active_avg = statistics.mean(active_prices) if active_prices else None
            active_med = statistics.median(active_prices) if active_prices else None
            return EbayMarketStats(
                isbn=isbn,
                active_count=len(active_prices),
                active_avg_price=round(active_avg, 2) if active_avg is not None else None,
                sold_count=0,
                sold_avg_price=None,
                sell_through_rate=None,  # sold history requires Marketplace Insights
                currency=b.get("currency"),
                active_median_price=round(active_med, 2) if active_med is not None else None,
                sold_median_price=None,
                unsold_count=None,
                raw_active=b.get("raw"),
                raw_sold=None,
            )
        return None

    active_items = extract_ebay_items(active_response, "findItemsByProductResponse") if active_response else []
    sold_items = extract_ebay_items(sold_response, "findCompletedItemsResponse") if sold_response else []

    active_prices, active_currency = gather_price_samples(active_items)
    sold_prices, sold_currency, sold_counts = gather_completed_samples(sold_items)

    # Optional: If both price arrays are empty, try Browse before bailing out
    if not active_prices and not sold_prices:
        try:
            b = _browse_active_by_isbn(isbn, limit=max_results)
        except Exception:
            b = None
        if b:
            active_prices = b["prices"]
            active_currency = b.get("currency")

    active_avg = statistics.mean(active_prices) if active_prices else None
    active_med = statistics.median(active_prices) if active_prices else None
    sold_avg = statistics.mean(sold_prices) if sold_prices else None
    sold_med = statistics.median(sold_prices) if sold_prices else None

    sold_count = sold_counts.get("sold", 0)
    unsold_count = sold_counts.get("unsold", 0)
    denominator = sold_count + unsold_count
    sell_through = (sold_count / denominator) if denominator else None

    currency = sold_currency or active_currency

    return EbayMarketStats(
        isbn=isbn,
        active_count=len(active_prices),
        active_avg_price=round(active_avg, 2) if active_avg is not None else None,
        sold_count=sold_count,
        sold_avg_price=round(sold_avg, 2) if sold_avg is not None else None,
        sell_through_rate=round(sell_through, 3) if sell_through is not None else None,
        currency=currency,
        active_median_price=round(active_med, 2) if active_med is not None else None,
        sold_median_price=round(sold_med, 2) if sold_med is not None else None,
        unsold_count=unsold_count,
        raw_active=active_response,
        raw_sold=sold_response,
    )


def call_ebay_finding(
    session: requests.Session,
    operation: str,
    app_id: str,
    global_id: str,
    extra_params: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    params = {
        "OPERATION-NAME": operation,
        "SERVICE-VERSION": "1.13.0",
        "SECURITY-APPNAME": app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "REST-PAYLOAD": "true",
        "GLOBAL-ID": global_id,
    }
    params.update(extra_params)
    try:
        response = session.get(EBAY_FINDING_URL, params=params, timeout=20)
        response.raise_for_status()
    except Exception:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def extract_ebay_items(payload: Dict[str, Any], root_key: str) -> List[Dict[str, Any]]:
    if not payload:
        return []
    root_any = payload.get(root_key)
    if not root_any:
        return []
    root_obj = root_any[0] if isinstance(root_any, list) and root_any else root_any
    if not isinstance(root_obj, dict):
        return []
    ack = _first_or_default(root_obj.get("ack"))
    if isinstance(ack, str) and ack.upper() != "SUCCESS":
        return []
    search_result_any = root_obj.get("searchResult")
    if not search_result_any:
        return []
    search_obj = search_result_any[0] if isinstance(search_result_any, list) and search_result_any else search_result_any
    if not isinstance(search_obj, dict):
        return []
    items_any = search_obj.get("item") or []
    if isinstance(items_any, list):
        return [i for i in items_any if isinstance(i, dict)]
    if isinstance(items_any, dict):
        return [items_any]
    return []


def gather_price_samples(items: Sequence[Dict[str, Any]]) -> Tuple[List[float], Optional[str]]:
    prices: List[float] = []
    currency = None
    for item in items:
        price, curr = extract_price(item)
        if price is not None:
            prices.append(price)
            currency = currency or curr
    return prices, currency


def gather_completed_samples(
    items: Sequence[Dict[str, Any]]
) -> Tuple[List[float], Optional[str], Dict[str, int]]:
    sold_prices: List[float] = []
    currency = None
    counts = {"sold": 0, "unsold": 0}
    for item in items:
        status = _first_or_default(item.get("sellingStatus")) or {}
        state = _first_or_default(status.get("sellingState"))
        price, curr = extract_price(item)
        if state == "EndedWithSales":
            counts["sold"] += 1
            if price is not None:
                sold_prices.append(price)
                currency = currency or curr
        else:
            counts["unsold"] += 1
    return sold_prices, currency, counts


def extract_price(item: Dict[str, Any], price_key: str = "currentPrice") -> Tuple[Optional[float], Optional[str]]:
    status = _first_or_default(item.get("sellingStatus")) or {}
    price_info = _first_or_default(status.get(price_key))
    if not price_info:
        price_info = _first_or_default(status.get("convertedCurrentPrice"))
    if not isinstance(price_info, dict):
        return None, None
    value = price_info.get("__value__")
    currency = price_info.get("@currencyId")
    num: Optional[float] = None
    if isinstance(value, (int, float, str)):
        try:
            num = float(value)
        except Exception:
            num = None
    return num, currency


def _first_or_default(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


# ==================== LOT PRICING ====================

class LotComp(TypedDict):
    """Single lot listing comp from eBay."""
    title: str
    price: float
    lot_size: int
    per_book_price: float
    currency: str
    item_id: str


class LotPricingResult(TypedDict):
    """Aggregated lot pricing analysis."""
    search_term: str
    total_comps: int
    lot_sizes: Dict[int, List[float]]  # lot_size -> list of per-book prices
    comps: List[LotComp]
    optimal_lot_size: Optional[int]
    optimal_per_book_price: Optional[float]
    avg_per_book_by_size: Dict[int, float]  # lot_size -> average per-book price


def parse_lot_size_from_title(title: str) -> Optional[int]:
    """
    Extract lot size from eBay listing title.

    Handles patterns like:
    - "Lot of 7"
    - "Lot 7"
    - "Set of 7 Books"
    - "7 Book Lot"
    - "7 Books"
    - "Complete Set 7"
    - "Lot 1st 12" / "Lot First 12"
    - "12 Novels"

    Args:
        title: eBay listing title

    Returns:
        Lot size as integer, or None if not found
    """
    title = title.lower()

    # Pattern 1: "lot of N", "set of N"
    match = re.search(r'(?:lot|set)\s+of\s+(\d+)', title)
    if match:
        return int(match.group(1))

    # Pattern 2: "lot 1st N", "lot first N", "set 1st N" (e.g., "Lot 1st 12 Alex Cross")
    match = re.search(r'(?:lot|set)\s+(?:1st|first|2nd|second|3rd|third|4th|fourth|5th|fifth|\d+(?:st|nd|rd|th)?)\s+(\d+)', title)
    if match:
        size = int(match.group(1))
        if 2 <= size <= 50:
            return size

    # Pattern 3: "lot N", "set N" (but not "lot 1" to avoid false positives)
    match = re.search(r'(?:lot|set)\s+(\d+)', title)
    if match:
        size = int(match.group(1))
        if size >= 2:  # Avoid matching single books
            return size

    # Pattern 4: "N book lot", "N books", "N novels"
    match = re.search(r'(\d+)\s+(?:books?|novels?)(?:\s+lot)?', title)
    if match:
        size = int(match.group(1))
        if 2 <= size <= 50:
            return size

    # Pattern 5: "complete set N", "full set N", "entire set N"
    match = re.search(r'(?:complete|full|entire)\s+set\s+(\d+)', title)
    if match:
        return int(match.group(1))

    # Pattern 6: "#N" (e.g., "#7") - but only if reasonable
    match = re.search(r'#\s*(\d+)', title)
    if match:
        size = int(match.group(1))
        if 2 <= size <= 50:
            return size

    return None


def search_ebay_lot_comps(
    search_term: str,
    limit: int = 50,
    marketplace: str = MARKETPLACE
) -> LotPricingResult:
    """
    Search eBay for lot listings and analyze per-book pricing.
    
    Args:
        search_term: Search query (e.g., "Alex Cross Lot", "James Patterson Books")
        limit: Maximum number of results to fetch
        marketplace: eBay marketplace ID
        
    Returns:
        LotPricingResult with pricing analysis
    """
    # Ensure search includes lot keywords
    if not any(keyword in search_term.lower() for keyword in ['lot', 'set', 'books', 'series']):
        search_term += " lot"
    
    # Search eBay Browse API
    tok = get_app_token()
    r = requests.get(
        BROWSE_URL,
        params={"q": search_term, "limit": str(limit)},
        headers={"Authorization": f"Bearer {tok}", "X-EBAY-C-MARKETPLACE-ID": marketplace},
        timeout=30,
    )
    
    if r.status_code != 200:
        return {
            "search_term": search_term,
            "total_comps": 0,
            "lot_sizes": {},
            "comps": [],
            "optimal_lot_size": None,
            "optimal_per_book_price": None,
            "avg_per_book_by_size": {},
        }
    
    js: Dict[str, Any] = r.json()
    items = cast(List[Dict[str, Any]], js.get("itemSummaries", []) or [])
    
    # Parse lot comps
    comps: List[LotComp] = []
    lot_sizes: Dict[int, List[float]] = {}
    
    for item in items:
        if not isinstance(item, dict):
            continue
        
        title = item.get("title", "")
        item_id = item.get("itemId", "")
        
        # Extract price
        price_info = item.get("price", {})
        price = price_info.get("value")
        currency = price_info.get("currency", "USD")
        
        if not price:
            continue
        
        try:
            price = float(price)
        except (ValueError, TypeError):
            continue
        
        # Parse lot size from title
        lot_size = parse_lot_size_from_title(title)
        if not lot_size or lot_size < 2:
            continue
        
        # Calculate per-book price
        per_book_price = price / lot_size
        
        # Store comp
        comp: LotComp = {
            "title": title,
            "price": price,
            "lot_size": lot_size,
            "per_book_price": per_book_price,
            "currency": currency,
            "item_id": item_id,
        }
        comps.append(comp)
        
        # Group by lot size
        if lot_size not in lot_sizes:
            lot_sizes[lot_size] = []
        lot_sizes[lot_size].append(per_book_price)
    
    # Calculate averages by lot size
    avg_per_book_by_size: Dict[int, float] = {}
    for size, prices in lot_sizes.items():
        avg_per_book_by_size[size] = statistics.mean(prices)
    
    # Find optimal lot size (highest average per-book price)
    optimal_lot_size: Optional[int] = None
    optimal_per_book_price: Optional[float] = None
    
    if avg_per_book_by_size:
        optimal_lot_size = max(avg_per_book_by_size.items(), key=lambda x: x[1])[0]
        optimal_per_book_price = avg_per_book_by_size[optimal_lot_size]
    
    return {
        "search_term": search_term,
        "total_comps": len(comps),
        "lot_sizes": lot_sizes,
        "comps": comps,
        "optimal_lot_size": optimal_lot_size,
        "optimal_per_book_price": optimal_per_book_price,
        "avg_per_book_by_size": avg_per_book_by_size,
    }


def get_lot_pricing_for_series(
    series_name: str,
    author_name: Optional[str] = None
) -> LotPricingResult:
    """
    Get lot pricing analysis for a book series.
    
    Args:
        series_name: Name of the series (e.g., "Alex Cross")
        author_name: Optional author name for more specific search
        
    Returns:
        LotPricingResult with pricing analysis
    """
    # Build search term
    if author_name:
        search_term = f"{author_name} {series_name} lot"
    else:
        search_term = f"{series_name} lot"
    
    return search_ebay_lot_comps(search_term)


# CLI test interface
if __name__ == "__main__":
    import sys
    import json
    
    if len(sys.argv) < 2:
        print("Usage: python -m isbn_lot_optimizer.market <series_name> [author_name]")
        print("Example: python -m isbn_lot_optimizer.market 'Alex Cross' 'James Patterson'")
        sys.exit(1)
    
    series = sys.argv[1]
    author = sys.argv[2] if len(sys.argv) > 2 else None
    
    result = get_lot_pricing_for_series(series, author)
    print(json.dumps(result, indent=2))
    
    print("\nLot Size Analysis:")
    for size in sorted(result["avg_per_book_by_size"].keys()):
        avg = result["avg_per_book_by_size"][size]
        count = len(result["lot_sizes"][size])
        print(f"  {size} books: ${avg:.2f}/book (n={count})")
    
    if result["optimal_lot_size"]:
        print(f"\nOptimal lot size: {result['optimal_lot_size']} books")
        print(f"Optimal per-book price: ${result['optimal_per_book_price']:.2f}")
