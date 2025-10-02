"""
DEPRECATED: OpenLibrary-based series catalog.

This module provides series detection via OpenLibrary API and is being phased out
in favor of the Hardcover GraphQL API integration (services/hardcover.py and
services/series_resolver.py).

For new code, prefer using the Hardcover-based series detection system.
This module is retained for backward compatibility only.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import warnings
from typing import Dict, List, Tuple

import requests

from .constants import TITLE_NORMALIZER

warnings.warn(
    "series_catalog module is deprecated. Use services.series_resolver (Hardcover integration) instead.",
    DeprecationWarning,
    stacklevel=2
)

CATALOG_DIR = Path.home() / ".isbn_lot_optimizer"
CATALOG_DIR.mkdir(parents=True, exist_ok=True)
CATALOG_PATH = CATALOG_DIR / "series_catalog.json"


@dataclass
class SeriesEntry:
    author: str
    series: str
    titles: List[str]              # canonical ordered titles
    order_map: Dict[str, int]      # normalized title -> 1-based index


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    return TITLE_NORMALIZER.sub(" ", s).strip()


def _load_cache() -> dict:
    if CATALOG_PATH.exists():
        try:
            return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_cache(cache: dict) -> None:
    CATALOG_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def _to_entry(author: str, series: str, titles: List[str]) -> SeriesEntry:
    normed = [t.strip() for t in titles if t and str(t).strip()]
    order_map = {_norm(t): i + 1 for i, t in enumerate(normed)}
    return SeriesEntry(author=author, series=series, titles=normed, order_map=order_map)


# --- Public API ---

def get_or_fetch_series_for_authors(authors: List[str], session: requests.Session | None = None) -> List[SeriesEntry]:
    """
    For each author, return a list of SeriesEntry. Uses local cache first, then attempts
    Open Library augmentation. Cache is updated on success.
    """
    session = session or requests.Session()
    cache = _load_cache()
    out: List[SeriesEntry] = []

    # seed with common franchises (good ordering signals)
    seeds = _builtin_seed()
    for a in authors:
        key = a.strip().lower()
        merged: Dict[str, List[str]] = {}
        # 1) cached
        if key in cache:
            for series_name, titles in cache[key].items():
                merged.setdefault(series_name, []).extend(titles)
        # 2) built-in seed
        if key in seeds:
            for series_name, titles in seeds[key].items():
                merged.setdefault(series_name, []).extend(titles)
        # 3) augment via Open Library
        try:
            ol = _fetch_author_series_from_openlibrary(a, session=session)
            for series_name, titles in ol.items():
                merged.setdefault(series_name, []).extend(titles)
        except Exception:
            # Network failures or parsing issues shouldn't break local usage
            pass

        # dedupe while preserving order
        entries: List[SeriesEntry] = []
        for series_name, titles in merged.items():
            seen = set()
            ordered: List[str] = []
            for t in titles:
                nt = _norm(t)
                if nt and nt not in seen:
                    ordered.append(t)
                    seen.add(nt)
            if ordered:
                entries.append(_to_entry(a, series_name, ordered))
        # update cache
        if entries:
            cache[key] = {e.series: e.titles for e in entries}
            out.extend(entries)

    _save_cache(cache)
    return out


def coverage_for_series(entry: SeriesEntry, owned_titles: List[str]) -> dict:
    """Return coverage stats for a single series."""
    owned_norm = {_norm(t) for t in owned_titles}
    total = len(entry.titles)
    have_idx: List[int] = []
    missing: List[Tuple[int, str]] = []
    for i, t in enumerate(entry.titles, 1):
        if _norm(t) in owned_norm:
            have_idx.append(i)
        else:
            missing.append((i, t))
    return {
        "series": entry.series,
        "author": entry.author,
        "total": total,
        "owned": len(have_idx),
        "have_numbers": have_idx,
        "missing": missing,   # list of (index, title)
        "complete": len(have_idx) == total and total > 0,
    }


# --- Helpers ---

def _builtin_seed() -> Dict[str, Dict[str, List[str]]]:
    """
    Curated seed for popular franchises—helps get a correct order quickly.
    Keys are lowercase author names.
    """
    return {
        "tom clancy": {
            "jack ryan": [
                "Patriot Games",
                "The Hunt for Red October",
                "The Cardinal of the Kremlin",
                "Clear and Present Danger",
                "The Sum of All Fears",
                "Debt of Honor",
                "Executive Orders",
                "Rainbow Six",
                "The Bear and the Dragon",
                "Red Rabbit",
                "The Teeth of the Tiger",
                "Dead or Alive",
                "Locked On",
                "Threat Vector",
                "Command Authority",
                "Support and Defend",
                "Full Force and Effect",
                "Commander-in-Chief",
                "True Faith and Allegiance",
                "Point of Contact",
                "Power and Empire",
                "Line of Sight",
                "Oath of Office",
                "Code of Honor",
                "Firing Point",
                "Shadow of the Dragon",
                "Chain of Command",
                "Zero Hour",
                "Red Winter",
                "Weapons Grade",
            ]
        },
        "james patterson": {
            "alex cross": [
                "Along Came a Spider",
                "Kiss the Girls",
                "Jack & Jill",
                "Cat & Mouse",
                "Pop Goes the Weasel",
                "Roses Are Red",
                "Violets Are Blue",
                "Four Blind Mice",
                "The Big Bad Wolf",
                "London Bridges",
                "Mary, Mary",
                "Cross",
                "Double Cross",
                "Cross Country",
                "Alex Cross's Trial",
                "I, Alex Cross",
                "Cross Fire",
                "Kill Alex Cross",
                "Merry Christmas, Alex Cross",
                "Alex Cross, Run",
                "Cross My Heart",
                "Hope to Die",
                "Cross Justice",
                "Cross Kill",
                "Cross the Line",
                "The People vs. Alex Cross",
                "Target: Alex Cross",
                "Criss Cross",
                "Deadly Cross",
                "Fear No Evil",
                "Triple Cross",
                "Alex Cross Must Die",
            ]
        },
        "joshua hood": {
            "treadstone": [
                "Robert Ludlum's The Treadstone Resurrection",
                "Robert Ludlum's The Treadstone Exile",
                "Robert Ludlum's The Treadstone Transgression",
                "Robert Ludlum's The Treadstone Rendition",
            ]
        },
        "robert ludlum": {
            "jason bourne": [
                "The Bourne Identity",
                "The Bourne Supremacy",
                "The Bourne Ultimatum",
                "The Bourne Legacy",
                "The Bourne Betrayal",
                "The Bourne Sanction",
                "The Bourne Deception",
                "The Bourne Objective",
                "The Bourne Dominion",
                "The Bourne Imperative",
                "The Bourne Retribution",
                "The Bourne Ascendancy",
                "The Bourne Enigma",
                "The Bourne Initiative",
                "The Bourne Evolution",
                "The Bourne Treachery",
                "The Bourne Sacrifice",
            ]
        },
    }


def _fetch_author_series_from_openlibrary(author: str, session: requests.Session) -> Dict[str, List[str]]:
    """
    Try to infer series for an author via Open Library signals.
    Strategy:
    - Find works by author
    - Collect any 'series' hints from edition metadata & subjects
    - Cluster by common series token
    """
    url = "https://openlibrary.org/search.json"
    r = session.get(url, params={"author": author, "limit": 100}, timeout=20)
    r.raise_for_status()
    data = r.json()
    buckets: Dict[str, List[str]] = {}
    for doc in data.get("docs", []):
        title = (doc.get("title") or "").strip()
        if not title:
            continue
        # series names sometimes appear in 'series' or 'subtitle' or 'subject'
        cand = None
        if isinstance(doc.get("series"), list) and doc["series"]:
            cand = doc["series"][0]
        elif doc.get("subtitle"):
            # e.g. "A Jack Ryan Novel"
            m = re.search(r"(a|the)\s+(.+?)\s+novel", doc["subtitle"], re.I)
            if m:
                cand = m.group(2)
        if not cand:
            subjects = doc.get("subject", []) or []
            for s in subjects[:5]:
                if "series" in s.lower():
                    cand = s.split(" series")[0]
                    break
        if cand:
            key = _norm(cand)
            if key:
                buckets.setdefault(key, []).append(title)

    # Tidy series names, prefer concise display label
    out: Dict[str, List[str]] = {}
    for key, titles in buckets.items():
        display = key.title()
        out[display] = titles
    return out
