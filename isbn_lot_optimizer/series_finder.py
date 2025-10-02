"""Series detection helpers.

DEPRECATED: This module resolves series metadata for ISBNs using Open Library and Wikidata,
falling back to lightweight heuristics when network data is unavailable.

This module is being phased out in favor of the Hardcover GraphQL API integration
(services/hardcover.py and services/series_resolver.py).

For new code, prefer using the Hardcover-based series detection system.
This module is retained for backward compatibility only.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "series_finder module is deprecated. Use services.series_resolver (Hardcover integration) instead.",
    DeprecationWarning,
    stacklevel=2
)

import re
from typing import Dict, Optional, Tuple

import requests

_OPENLIB_BASE = "https://openlibrary.org"
_SERIES_INDEX_RE = re.compile(r"(?:#|book\s*)(\d+)", re.IGNORECASE)
_HEURISTIC_SERIES = {
    "jason bourne": "Jason Bourne",
    "jack ryan": "Jack Ryan",
    "harry potter": "Harry Potter",
    "cormoran strike": "Cormoran Strike",
    "womens murder club": "Women's Murder Club",
    "womens murder club": "Women's Murder Club",
    "prey" : "Lucas Davenport Prey",
    "stone barrington": "Stone Barrington",
}


def attach_series(meta: Dict[str, any], isbn: str, session: Optional[requests.Session] = None) -> Dict[str, any]:
    """Attach series data to a metadata dict (mutates and returns the dict)."""
    if not isinstance(meta, dict):
        return meta

    sess = session or requests.Session()
    series_info: Optional[Dict[str, any]] = None

    try:
        series_info = series_from_openlibrary(isbn, sess)
    except Exception:
        series_info = None

    if not series_info:
        try:
            series_info = series_from_wikidata(isbn, sess)
        except Exception:
            series_info = None

    if not series_info:
        series_info = _series_from_heuristic(meta)

    if series_info:
        meta.setdefault("series", series_info)
        if series_info.get("name"):
            meta.setdefault("series_name", series_info["name"])
        if series_info.get("index") is not None:
            meta.setdefault("series_index", series_info["index"])
        series_id = _series_identifier(series_info)
        if series_id:
            meta["series_id"] = series_id
    return meta


def series_from_openlibrary(isbn: str, session: requests.Session) -> Optional[Dict[str, any]]:
    if not isbn:
        return None
    try:
        edition = session.get(f"{_OPENLIB_BASE}/isbn/{isbn}.json", timeout=10)
        if edition.status_code != 200:
            return None
        ej = edition.json()
    except Exception:
        return None

    name, index, work_id = _series_from_openlibrary_payload(ej)
    if name:
        return _series_payload(name, index, {"openlibrary_work": work_id} if work_id else {})

    works = ej.get("works", []) or []
    for work in works:
        key = work.get("key")
        if not key:
            continue
        try:
            resp = session.get(f"{_OPENLIB_BASE}{key}.json", timeout=10)
            if resp.status_code != 200:
                continue
            wj = resp.json()
        except Exception:
            continue
        name, index, _ = _series_from_openlibrary_payload(wj)
        if name:
            return _series_payload(name, index, {"openlibrary_work": key})
    return None


def series_from_wikidata(isbn: str, session: requests.Session) -> Optional[Dict[str, any]]:
    query = f"""
    SELECT ?work ?workLabel ?series ?seriesLabel ?ord WHERE {{
      VALUES ?isbn {{ "{isbn}" }}
      ?ed (wdt:P212|wdt:P957) ?isbn .
      ?ed wdt:P629 ?work .
      OPTIONAL {{ ?work wdt:P179 ?series . }}
      OPTIONAL {{ ?work p:P179/ps:P179 ?series ;
                        p:P179/pq:P1545 ?ord . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }} LIMIT 1
    """
    try:
        resp = session.get(
            "https://query.wikidata.org/sparql",
            params={"format": "json", "query": query},
            headers={"User-Agent": "ISBN-Lot-Optimizer/series-resolver"},
            timeout=12,
        )
        if resp.status_code != 200:
            return None
        data = resp.json().get("results", {}).get("bindings", [])
        if not data:
            return None
        row = data[0]
        series_name = row.get("seriesLabel", {}).get("value")
        if not series_name:
            return None
        ord_value = row.get("ord", {}).get("value")
        try:
            index = int(ord_value) if ord_value and str(ord_value).isdigit() else None
        except Exception:
            index = None
        ids = {
            "wikidata_qid": _extract_qid(row.get("series", {}).get("value")),
            "work_qid": _extract_qid(row.get("work", {}).get("value")),
        }
        ids = {k: v for k, v in ids.items() if v}
        return _series_payload(series_name, index, ids)
    except Exception:
        return None


def _series_from_openlibrary_payload(payload: Dict[str, any]) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    if not isinstance(payload, dict):
        return None, None, None
    series = payload.get("series")
    if isinstance(series, list):
        series = series[0] if series else None
    name, index = _split_series(series if isinstance(series, str) else None)
    work_id = None
    if not name:
        name = payload.get("title")
    works = payload.get("works") or []
    if isinstance(works, list):
        for w in works:
            if isinstance(w, dict) and w.get("key"):
                work_id = w["key"]
                break
    return name, index, work_id


def _split_series(series: Optional[str]) -> Tuple[Optional[str], Optional[int]]:
    if not series:
        return None, None
    match = _SERIES_INDEX_RE.search(series)
    index = None
    if match:
        try:
            index = int(match.group(1))
        except Exception:
            index = None
    name = series.split("#")[0].strip().rstrip(",")
    return (name or series or None), index


def _series_payload(name: str, index: Optional[int], identifiers: Dict[str, str]) -> Dict[str, any]:
    payload: Dict[str, any] = {
        "name": name,
        "index": index,
        "id": {k: v for k, v in identifiers.items() if v},
    }
    return payload


def _series_identifier(series_info: Dict[str, any]) -> Optional[str]:
    if not isinstance(series_info, dict):
        return None
    ids = series_info.get("id") if isinstance(series_info.get("id"), dict) else {}
    if isinstance(ids, dict):
        for key in ("openlibrary_work", "wikidata_qid", "work_qid", "id"):
            if ids.get(key):
                return ids[key]
    name = series_info.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _series_from_heuristic(meta: Dict[str, any]) -> Optional[Dict[str, any]]:
    title_parts = [meta.get("title"), meta.get("subtitle"), meta.get("series_name")]
    title = " ".join(filter(None, title_parts)).lower()
    for key, value in _HEURISTIC_SERIES.items():
        if key in title:
            return _series_payload(value, None, {})
    return None


def _extract_qid(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value.rsplit("/", 1)[-1]


__all__ = ["attach_series", "series_from_openlibrary", "series_from_wikidata"]
