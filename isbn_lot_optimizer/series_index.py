from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

try:  # Avoid import errors if series_catalog has side effects
    from .series_catalog import CATALOG_PATH as SERIES_CATALOG_PATH
except Exception:  # pragma: no cover - fallback when module import fails
    SERIES_CATALOG_PATH = Path.home() / ".isbn_lot_optimizer" / "series_catalog.json"

DEFAULT_INDEX_PATH = Path.home() / ".isbn_lot_optimizer" / "series_index.json"
_AUTHOR_SPLIT_RE = re.compile(r"\s*(?:&| and | with |,|;|\+| featuring | feat\.? )\s*", re.IGNORECASE)
_SERIES_SUFFIX_RE = re.compile(r"\b(series|novels|books|collection|box set|set|saga)\b", re.IGNORECASE)
_VOLUME_PATTERNS = [
    re.compile(r"#\s*(\d{1,3})"),
    re.compile(r"\bbook\s*(\d{1,3})\b", re.IGNORECASE),
    re.compile(r"\bvol(?:ume)?\.?\s*(\d{1,3})\b", re.IGNORECASE),
    re.compile(r"\bpart\s*(\d{1,3})\b", re.IGNORECASE),
    re.compile(r"\((\d{1,3})(?:st|nd|rd|th)?\s*(?:book|novel)?\)", re.IGNORECASE),
]


@dataclass
class SeriesMatch:
    canonical_author: str
    canonical_series: str
    display_author: Optional[str]
    display_series: Optional[str]
    volume: Optional[int]
    title: Optional[str]
    expected_vols: Dict[str, str]
    known_isbns: Dict[str, Dict[str, Optional[int]]]
    last_enriched: Optional[int]


class SeriesIndex:
    """Disk-backed ledger of series membership for fast local routing."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or DEFAULT_INDEX_PATH).expanduser()
        self._lock = threading.Lock()
        self._series: Dict[str, Dict] = {}
        self._isbn_lookup: Dict[str, Dict] = {}
        self._dirty = False

    # --------------------------------------------------------------
    # Persistence helpers

    def load(self) -> "SeriesIndex":
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._series = data
            except Exception:
                self._series = {}
        self._normalise_entries()
        self._rebuild_isbn_lookup()
        return self

    def save(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            payload = json.dumps(self._series, ensure_ascii=False, indent=2)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(payload, encoding="utf-8")
            self._dirty = False

    def save_if_dirty(self) -> None:
        with self._lock:
            dirty = self._dirty
        if dirty:
            self.save()

    def known_isbns(self) -> set[str]:
        with self._lock:
            return set(self._isbn_lookup.keys())

    def canonical_authors(self) -> set[str]:
        with self._lock:
            return {
                entry.get("canonical_author")
                for entry in self._series.values()
                if entry.get("canonical_author")
            }

    def bootstrap_from_local_catalog(self, author: str, display_author: Optional[str] = None) -> bool:
        author_key = (author or "").strip().lower()
        if not author_key or not SERIES_CATALOG_PATH.exists():
            return False
        try:
            cache = json.loads(SERIES_CATALOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return False
        data = cache.get(author_key)
        if not isinstance(data, dict):
            return False

        display_name = display_author or author
        updated = False
        now = int(time.time())
        for series_name, titles in data.items():
            if not titles:
                continue
            existing = self._get_entry(display_name, series_name)
            expected = existing.get("expected_vols") if existing else {}
            if expected:
                continue
            self.add_expected_titles(display_name, series_name, titles, enriched_ts=now)
            entry = self._get_entry(display_name, series_name)
            if entry is not None:
                entry.setdefault("last_catalog_bootstrap", now)
                entry["display_author"] = entry.get("display_author") or display_name
            updated = True
        if updated:
            self._dirty = True
        return updated

    # --------------------------------------------------------------
    # Public API

    def route_isbn(self, isbn: str) -> Optional[SeriesMatch]:
        with self._lock:
            info = self._isbn_lookup.get(isbn)
            if not info:
                return None
            key = self._make_key(info["canonical_author"], info["canonical_series"])
            entry = self._series.get(key)
            if not entry:
                return None
            known = entry.get("known_isbns", {})
            record = known.get(isbn, {})
            return SeriesMatch(
                canonical_author=info["canonical_author"],
                canonical_series=info["canonical_series"],
                display_author=entry.get("display_author"),
                display_series=entry.get("display_series"),
                volume=record.get("volume"),
                title=record.get("title"),
                expected_vols=entry.get("expected_vols", {}),
                known_isbns=known,
                last_enriched=entry.get("last_enriched"),
            )

    def add_mapping(
        self,
        isbn: str,
        author: str,
        series: str,
        *,
        volume: Optional[int] = None,
        title: Optional[str] = None,
        enriched_ts: Optional[int] = None,
    ) -> None:
        canonical_author_value = canonical_author(author)
        canonical_series_value = canonical_series(series)
        if not (isbn and canonical_author_value and canonical_series_value):
            return

        vol_int = int(volume) if isinstance(volume, int) and volume > 0 else None

        with self._lock:
            key = self._make_key(canonical_author_value, canonical_series_value)
            entry = self._series.setdefault(
                key,
                {
                    "canonical_author": canonical_author_value,
                    "canonical_series": canonical_series_value,
                    "display_author": author,
                    "display_series": series,
                    "expected_vols": {},
                    "known_isbns": {},
                    "last_enriched": None,
                },
            )

            if author and (not entry.get("display_author")):
                entry["display_author"] = author
            if series and (not entry.get("display_series")):
                entry["display_series"] = series

            known = entry.setdefault("known_isbns", {})
            record = known.get(isbn)
            changed = False
            if record is None or record.get("volume") != vol_int or record.get("title") != title:
                known[isbn] = {"volume": vol_int, "title": title}
                changed = True

            self._isbn_lookup[isbn] = {
                "canonical_author": canonical_author_value,
                "canonical_series": canonical_series_value,
                "volume": known.get(isbn, {}).get("volume"),
            }

            if vol_int is not None:
                expected = entry.setdefault("expected_vols", {})
                key_vol = str(vol_int)
                if expected.get(key_vol) in (None, "") and (title or known[isbn].get("title")):
                    expected[key_vol] = title or known[isbn].get("title") or ""
                    changed = True

            if enriched_ts and entry.get("last_enriched") != enriched_ts:
                entry["last_enriched"] = enriched_ts
                changed = True

            if changed:
                self._dirty = True

    def add_expected_titles(
        self,
        author: str,
        series: str,
        titles: Iterable[str],
        *,
        enriched_ts: Optional[int] = None,
    ) -> None:
        canonical_author_value = canonical_author(author)
        canonical_series_value = canonical_series(series)
        if not (canonical_author_value and canonical_series_value):
            return
        with self._lock:
            key = self._make_key(canonical_author_value, canonical_series_value)
            entry = self._series.setdefault(
                key,
                {
                    "canonical_author": canonical_author_value,
                    "canonical_series": canonical_series_value,
                    "display_author": author,
                    "display_series": series,
                    "expected_vols": {},
                    "known_isbns": {},
                    "last_enriched": None,
                },
            )
            expected = entry.setdefault("expected_vols", {})
            for idx, title in enumerate(titles, start=1):
                expected.setdefault(str(idx), title)
            if enriched_ts:
                entry["last_enriched"] = enriched_ts
            self._dirty = True

    def expected_for(self, author: str, series: str) -> Dict[str, str]:
        entry = self._get_entry(author, series)
        return dict(entry.get("expected_vols", {})) if entry else {}

    def missing_for(self, author: str, series: str) -> set[str]:
        entry = self._get_entry(author, series)
        if not entry:
            return set()
        expected = set(entry.get("expected_vols", {}).keys())
        known = {
            str(meta.get("volume"))
            for meta in entry.get("known_isbns", {}).values()
            if meta.get("volume")
        }
        return expected - known

    def series_entries_for_author(self, author: str) -> Dict[str, Dict]:
        canonical_author_value = canonical_author(author)
        results: Dict[str, Dict] = {}
        if not canonical_author_value:
            return results
        with self._lock:
            for key, info in self._series.items():
                if info.get("canonical_author") == canonical_author_value:
                    results[info.get("canonical_series") or key] = info
        return results

    def get_entry(self, canonical_author_value: str, canonical_series_value: str) -> Optional[Dict]:
        key = self._make_key(canonical_author_value, canonical_series_value)
        with self._lock:
            return self._series.get(key)

    def mark_enriched(self, author: str, series: str, ts: Optional[int] = None) -> None:
        entry = self._get_entry(author, series)
        if entry is None:
            return
        with self._lock:
            entry["last_enriched"] = ts or int(time.time())
            self._dirty = True

    def rebuild_indexes(self) -> None:
        with self._lock:
            self._rebuild_isbn_lookup()

    # --------------------------------------------------------------
    # Internal helpers

    def _normalise_entries(self) -> None:
        with self._lock:
            for key, entry in list(self._series.items()):
                if not isinstance(entry, dict):
                    self._series.pop(key)
                    continue
                entry.setdefault("expected_vols", {})
                entry.setdefault("known_isbns", {})
                entry.setdefault("display_author", entry.get("display_author"))
                entry.setdefault("display_series", entry.get("display_series"))

    def _rebuild_isbn_lookup(self) -> None:
        lookup: Dict[str, Dict] = {}
        for entry in self._series.values():
            canonical_author_value = entry.get("canonical_author")
            canonical_series_value = entry.get("canonical_series")
            if not (canonical_author_value and canonical_series_value):
                continue
            for isbn, meta in entry.get("known_isbns", {}).items():
                lookup[isbn] = {
                    "canonical_author": canonical_author_value,
                    "canonical_series": canonical_series_value,
                    "volume": meta.get("volume"),
                }
        self._isbn_lookup = lookup

    def _get_entry(self, author: str, series: str) -> Optional[Dict]:
        canonical_author_value = canonical_author(author)
        canonical_series_value = canonical_series(series)
        if not (canonical_author_value and canonical_series_value):
            return None
        key = self._make_key(canonical_author_value, canonical_series_value)
        with self._lock:
            return self._series.get(key)

    @staticmethod
    def _make_key(canonical_author_value: str, canonical_series_value: str) -> str:
        return f"{canonical_author_value}|{canonical_series_value}"


# --------------------------------------------------------------
# Canonicalisation and parsing helpers


def canonical_author(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    lowered = name.strip().lower()
    if not lowered:
        return None
    parts = _AUTHOR_SPLIT_RE.split(lowered)
    primary = parts[0] if parts else lowered
    primary = re.sub(r"[^a-z0-9\s]", " ", primary)
    primary = re.sub(r"\s+", " ", primary).strip()
    return primary or None


def canonical_series(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    lowered = name.strip().lower()
    if not lowered:
        return None
    lowered = _SERIES_SUFFIX_RE.sub("", lowered)
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered or None


def parse_series_volume_hint(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    for pattern in _VOLUME_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                value = int(match.group(1))
                if value > 0:
                    return value
            except Exception:
                continue
    return None


def canonical_key(author: Optional[str], series: Optional[str]) -> Optional[Tuple[str, str]]:
    canonical_author_value = canonical_author(author)
    canonical_series_value = canonical_series(series)
    if canonical_author_value and canonical_series_value:
        return canonical_author_value, canonical_series_value
    return None


def now_ts() -> int:
    return int(time.time())
