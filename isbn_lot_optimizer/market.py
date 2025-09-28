from __future__ import annotations

import statistics
import time
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple, TypedDict, cast

import requests
from requests.auth import _basic_auth_str

from .models import EbayMarketStats

EBAY_FINDING_URL = "https://svcs.ebay.com/services/search/FindingService/v1"

# --- eBay Browse API (app token + active comps) ---
BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
MARKETPLACE = os.getenv("EBAY_MARKETPLACE", "EBAY_US")

class _TokenCache(TypedDict):
    access_token: Optional[str]
    expires_at: float

_token_cache: _TokenCache = {"access_token": None, "expires_at": 0.0}


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


def browse_active_by_isbn(isbn: str, limit: int = 50, marketplace: str = MARKETPLACE) -> Dict[str, Any]:
    tok = get_app_token()
    r = requests.get(
        BROWSE_URL,
        params={"gtin": isbn, "limit": str(limit)},
        headers={"Authorization": f"Bearer {tok}", "X-EBAY-C-MARKETPLACE-ID": marketplace},
        timeout=30,
    )
    if r.status_code != 200:
        return {"error": f"http_{r.status_code}", "body": r.text[:400], "source": "browse"}
    js: Dict[str, Any] = r.json()
    items = cast(List[Dict[str, Any]], js.get("itemSummaries", []) or [])
    prices: List[float] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        p = it.get("price", {}).get("value")
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
    }
    return stats


def fetch_market_stats_v2(isbn: str) -> Dict[str, Any]:
    try:
        return browse_active_by_isbn(isbn)
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


def _browse_active_by_isbn(isbn: str, limit: int = 50) -> Optional[Dict[str, Any]]:
    """
    Internal: Fetch active comps via eBay Browse API and return raw price list/currency.
    Returns None if no prices found or on HTTP error.
    """
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
