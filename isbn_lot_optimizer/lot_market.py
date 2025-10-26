from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from shared.ebay_auth import get_bearer_token

EBAY_FINDING_URL = "https://svcs.ebay.com/services/search/FindingService/v1"
BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
CACHE_PATH = Path.home() / ".isbn_lot_optimizer" / "lot_cache.json"
CACHE_TTL = 60 * 60 * 24  # 24h
_CACHE_LOCK = threading.Lock()


def _load_cache() -> Dict[str, Dict]:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: Dict[str, Dict]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _cache_key(author: Optional[str], series: Optional[str], theme: Optional[str]) -> str:
    parts = (author or "").strip().lower(), (series or "").strip().lower(), (theme or "").strip().lower()
    return "|".join(parts)


def _winsor(vals: List[float], p: float = 0.10) -> List[float]:
    xs = sorted(v for v in vals if isinstance(v, (int, float)) and v > 0)
    if len(xs) < 3:
        return xs
    k = max(1, int(len(xs) * p))
    trimmed = xs[k:-k]
    return trimmed or xs


def _median(vals: List[float]) -> Optional[float]:
    xs = _winsor(vals)
    if not xs:
        return None
    import statistics as st  # local import keeps module light for CLI startup

    return round(st.median(xs), 2)


def _browse_active(session: requests.Session, q: str, limit: int = 50) -> Tuple[Optional[float], int]:
    bearer = get_bearer_token(session=session)
    if not bearer:
        return (None, 0)
    params = {"q": q, "category_ids": "267", "limit": str(limit)}
    response = session.get(
        BROWSE_URL,
        params=params,
        headers={
            "Authorization": f"Bearer {bearer}",
            "X-EBAY-C-MARKETPLACE-ID": os.getenv("EBAY_MARKETPLACE", "EBAY_US"),
            "Accept": "application/json",
        },
        timeout=15,
    )
    if response.status_code != 200:
        return (None, 0)
    payload = response.json()
    prices: List[float] = []
    for item in payload.get("itemSummaries", []) or []:
        price = (item.get("price") or {}).get("value")
        try:
            prices.append(float(price))
        except Exception:
            pass
    return (_median(prices), len(prices))


def _finding_sold(
    session: requests.Session,
    app_id: str,
    q: str,
    entries: int = 100,
    delay: float = 1.2,
) -> Tuple[Optional[float], int]:
    params = {
        "OPERATION-NAME": "findCompletedItems",
        "SERVICE-VERSION": "1.13.0",
        "SECURITY-APPNAME": app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "REST-PAYLOAD": "",
        "keywords": q,
        "itemFilter(0).name": "SoldItemsOnly",
        "itemFilter(0).value": "true",
        "categoryId": "267",
        "paginationInput.entriesPerPage": str(entries),
    }
    response = session.get(EBAY_FINDING_URL, params=params, timeout=20)
    if response.status_code != 200:
        return (None, 0)
    payload = response.json()
    root = payload.get("findCompletedItemsResponse", [{}])[0]
    if root.get("ack", [""])[0] != "Success":
        return (None, 0)
    items = root.get("searchResult", [{}])[0].get("item") or []
    prices: List[float] = []
    for item in items:
        selling = item.get("sellingStatus", [{}])[0]
        sold_price = selling.get("currentPrice", [{}])[0].get("__value__")
        try:
            prices.append(float(sold_price))
        except Exception:
            pass
    time.sleep(delay)
    return (_median(prices), len(prices))


def build_lot_queries(author: str | None, series: str | None, theme: str | None) -> List[str]:
    queries: Dict[str, None] = {}
    if series:
        queries[f'"{series}" {author or ""} lot set'] = None
        queries[f'"{series}" lot set books'] = None
    if author:
        queries[f"{author} lot set"] = None
        queries[f"{author} book lot"] = None
    if theme:
        queries[f"{theme} lot set books"] = None
    if not queries:
        queries["book lot set"] = None
    return list(queries.keys())


def market_snapshot_for_lot(
    author: Optional[str],
    series: Optional[str],
    theme: Optional[str],
    session: requests.Session | None = None,
) -> Dict:
    cache_key = _cache_key(author, series, theme)
    now = int(time.time())
    with _CACHE_LOCK:
        cache = _load_cache()
        cached = cache.get(cache_key)
        if cached and now - cached.get("ts", 0) < CACHE_TTL:
            return cached

    sess = session or requests.Session()
    queries = build_lot_queries(author, series, theme)
    active_prices: List[float] = []
    sold_prices: List[float] = []
    active_count_total = 0
    sold_count_total = 0

    for query in queries:
        price, count = _browse_active(sess, query)
        if price:
            active_prices.append(price)
        active_count_total += count

    app_id = os.getenv("EBAY_APP_ID")
    if app_id:
        for query in queries:
            price, count = _finding_sold(sess, app_id, query)
            if price:
                sold_prices.append(price)
            sold_count_total += count

    snapshot = {
        "queries": queries,
        "active_median": _median(active_prices),
        "sold_median": _median(sold_prices),
        "active_count": active_count_total,
        "sold_count": sold_count_total,
        "source": "ebay_free",
        "ts": int(time.time()),
    }

    with _CACHE_LOCK:
        cache = _load_cache()
        cache[cache_key] = snapshot
        _save_cache(cache)

    return snapshot
