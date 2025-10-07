from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
import re
import time
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, cast

import requests

from .author_aliases import canonical_author, display_label as alias_display_label
from .booksrun import (
    BooksRunAPIError,
    DEFAULT_BASE_URL as BOOKSRUN_DEFAULT_BASE_URL,
    fetch_offer as fetch_booksrun_offer,
    normalise_condition as normalize_booksrun_condition,
)
from .constants import BOOKSRUN_FALLBACK_KEY, BOOKSRUN_FALLBACK_AFFILIATE, COVER_CHOICES, TITLE_NORMALIZER
from .database import DatabaseManager
from .metadata import create_http_session, enrich_authorship, fetch_metadata
from .series_index import (
    SeriesIndex,
    canonical_series,
    now_ts,
    parse_series_volume_hint,
)
from .models import BookEvaluation, BookMetadata, BooksRunOffer, EbayMarketStats, LotCandidate, LotSuggestion
from .probability import build_book_evaluation
from .lots import build_lots_with_strategies, generate_lot_suggestions
from .series_catalog import get_or_fetch_series_for_authors
from .series_finder import attach_series
from .market import fetch_single_market_stat, fetch_market_stats_v2
from .lot_market import market_snapshot_for_lot
from .lot_scoring import score_lot
from .utils import normalise_isbn, read_isbn_csv

# Re-export for backward compatibility (gui.py imports this)
# New code should import from constants.py directly
__all__ = ["BookService", "COVER_CHOICES"]


def _normalise_title(text: Optional[str]) -> str:
    if not text:
        return ""
    value = str(text).lower()
    return TITLE_NORMALIZER.sub(" ", value).strip()


class BookService:

    def __init__(
        self,
        database_path: Path,
        *,
        ebay_app_id: Optional[str] = None,
        ebay_global_id: str = "EBAY-US",
        ebay_delay: float = 1.0,
        ebay_entries: int = 20,
        metadata_delay: float = 0.0,
        booksrun_api_key: Optional[str] = None,
        booksrun_affiliate_id: Optional[str] = None,
        booksrun_base_url: Optional[str] = None,
        booksrun_timeout: Optional[float] = None,
    ) -> None:
        self.db = DatabaseManager(database_path)
        self.metadata_session = create_http_session()
        self.metadata_delay = metadata_delay
        self.ebay_app_id = ebay_app_id
        self.ebay_global_id = ebay_global_id
        self.ebay_delay = ebay_delay
        self.ebay_entries = ebay_entries
        self.series_index = SeriesIndex().load()
        self._series_index_registered_isbns: set[str] = set(self.series_index.known_isbns())
        self._series_index_bootstrapped: set[str] = set(self.series_index.canonical_authors())
        self._lot_manual_cache: dict[str, str] = {}
        self._series_catalog_fetched: set[str] = set()
        # Standardize on BOOKSRUN_KEY (deprecated: BOOKSRUN_API_KEY)
        key_from_env = os.getenv("BOOKSRUN_KEY") or os.getenv("BOOKSRUN_API_KEY")
        if os.getenv("BOOKSRUN_API_KEY") and not os.getenv("BOOKSRUN_KEY"):
            import warnings
            warnings.warn(
                "BOOKSRUN_API_KEY is deprecated. Please use BOOKSRUN_KEY instead.",
                DeprecationWarning,
                stacklevel=2
            )
        self.booksrun_api_key = (
            booksrun_api_key
            if booksrun_api_key is not None
            else (key_from_env or BOOKSRUN_FALLBACK_KEY)
        )

        # Standardize on BOOKSRUN_AFFILIATE_ID (deprecated: BOOKSRUN_AFK)
        affiliate_from_env = os.getenv("BOOKSRUN_AFFILIATE_ID") or os.getenv("BOOKSRUN_AFK")
        if os.getenv("BOOKSRUN_AFK") and not os.getenv("BOOKSRUN_AFFILIATE_ID"):
            import warnings
            warnings.warn(
                "BOOKSRUN_AFK is deprecated. Please use BOOKSRUN_AFFILIATE_ID instead.",
                DeprecationWarning,
                stacklevel=2
            )
        self.booksrun_affiliate_id = (
            booksrun_affiliate_id
            if booksrun_affiliate_id is not None
            else (affiliate_from_env or BOOKSRUN_FALLBACK_AFFILIATE)
        )
        base_url_env = os.getenv("BOOKSRUN_BASE_URL")
        self.booksrun_base_url = booksrun_base_url or base_url_env or BOOKSRUN_DEFAULT_BASE_URL
        timeout_env = os.getenv("BOOKSRUN_TIMEOUT")
        self.booksrun_timeout = (
            float(booksrun_timeout)
            if booksrun_timeout is not None
            else float(timeout_env) if timeout_env else 15.0
        )
        self._booksrun_session: Optional[requests.Session] = None

    # ------------------------------------------------------------------
    # Public API

    def close(self) -> None:
        """
        Clean up all resources: HTTP sessions and database connections.

        Note: In the future, we could further centralize HTTP session management
        by passing self.metadata_session to market.py, lot_market.py, and other
        modules that currently create their own requests.Session() instances.
        This would reduce overhead and improve connection reuse.
        """
        self.metadata_session.close()
        self.series_index.save_if_dirty()
        if self._booksrun_session:
            try:
                self._booksrun_session.close()
            except Exception:
                pass
        # Close database connection
        try:
            self.db.close()
        except Exception:
            pass

    def scan_isbn(
        self,
        raw_isbn: str,
        *,
        condition: str = "Good",
        edition: Optional[str] = None,
        include_market: bool = True,
        recalc_lots: bool = True,
    ) -> BookEvaluation:
        original_isbn = raw_isbn.strip()
        normalized = normalise_isbn(original_isbn)
        if not normalized:
            raise ValueError(f"Unrecognised ISBN: {original_isbn}")

        metadata_payload = fetch_metadata(self.metadata_session, normalized, delay=self.metadata_delay)
        metadata = self._build_metadata_from_payload(normalized, metadata_payload)

        existing_row = self.db.fetch_book(normalized)
        existing_quantity = 1
        if existing_row:
            try:
                raw_source = existing_row["source_json"] if "source_json" in existing_row.keys() else None
            except Exception:
                raw_source = None
            try:
                existing_source = json.loads(raw_source) if raw_source else {}
            except Exception:
                existing_source = {}
            try:
                existing_quantity = int(existing_source.get("quantity") or 1)
            except Exception:
                existing_quantity = 1
            if metadata is None:
                existing = self._row_to_evaluation(existing_row)
                metadata = existing.metadata

        market_stats: Optional[EbayMarketStats] = None
        if include_market and self.ebay_app_id:
            market_stats = fetch_single_market_stat(
                isbn=normalized,
                app_id=self.ebay_app_id,
                global_id=self.ebay_global_id,
                max_results=self.ebay_entries,
            )

        evaluation = build_book_evaluation(
            isbn=normalized,
            original_isbn=original_isbn,
            metadata=metadata,
            market=market_stats,
            condition=condition,
            edition=edition,
        )
        evaluation.quantity = max(1, existing_quantity)

        self._register_book_in_series_index(evaluation)
        # Try Browse API median as a better price anchor; keep $10 minimum rule
        booksrun_offer: Optional[BooksRunOffer] = None
        if include_market:
            booksrun_offer = self._fetch_booksrun_offer(normalized, condition=condition)
        v2_stats_result = None
        try:
            v2_stats_result = fetch_market_stats_v2(normalized)
            median_price = v2_stats_result.get("median_price")
            if isinstance(median_price, (int, float)):
                evaluation.estimated_price = max(10.0, float(median_price))
        except Exception:
            pass

        self._apply_booksrun_to_evaluation(evaluation, booksrun_offer)
        self._persist_book(evaluation, v2_stats=v2_stats_result)
        if recalc_lots:
            self.recalculate_lots()
        return evaluation

    def import_csv(
        self,
        path: Path,
        *,
        condition: str = "Good",
        edition: Optional[str] = None,
        include_market: bool = True,
    ) -> List[BookEvaluation]:
        rows, _, isbn_field = read_isbn_csv(path)
        evaluations: List[BookEvaluation] = []
        for row in rows:
            raw_isbn = (row.get(isbn_field) or "").strip()
            if not raw_isbn:
                continue
            try:
                evaluation = self.scan_isbn(
                    raw_isbn,
                    condition=row.get("condition", condition) or condition,
                    edition=row.get("edition", edition) or edition,
                    include_market=include_market,
                )
                evaluations.append(evaluation)
            except Exception:
                continue
        return evaluations

    def refresh_book_market(self, isbn: str, *, recalc_lots: bool = True) -> Optional[BookEvaluation]:
        """
        Refresh market stats for a single ISBN and persist the updated evaluation.
        Uses Finding API (if AppID is configured) and Browse median price override when available.
        """
        row = self.db.fetch_book(isbn)
        if not row:
            return None
        existing = self._row_to_evaluation(row)

        market_stats: Optional[EbayMarketStats] = None
        if self.ebay_app_id:
            try:
                market_stats = fetch_single_market_stat(
                    isbn=isbn,
                    app_id=self.ebay_app_id,
                    global_id=self.ebay_global_id,
                    max_results=self.ebay_entries,
                )
            except Exception:
                market_stats = None

        evaluation = build_book_evaluation(
            isbn=existing.isbn,
            original_isbn=existing.original_isbn,
            metadata=existing.metadata,
            market=market_stats,
            condition=existing.condition,
            edition=existing.edition,
        )
        evaluation.quantity = max(1, getattr(existing, "quantity", 1))

        self._register_book_in_series_index(evaluation)
        # Try Browse API median as a better price anchor; keep $10 minimum rule
        v2_stats_result = None
        try:
            v2_stats_result = fetch_market_stats_v2(isbn)
            median_price = v2_stats_result.get("median_price")
            if isinstance(median_price, (int, float)):
                evaluation.estimated_price = max(10.0, float(median_price))
        except Exception:
            pass

        booksrun_offer = self._fetch_booksrun_offer(isbn, condition=existing.condition)
        self._apply_booksrun_to_evaluation(evaluation, booksrun_offer)
        self._persist_book(evaluation, v2_stats=v2_stats_result)
        if recalc_lots:
            self.recalculate_lots()
        return evaluation

    def list_books(self) -> List[BookEvaluation]:
        rows = self.db.fetch_all_books()
        return [self._row_to_evaluation(row) for row in rows]

    def get_all_books(self) -> List[BookEvaluation]:
        """Return all books currently stored in the database."""
        return self.list_books()

    def get_book(self, isbn: str) -> Optional[BookEvaluation]:
        normalized = normalise_isbn(isbn)
        if not normalized:
            return None
        row = self.db.fetch_book(normalized)
        if not row:
            return None
        return self._row_to_evaluation(row)

    def set_book_quantity(self, isbn: str, quantity: int) -> Optional[BookEvaluation]:
        normalized = normalise_isbn(isbn)
        if not normalized:
            return None
        row = self.db.fetch_book(normalized)
        if not row:
            return None
        try:
            source_raw = row["source_json"] if "source_json" in row.keys() else None
        except Exception:
            source_raw = None
        try:
            source_dict = json.loads(source_raw) if source_raw else {}
        except Exception:
            source_dict = {}
        try:
            new_quantity = max(1, int(quantity))
        except Exception:
            new_quantity = 1
        source_dict["quantity"] = new_quantity
        self.db.update_book_source_json(normalized, source_dict)
        updated_row = self.db.fetch_book(normalized)
        return self._row_to_evaluation(updated_row) if updated_row else None

    def increment_book_quantity(self, isbn: str, delta: int = 1) -> Optional[BookEvaluation]:
        try:
            delta_int = int(delta)
        except Exception:
            delta_int = 0
        current = self.get_book(isbn)
        if not current:
            return None
        if delta_int == 0:
            return current
        new_quantity = max(1, current.quantity + delta_int)
        return self.set_book_quantity(current.isbn, new_quantity)

    def _update_book_fields_single(
        self,
        isbn: str,
        fields: Dict[str, Any],
        *,
        raise_if_missing: bool = True,
    ) -> bool:
        normalized = normalise_isbn(isbn)
        if not normalized:
            if raise_if_missing:
                raise ValueError("Invalid ISBN")
            return False

        row = self.db.fetch_book(normalized)
        if not row:
            if raise_if_missing:
                raise ValueError(f"Book {isbn} not found")
            return False

        try:
            meta = json.loads(row["metadata_json"] or "{}")
        except Exception:
            meta = {}
        raw_meta = meta.get("raw") if isinstance(meta.get("raw"), dict) else {}
        if not isinstance(raw_meta, dict):
            raw_meta = {}
        meta["raw"] = raw_meta

        column_updates: Dict[str, Any] = {}
        metadata_changed = False

        for key, value in fields.items():
            if key == "title":
                column_updates["title"] = value
                meta["title"] = value
                raw_meta["title"] = value
                metadata_changed = True
            elif key == "authors":
                if isinstance(value, str):
                    authors_list = [part.strip() for part in value.split(",") if part.strip()]
                elif isinstance(value, Iterable):
                    authors_list = [str(part).strip() for part in value if str(part).strip()]
                else:
                    authors_list = []
                if not authors_list:
                    authors_list = ["Unknown"]
                column_updates["authors"] = "; ".join(authors_list)
                meta["authors"] = authors_list
                meta["authors_str"] = ", ".join(authors_list)
                raw_meta["authors"] = authors_list
                meta = enrich_authorship(meta)
                metadata_changed = True
            elif key == "edition":
                value_or_none = value if value else None
                column_updates["edition"] = value_or_none
                meta["edition"] = value_or_none
                raw_meta["edition"] = value_or_none
                metadata_changed = True
            elif key == "condition":
                column_updates["condition"] = value if value else None
            elif key == "probability_label":
                column_updates["probability_label"] = value if value else None
            elif key == "probability_score":
                try:
                    column_updates["probability_score"] = float(value) if value is not None else None
                except Exception:
                    pass
            elif key == "cover_type":
                selected = value if value in COVER_CHOICES else "Unknown"
                raw_meta["cover_type"] = selected
                metadata_changed = True
            elif key == "printing":
                raw_meta["printing"] = value if value else None
                metadata_changed = True
            else:
                raw_meta[key] = value
                metadata_changed = True

        meta["raw"] = raw_meta
        metadata_payload = meta if metadata_changed else None
        # Skip database writes if nothing changed
        if not column_updates and metadata_payload is None:
            return False

        self.db.update_book_record(normalized, columns=column_updates, metadata=metadata_payload)

        updated = self.get_book(normalized)
        if updated:
            self._register_book_in_series_index(updated)
        return True

    def update_book_fields(self, isbn: str, fields: Dict[str, Any]) -> None:
        changed = self._update_book_fields_single(isbn, fields, raise_if_missing=True)
        if changed:
            self.series_index.save_if_dirty()
            self.recalculate_lots()

    def update_books_fields(self, isbns: Iterable[str], fields: Dict[str, Any]) -> int:
        updated_count = 0
        for isbn in isbns:
            try:
                changed = self._update_book_fields_single(isbn, fields, raise_if_missing=False)
            except Exception:
                continue
            if changed:
                updated_count += 1
        if updated_count:
            self.series_index.save_if_dirty()
            self.recalculate_lots()
        return updated_count

    def delete_books(self, isbns: Iterable[str]) -> int:
        normalized_isbns: List[str] = []
        for isbn in isbns:
            norm = normalise_isbn(isbn)
            if norm:
                normalized_isbns.append(norm)
        if not normalized_isbns:
            return 0
        deleted = self.db.delete_books(normalized_isbns)
        if deleted:
            self.recalculate_lots()
        return deleted

    def refresh_books(
        self,
        isbns: Iterable[str],
        *,
        requery_market: bool = True,
        requery_metadata: bool = False,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        normalized_isbns: List[str] = []
        for raw in isbns:
            norm = normalise_isbn(raw)
            if norm:
                normalized_isbns.append(norm)
        total = len(normalized_isbns)
        if progress_cb:
            try:
                progress_cb(0, total)
            except Exception:
                pass
        refreshed = 0
        for index, isbn in enumerate(normalized_isbns, start=1):
            evaluation = self._refresh_single_book(
                isbn,
                requery_market=requery_market,
                requery_metadata=requery_metadata,
            )
            if evaluation:
                refreshed += 1
            if progress_cb:
                try:
                    progress_cb(index, total)
                except Exception:
                    pass
        if refreshed:
            self.recalculate_lots()
        return refreshed

    def refresh_booksrun_all(
        self,
        *,
        delay: Optional[float] = None,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        """
        Refresh BooksRun offers for all books without touching eBay stats/metadata.
        Polite rate limiting via 'delay' seconds between calls (default from BOOKSRUN_DELAY or 0.2).
        """
        try:
            rows = self.db.fetch_all_books()
        except Exception:
            rows = []
        isbns: list[str] = []
        for row in rows:
            try:
                code = row["isbn"]
            except Exception:
                code = None
            if code:
                isbns.append(str(code))
        total = len(isbns)
        if total == 0:
            if progress_cb:
                try:
                    progress_cb(0, 0)
                except Exception:
                    pass
            return 0

        # Determine delay
        if delay is None:
            try:
                delay = float(os.getenv("BOOKSRUN_DELAY", "0.2"))
            except Exception:
                delay = 0.2

        # Ensure a session for connection reuse
        if self._booksrun_session is None:
            try:
                self._booksrun_session = requests.Session()
            except Exception:
                self._booksrun_session = None

        count = 0
        for idx, isbn in enumerate(isbns, start=1):
            try:
                evaluation = self._refresh_single_book(
                    isbn,
                    requery_market=False,
                    requery_metadata=False,
                    requery_booksrun=True,
                )
                if evaluation:
                    count += 1
            except Exception:
                # Continue on errors
                pass
            if progress_cb:
                try:
                    progress_cb(idx, total)
                except Exception:
                    pass
            if idx < total and delay and delay > 0:
                try:
                    time.sleep(delay)
                except Exception:
                    pass

        if count:
            self.recalculate_lots()
        return count

    def rename_authors(
        self,
        mapping: Dict[str, str],
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        """
        Rename author display names across the catalog.

        mapping: dict of raw_name -> canonical_name to apply. Matches are exact string matches
        on the delimited 'authors' column and in metadata_json authors lists.

        Returns the number of rows updated.
        """
        if not mapping:
            return 0
        try:
            rows = self.db.fetch_all_books()
        except Exception:
            rows = []
        total = len(rows)
        updated = 0
        for idx, row in enumerate(rows, start=1):
            try:
                raw_authors = row["authors"] or ""
            except Exception:
                raw_authors = ""
            # Split authors by ';' or ',' preserving order
            parts_raw: list[str] = []
            for token in re.split(r";|,", str(raw_authors)):
                t = token.strip()
                if t:
                    parts_raw.append(t)
            if not parts_raw:
                if progress_cb:
                    try:
                        progress_cb(idx, total)
                    except Exception:
                        pass
                continue

            # Apply mapping
            new_parts: list[str] = []
            seen_local: set[str] = set()
            changed = False
            for name in parts_raw:
                renamed = mapping.get(name, name)
                if renamed != name:
                    changed = True
                if renamed not in seen_local:
                    new_parts.append(renamed)
                    seen_local.add(renamed)

            if not changed:
                if progress_cb:
                    try:
                        progress_cb(idx, total)
                    except Exception:
                        pass
                continue

            # Prepare updated metadata
            try:
                meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
            except Exception:
                meta = {}
            if not isinstance(meta, dict):
                meta = {}
            meta["authors"] = list(new_parts)
            meta["credited_authors"] = list(new_parts)
            meta["authors_str"] = ", ".join(new_parts)
            # Recompute canonical fields using existing pipeline
            try:
                meta = enrich_authorship(meta)
            except Exception:
                pass

            # Persist updated authors column and metadata
            try:
                isbn_code = str(row["isbn"])
            except Exception:
                isbn_code = None
            if isbn_code:
                try:
                    self.db.update_book_record(
                        isbn_code,
                        columns={"authors": "; ".join(new_parts)},
                        metadata=meta,
                    )
                    updated += 1
                except Exception:
                    pass

            if progress_cb:
                try:
                    progress_cb(idx, total)
                except Exception:
                    pass

        if updated:
            # Refresh lots after cleanup
            self.recalculate_lots()
        return updated

    def search_books(self, query: str) -> List[BookEvaluation]:
        """
        Search books by ISBN/title/authors using DatabaseManager.search_books.
        """
        rows = self.db.search_books(query)
        return [self._row_to_evaluation(row) for row in rows]

    def list_lots(self) -> List[LotSuggestion]:
        rows = self.db.fetch_lots()
        suggestions: List[LotSuggestion] = []
        for row in rows:
            book_isbns = json.loads(row["book_isbns"]) if row["book_isbns"] else []
            justification_lines = (row["justification"] or "").split("\n") if row["justification"] else []
            lot = LotSuggestion(
                name=row["name"],
                strategy=row["strategy"],
                book_isbns=book_isbns,
                estimated_value=row["estimated_value"] or 0.0,
                probability_score=row["probability_score"] or 0.0,
                probability_label=row["probability_label"] or "Unknown",
                sell_through=row["sell_through"],
                justification=justification_lines,
            )
            # Add the database ID to the lot object
            lot.id = row["id"]
            try:
                books_for_lot = self.get_books_for_lot(lot)
            except Exception:
                books_for_lot = []
            if books_for_lot:
                lot.books = tuple(books_for_lot)
                canonical_value, display_label_value, _ = self._author_labels_for_books(books_for_lot)
                lot.display_author_label = display_label_value
                lot.canonical_author = canonical_value
                if not lot.series_name:
                    lot.series_name = books_for_lot[0].metadata.series_name or None
            cache_key = self._lot_cache_key(lot)
            cached_blob = self._lot_manual_cache.get(cache_key)
            if cached_blob:
                setattr(lot, "market_json", cached_blob)
            suggestions.append(lot)
        return suggestions

    def clear_database(self) -> None:
        """Remove all stored books and lot records."""
        self.db.clear()
        self._lot_manual_cache.clear()
        self._series_index_registered_isbns.clear()

    def current_lots(self) -> List[LotSuggestion]:
        """
        Return the current lots to display in the GUI.
        Currently proxies to list_lots(), which reads the persisted set.
        """
        return self.list_lots()

    def build_lot_candidates(self) -> List[LotCandidate]:
        books = self.list_books()
        if not books:
            return []

        self._sync_series_index_books(books)
        isbn_map = {book.isbn: book for book in books}

        if hasattr(self, "lot_strategies") and getattr(self, "lot_strategies"):
            suggestions = build_lots_with_strategies(books, set(self.lot_strategies))
        else:
            suggestions = generate_lot_suggestions(books)

        author_groups: Dict[str, List[BookEvaluation]] = defaultdict(list)
       
        author_display_map: Dict[str, str] = {}
        for book in books:
            credited = list(getattr(book.metadata, "credited_authors", ())) or [
                a.strip() for a in book.metadata.authors if a and a.strip()
            ]
            canonical_name = getattr(book.metadata, "canonical_author", None)
            if not canonical_name and credited:
                canonical_name = alias_canonical_author(credited[0]) or credited[0]
            if not canonical_name:
                continue
            author_groups[canonical_name].append(book)
            if canonical_name not in author_display_map and credited:
                author_display_map[canonical_name] = credited[0]

        for canonical_name, grouped_books in author_groups.items():
            if canonical_name in self._series_index_bootstrapped:
                continue
            display_author = author_display_map.get(canonical_name, canonical_name)
            try:
                updated = self.series_index.bootstrap_from_local_catalog(display_author, display_author=display_author)
                if not updated and display_author != canonical_name:
                    updated = self.series_index.bootstrap_from_local_catalog(canonical_name, display_author=display_author)
                if updated or canonical_name in self.series_index.canonical_authors():
                    self._series_index_bootstrapped.add(canonical_name)
            except Exception:
                continue

        def resolve_series(
            author_display: Optional[str],
            canonical_author_value: Optional[str],
            lot_books: Sequence[BookEvaluation],
        ) -> Tuple[Optional[str], Optional[str], Optional[int], Optional[int], bool]:
            hits: Counter[Tuple[str, str]] = Counter()
            volumes: Dict[Tuple[str, str], set[int]] = defaultdict(set)
            display_map: Dict[Tuple[str, str], str] = {}

            for book in lot_books:
                match = self.series_index.route_isbn(book.isbn)
                if match and (not canonical_author_value or match.canonical_author == canonical_author_value):
                    key = (match.canonical_author, match.canonical_series)
                    hits[key] += 1
                    vol_val = getattr(match, "volume", None)
                    if isinstance(vol_val, (int, str)) and str(vol_val).isdigit():
                        volumes[key].add(int(vol_val))
                    if match.display_series:
                        display_map.setdefault(key, match.display_series)
                    if not getattr(match, "volume", None):
                        volume_hint = getattr(book.metadata, "series_index", None) or parse_series_volume_hint(
                            getattr(book.metadata, "title", None)
                        ) or parse_series_volume_hint(getattr(book.metadata, "subtitle", None))
                        if isinstance(volume_hint, (int, str)) and str(volume_hint).isdigit():
                            self.series_index.add_mapping(
                                book.isbn,
                                match.display_author or author_display or (book.metadata.authors[0] if book.metadata.authors else ""),
                                match.display_series
                                or getattr(book.metadata, "series_name", None)
                                or getattr(book.metadata, "series", None)
                                or "",
                                volume=int(volume_hint),
                                title=getattr(book.metadata, "title", None),
                                enriched_ts=now_ts(),
                            )
                            volumes[key].add(int(volume_hint))
                    continue

                meta_series = getattr(book.metadata, "series_name", None) or getattr(book.metadata, "series", None)
                if not meta_series:
                    continue
                canonical_series_value = canonical_series(meta_series)
                if not canonical_series_value:
                    continue
                fallback_name = None
                credited = list(getattr(book.metadata, "credited_authors", ()))
                if credited:
                    fallback_name = credited[0]
                elif book.metadata.authors:
                    fallback_name = book.metadata.authors[0]
                elif author_display:
                    fallback_name = author_display
                author_for_book = canonical_author_value or (
                    alias_canonical_author(fallback_name) if fallback_name else None
                )
                if not author_for_book:
                    continue
                key = (author_for_book, canonical_series_value)
                hits[key] += 1
                display_map.setdefault(key, meta_series)
                volume_hint = getattr(book.metadata, "series_index", None) or parse_series_volume_hint(
                    getattr(book.metadata, "title", None)
                ) or parse_series_volume_hint(getattr(book.metadata, "subtitle", None))
                if isinstance(volume_hint, (int, str)) and str(volume_hint).isdigit():
                    volumes[key].add(int(volume_hint))

            if not hits:
                return None, None, None, None, False

            (best_author, best_series), _ = hits.most_common(1)[0]
            entry_obj = self.series_index.get_entry(best_author, best_series)
            series_display = display_map.get((best_author, best_series))
            entry_dict: Dict[str, Any] = cast(Dict[str, Any], entry_obj) if isinstance(entry_obj, dict) else {}
            if entry_dict:
                series_display = entry_dict.get("display_series") or series_display
            expected_map = entry_dict.get("expected_vols", {})
            if not isinstance(expected_map, dict):
                expected_map = {}

            series_have = len(volumes.get((best_author, best_series), set()))
            if series_have == 0:
                series_have = hits[(best_author, best_series)]

            series_expected = len(expected_map) or None
            is_single = len(hits) == 1
            return series_display, best_series, series_have, series_expected, is_single

        candidates: List[LotCandidate] = []
        for suggestion in suggestions:
            lot_books = [isbn_map.get(isbn) for isbn in suggestion.book_isbns]
            lot_books = [b for b in lot_books if b]
            if len(lot_books) < 2:
                continue

            canonical_author_value, display_author_label, credited_names = self._author_labels_for_books(lot_books)
            author_display = credited_names[0] if credited_names else display_author_label
            (
                series_name,
                canonical_series_value,
                series_have,
                series_expected,
                is_single_series,
            ) = resolve_series(author_display, canonical_author_value, lot_books)

            candidate = LotCandidate(
                name=suggestion.name,
                strategy=suggestion.strategy,
                books=lot_books,
                book_isbns=list(suggestion.book_isbns),
                author=author_display,
                series_name=series_name,
                canonical_author=canonical_author_value,
                canonical_series=canonical_series_value,
                series_have=series_have,
                series_expected=series_expected,
                is_single_series=is_single_series,
                estimated_value=suggestion.estimated_value,
                estimated_price=suggestion.estimated_value,
                probability_score=suggestion.probability_score,
                probability_label=suggestion.probability_label,
                sell_through=suggestion.sell_through,
                justification=list(suggestion.justification),
            )
            candidate.display_author_label = display_author_label
            candidate.canonical_author = canonical_author_value or candidate.canonical_author
            if candidate.series_name:
                label_tail = f" — {display_author_label}" if display_author_label else ""
                candidate.name = f"{candidate.series_name}{label_tail}"
            elif display_author_label:
                candidate.name = f"{display_author_label} Collection"
            candidates.append(candidate)

        candidates.extend(self._build_incomplete_series_candidates(candidates))

        filtered: List[LotCandidate] = []
        by_author: Dict[str, List[LotCandidate]] = defaultdict(list)
        for candidate in candidates:
            if candidate.author:
                by_author[candidate.author].append(candidate)
            else:
                filtered.append(candidate)

        for author, items in by_author.items():
            strong_series = [
                cand
                for cand in items
                if cand.is_single_series
                and cand.series_expected
                and cand.series_expected > 0
                and cand.series_have
                and (cand.series_have / max(1, cand.series_expected)) >= 0.5
            ]
            for cand in items:
                if cand.strategy == "author" and len(strong_series) >= 2:
                    continue
                filtered.append(cand)

        filtered.sort(key=lambda lot: (lot.probability_score, lot.estimated_value), reverse=True)
        self.series_index.save_if_dirty()
        return filtered

    def enrich_lot_with_market(self, lot: LotCandidate) -> None:
        session = requests.Session()
        try:
            books_payload = [self._lot_book_payload(book) for book in lot.books]
            snapshot = market_snapshot_for_lot(
                author=lot.author,
                series=lot.series_name,
                theme=None,
                session=session,
            )
            score = score_lot(
                snapshot=snapshot,
                books=books_payload,
                is_single_series=lot.is_single_series,
                series_have=lot.series_have,
                series_expected=lot.series_expected,
            )
        finally:
            session.close()

        lot.market_json = json.dumps({"lot_snapshot": snapshot, "lot_score": score}, ensure_ascii=False)
        baseline = score.get("price_baseline") or snapshot.get("active_median") or 0.0
        lot.estimated_price = float(baseline or 0.0)
        lot.estimated_value = float(baseline or lot.estimated_value or 0.0)
        lot.probability_score = float(score.get("score", lot.probability_score))
        lot.probability_label = score.get("label", lot.probability_label)
        lot.probability_reasons = "\n".join(score.get("reasons", []))
        lot.sell_through = score.get("sell_through", lot.sell_through)
        lot.ebay_active_count = snapshot.get("active_count") or 0
        lot.ebay_sold_count = snapshot.get("sold_count") or 0

        existing_justification = list(lot.justification)
        for reason in score.get("reasons", []):
            if reason not in existing_justification:
                existing_justification.append(reason)
        lot.justification = existing_justification

        self._record_lot_signal(lot, snapshot, score)

    def save_lots(self, lots: Sequence[LotCandidate]) -> None:
        payloads = []
        for lot in lots:
            justification_lines = list(lot.justification)
            if lot.probability_reasons:
                for line in (line.strip() for line in lot.probability_reasons.splitlines() if line.strip()):
                    if line not in justification_lines:
                        justification_lines.append(line)
            payloads.append(
                {
                    "name": lot.name,
                    "strategy": lot.strategy,
                    "book_isbns": list(lot.book_isbns),
                    "estimated_value": float(lot.estimated_value or 0.0),
                    "probability_label": lot.probability_label,
                    "probability_score": float(lot.probability_score or 0.0),
                    "sell_through": lot.sell_through,
                    "justification": "\n".join(justification_lines),
                }
            )

        if payloads:
            name_tracker: dict[tuple[str, str], int] = {}
            used_names: set[tuple[str, str]] = set()
            for payload in payloads:
                base_key = (payload["name"], payload["strategy"])
                name_tracker[base_key] = name_tracker.get(base_key, 0) + 1
                if name_tracker[base_key] > 1:
                    suffix = name_tracker[base_key]
                    new_name = f"{payload['name']} ({suffix})"
                    while (new_name, payload["strategy"]) in used_names:
                        suffix += 1
                        new_name = f"{payload['name']} ({suffix})"
                    payload["name"] = new_name
                    used_names.add((payload["name"], payload["strategy"]))
                else:
                    used_names.add(base_key)

            self.db.replace_lots(payloads)
        else:
            self.db.replace_lots([])

    def refresh_series_catalog_for_authors(self, authors: List[str]) -> None:
        if not authors:
            return
        # Calling fetch updates the local cache; no return needed
        get_or_fetch_series_for_authors(list(authors))

    def build_series_lots_with_coverage(self) -> List[dict]:
        """
        Build series lots using the series catalog with coverage stats.
        Returns a list of dicts containing label, key, size, estimated_value, probability, books, coverage.
        """
        books = self.list_books()
        # Group by primary author
        by_author: dict[str, list[BookEvaluation]] = {}
        for b in books:
            author = (b.metadata.authors[0].strip() if b.metadata.authors else "")
            if author:
                by_author.setdefault(author, []).append(b)

        lots: list[dict] = []
        for author, items in by_author.items():
            try:
                self.series_index.bootstrap_from_local_catalog(author, display_author=author)
            except Exception:
                pass
            canonical = canonical_author(author)
            if canonical:
                self._series_index_bootstrapped.add(canonical)

            entries_obj = self.series_index.series_entries_for_author(author)
            entries: Dict[str, Any] = entries_obj if isinstance(entries_obj, dict) else {}
            for canonical_series_value, entry in entries.items():
                entry_dict: Dict[str, Any] = cast(Dict[str, Any], entry) if isinstance(entry, dict) else {}
                series_display = entry_dict.get("display_series") or canonical_series_value
                expected_map = entry_dict.get("expected_vols", {}) or {}
                if not isinstance(expected_map, dict):
                    expected_map = {}
                expected_norm: Dict[str, Optional[int]] = {}
                for vol_key, title in expected_map.items():
                    norm = _normalise_title(title)
                    if not norm:
                        continue
                    if isinstance(vol_key, (int, str)) and str(vol_key).isdigit():
                        expected_norm[norm] = int(vol_key)
                    else:
                        expected_norm[norm] = None

                in_series: List[BookEvaluation] = []
                have_numbers: set[int] = set()
                seen_isbns: set[str] = set()
                for book in items:
                    if book.isbn in seen_isbns:
                        continue
                    match = self.series_index.route_isbn(book.isbn)
                    if match and match.canonical_series == canonical_series_value:
                        in_series.append(book)
                        seen_isbns.add(book.isbn)
                        vol = getattr(match, "volume", None)
                        if isinstance(vol, (int, str)) and str(vol).isdigit():
                            have_numbers.add(int(vol))
                        continue
                    meta_series = getattr(book.metadata, "series_name", None) or getattr(book.metadata, "series", None)
                    if meta_series and canonical_series(meta_series) == canonical_series_value:
                        in_series.append(book)
                        seen_isbns.add(book.isbn)
                        vol_hint = getattr(book.metadata, "series_index", None) or parse_series_volume_hint(
                            getattr(book.metadata, "title", None)
                        ) or parse_series_volume_hint(getattr(book.metadata, "subtitle", None))
                        if isinstance(vol_hint, (int, str)) and str(vol_hint).isdigit():
                            have_numbers.add(int(vol_hint))
                        continue
                    title_norm = _normalise_title(getattr(book.metadata, "title", None))
                    if title_norm and title_norm in expected_norm:
                        in_series.append(book)
                        seen_isbns.add(book.isbn)
                        vol_hint = expected_norm.get(title_norm)
                        if isinstance(vol_hint, int) and vol_hint > 0:
                            have_numbers.add(vol_hint)
                        try:
                            self.series_index.add_mapping(
                                book.isbn,
                                author,
                                series_display,
                                volume=vol_hint,
                                title=getattr(book.metadata, "title", None),
                                enriched_ts=now_ts(),
                            )
                            self._series_index_registered_isbns.add(book.isbn)
                        except Exception:
                            pass
                if not in_series:
                    continue

                total_expected = len(expected_map) or len(in_series)
                owned = len(in_series)
                missing = []
                if expected_map:
                    # Safely gather known volumes from entry.known_isbns
                    known_isbns_raw = entry_dict.get("known_isbns")
                    known_isbns = known_isbns_raw if isinstance(known_isbns_raw, dict) else {}
                    known_vols: set[str] = set()
                    if isinstance(known_isbns, dict):
                        for meta in known_isbns.values():
                            if isinstance(meta, dict):
                                vol_val = meta.get("volume")
                                if vol_val is not None:
                                    known_vols.add(str(vol_val))
                    owned = len(known_vols) or owned
                    # Build missing list without unsafe int() casts on unknown keys
                    missing = []
                    for vol_key, title in expected_map.items():
                        vol_key_str = str(vol_key)
                        if vol_key_str not in known_vols:
                            missing.append((vol_key_str, title))
                    total_expected = len(expected_map)

                est_total = sum(float(getattr(b, "estimated_price", 0.0) or 0.0) for b in in_series)
                prob = "High" if owned >= 4 else ("Medium" if owned >= 3 else "Low")
                label = f"Series: {series_display} by {author} ({owned}/{total_expected} owned)"
                cov = {
                    "series": series_display,
                    "author": author,
                    "total": total_expected,
                    "owned": owned,
                    "have_numbers": sorted(have_numbers),
                    "missing": missing,
                    "complete": owned >= total_expected and total_expected > 0,
                }
                lots.append({
                    "label": label,
                    "key": f"series:{author}:{series_display}",
                    "size": owned,
                    "estimated_value": round(est_total, 2),
                    "probability": prob,
                    "books": in_series,
                    "coverage": cov,
                })
        lots.sort(key=lambda L: (L["size"], L["estimated_value"]), reverse=True)
        self.series_index.save_if_dirty()
        return lots

    def set_lot_strategies(self, strategies: set[str]) -> None:
        """Set allowed lot strategies (e.g., {'author','series','genre'})."""
        # Store as simple strings; GUI may include 'genre' which maps to 'value' in lots.py
        self.lot_strategies = set(str(s) for s in strategies)

    def get_books_for_lot(self, lot) -> List[BookEvaluation]:
        """
        Return a list of BookEvaluation objects that belong to this lot.
        Works with lots that expose either `books` (already-evaluated objects)
        or a list of identifiers like `isbns` or `book_isbns`.
        """
        # Already attached objects?
        if hasattr(lot, "books") and getattr(lot, "books"):
            return list(getattr(lot, "books"))

        # Otherwise resolve by ISBNs via our DB / in-memory list
        isbns: List[str] = []
        for attr in ("isbns", "book_isbns", "isbn_list"):
            if hasattr(lot, attr):
                vals = getattr(lot, attr) or []
                isbns = list(vals)
                break

        results: List[BookEvaluation] = []
        if isbns:
            # Use DB fetch to avoid needing GUI knowledge of lot internals
            for isbn in isbns:
                row = self.db.fetch_book(isbn)
                if row:
                    results.append(self._row_to_evaluation(row))
        else:
            # Last resort: recompute membership by group key (author/series)
            key = getattr(lot, "key", None) or getattr(lot, "label", None)
            if key:
                for b in self.list_books():
                    if getattr(b, "group_key", None) == key:
                        results.append(b)

        return results

    def attach_manual_research_to_lot(self, lot, payload: dict):
        payload = payload or {}
        raw_blob = getattr(lot, "market_json", None)
        try:
            current = json.loads(raw_blob) if raw_blob else {}
        except Exception:
            current = {}
        current.update(payload)
        manual = current.get("manual_product_research", {}) or {}
        sold_prices = manual.get("sold_prices", {}) or {}
        median = sold_prices.get("median")
        count_raw = sold_prices.get("count") or 0
        try:
            count = int(count_raw)
        except Exception:
            count = 0

        lot.market_json = json.dumps(current, ensure_ascii=False)
        median_val = None
        if median is not None:
            try:
                median_val = float(median)
            except Exception:
                median_val = None
            if median_val is not None:
                setattr(lot, "estimated_price", median_val)
                lot.estimated_value = median_val

        if median_val is not None:
            note_line = f"Manual Product Research median ${median_val:.2f} (n={count})"
        else:
            note_line = "Manual Product Research data attached"

        existing_reasons = (getattr(lot, "probability_reasons", "") or "").rstrip()
        formatted_note = f"\n - {note_line}"
        lot.probability_reasons = (existing_reasons + formatted_note) if existing_reasons else note_line

        justification = list(getattr(lot, "justification", []) or [])
        if note_line not in justification:
            justification.append(note_line)
        lot.justification = justification

        # Persist manual evidence alongside each member book for traceability
        manual_blob = current.get("manual_product_research", {})
        for isbn in getattr(lot, "book_isbns", []) or []:
            row = self.db.fetch_book(isbn)
            if not row:
                continue
            try:
                book_blob = json.loads(row["market_json"]) if row["market_json"] else {}
            except Exception:
                book_blob = {}
            book_blob["manual_product_research"] = manual_blob
            self.db.update_book_market_json(isbn, book_blob)

        cache_key = self._lot_cache_key(lot)
        self._lot_manual_cache[cache_key] = lot.market_json

    def rescore_lot(self, lot):
        raw_blob = getattr(lot, "market_json", None)
        try:
            blob = json.loads(raw_blob) if raw_blob else {}
        except Exception:
            blob = {}

        manual = blob.get("manual_product_research", {}) or {}
        sold_prices = manual.get("sold_prices", {}) or {}
        median = sold_prices.get("median")
        try:
            count = int(sold_prices.get("count") or 0)
        except Exception:
            count = 0

        snapshot = dict(blob.get("lot_snapshot") or {})
        if median is not None:
            try:
                median_val = float(median)
            except Exception:
                median_val = None
            if median_val is not None:
                snapshot["sold_median"] = median_val
                snapshot.setdefault("active_median", median_val)
        snapshot.setdefault("sold_count", count)
        snapshot.setdefault("active_count", snapshot.get("active_count", 0) or 0)

        books = self.get_books_for_lot(lot)
        books_payload = [self._lot_book_payload(book) for book in books]

        score = score_lot(
            snapshot=snapshot,
            books=books_payload,
            is_single_series=getattr(lot, "is_single_series", False),
            series_have=getattr(lot, "series_have", None),
            series_expected=getattr(lot, "series_expected", None),
        )

        lot.probability_score = float(score.get("score", getattr(lot, "probability_score", 0.0) or 0.0))
        lot.probability_label = score.get("label", getattr(lot, "probability_label", "Unknown"))
        lot.sell_through = score.get("sell_through", getattr(lot, "sell_through", None))

        baseline = score.get("price_baseline")
        if baseline is not None:
            try:
                baseline_val = float(baseline)
            except Exception:
                baseline_val = None
            if baseline_val is not None:
                setattr(lot, "estimated_price", baseline_val)
                lot.estimated_value = baseline_val

        justification = list(getattr(lot, "justification", []) or [])
        for reason in score.get("reasons", []) or []:
            if reason not in justification:
                justification.append(reason)
        lot.justification = justification

        blob["lot_snapshot"] = snapshot
        blob["lot_score"] = score
        lot.market_json = json.dumps(blob, ensure_ascii=False)

        cache_key = self._lot_cache_key(lot)
        self._lot_manual_cache[cache_key] = lot.market_json
        self._update_lot_record(lot)
        return lot

    def recompute_lots(self) -> List[LotSuggestion]:
        """Alias for UI compatibility; recompute lot suggestions and persist them."""
        return self.recalculate_lots()

    def recalculate_lots(self) -> List[LotSuggestion]:
        candidates = self.build_lot_candidates()
        self.save_lots(candidates)
        return [self._candidate_to_suggestion(lot) for lot in candidates]

    # ------------------------------------------------------------------
    # Internal helpers

    def _ensure_series_catalog(self, author: Optional[str]) -> None:
        name = (author or "").strip()
        if not name:
            return
        canonical = canonical_author(name) or name.lower()
        if canonical in self._series_catalog_fetched:
            return
        try:
            get_or_fetch_series_for_authors([name])
        except Exception:
            return
        try:
            self.series_index.bootstrap_from_local_catalog(name, display_author=name)
        except Exception:
            pass
        self._series_catalog_fetched.add(canonical)

    def _candidate_to_suggestion(self, lot: LotCandidate) -> LotSuggestion:
        return LotSuggestion(
            name=lot.name,
            strategy=lot.strategy,
            book_isbns=list(lot.book_isbns),
            estimated_value=round(float(lot.estimated_value or 0.0), 2),
            probability_score=float(lot.probability_score or 0.0),
            probability_label=lot.probability_label,
            sell_through=lot.sell_through,
            justification=list(lot.justification),
            display_author_label=lot.display_author_label,
            canonical_author=lot.canonical_author,
            series_name=lot.series_name,
            books=tuple(lot.books),
        )

    def _author_labels_for_books(self, books: Sequence[BookEvaluation]) -> Tuple[Optional[str], str, List[str]]:
        credited_all: List[str] = []
        canonical_candidates: List[str] = []
        for book in books:
            credited = list(getattr(book.metadata, "credited_authors", ())) or [
                a.strip() for a in book.metadata.authors if a and a.strip()
            ]
            if not credited:
                credited = ["Unknown"]
            for name in credited:
                if name and name not in credited_all:
                    credited_all.append(name)
            canon = getattr(book.metadata, "canonical_author", None)
            if canon:
                canonical_candidates.append(canon)
        canonical_value = None
        if canonical_candidates:
            canonical_value = Counter(canonical_candidates).most_common(1)[0][0]
        elif credited_all:
            canonical_value = alias_canonical_author(credited_all[0]) or credited_all[0]
        display = alias_display_label(credited_all) if credited_all else (canonical_value or "Unknown")
        return canonical_value, display, credited_all

    def _build_incomplete_series_candidates(self, existing: List[LotCandidate]) -> List[LotCandidate]:
        extras: List[LotCandidate] = []
        existing_series = {
            cand.canonical_series
            for cand in existing
            if cand.strategy == "series" and cand.canonical_series
        }

        try:
            coverage_entries = self.build_series_lots_with_coverage()
        except Exception:
            coverage_entries = []

        for entry in coverage_entries:
            entry_dict: Dict[str, Any] = entry if isinstance(entry, dict) else {}
            coverage = entry_dict.get("coverage") or {}
            if not isinstance(coverage, dict):
                coverage = {}
            series_display = (coverage.get("series") or entry_dict.get("label") or "Series")
            author = coverage.get("author")
            total_expected = coverage.get("total") or 0
            owned = coverage.get("owned") or 0
            missing = coverage.get("missing") or []
            if not isinstance(missing, list):
                missing = []
            if owned <= 0:
                continue
            if total_expected and owned >= total_expected:
                continue
            if total_expected == 0 and not missing:
                continue

            canonical_series_value = canonical_series(series_display)
            if canonical_series_value and canonical_series_value in existing_series:
                continue

            books = [b for b in (entry_dict.get("books") or []) if isinstance(b, BookEvaluation)]
            if not books:
                continue

            book_isbns = [b.isbn for b in books if getattr(b, "isbn", None)]
            if not book_isbns:
                continue

            estimated_value = sum(float(getattr(b, "estimated_price", 0.0) or 0.0) for b in books)
            avg_probability = (
                sum(float(getattr(b, "probability_score", 0.0) or 0.0) for b in books) / len(books)
            ) if books else 0.0
            probability_score = min(100.0, avg_probability + 5.0)
            if probability_score >= 70:
                probability_label = "High"
            elif probability_score >= 45:
                probability_label = "Medium"
            else:
                probability_label = "Low"

            canonical_from_books, display_author_label, _credited = self._author_labels_for_books(books)
            canonical_author_value = canonical_from_books or (canonical_author(author) if author else None)

            # Safely compute sell-through values with explicit None/type checks to satisfy static typing
            sell_through_values: list[float] = []
            for b in books:
                mkt = getattr(b, "market", None)
                if not mkt:
                    continue
                rate = getattr(mkt, "sell_through_rate", None)
                if rate is None:
                    continue
                try:
                    sell_through_values.append(float(rate))
                except Exception:
                    # Skip values that cannot be coerced to float
                    continue
            sell_through = (
                sum(sell_through_values) / len(sell_through_values)
                if sell_through_values
                else None
            )

            missing_desc: List[str] = []
            for item in missing:
                try:
                    vol, title = item
                    label = f"#{vol}" if isinstance(vol, (int, float, str)) else str(item)
                    if title:
                        label = f"{label}: {title}"
                    missing_desc.append(str(label))
                except Exception:
                    missing_desc.append(str(item))

            if total_expected and missing_desc:
                coverage_line = f"Missing volumes: {', '.join(missing_desc[:8])}"
                if len(missing_desc) > 8:
                    coverage_line += "…"
            elif total_expected:
                coverage_line = f"Series incomplete: {owned}/{total_expected} owned"
            else:
                coverage_line = "Series incomplete: additional titles expected"

            justification = [
                f"Incomplete series: {owned}/{total_expected or '?'} owned",
                coverage_line,
                "Set aside until remaining titles are sourced.",
            ]

            probability_reasons = "Incomplete series requires additional volumes"

            canonical_author_value = canonical_author(author) if author else None

            candidate = LotCandidate(
                name=f"Incomplete {series_display}",
                strategy="series",
                books=books,
                book_isbns=book_isbns,
                author=author,
                series_name=series_display,
                canonical_author=canonical_author_value,
                canonical_series=canonical_series_value,
                series_have=owned,
                series_expected=total_expected or None,
                is_single_series=True,
                estimated_value=round(estimated_value, 2),
                estimated_price=round(estimated_value, 2),
                probability_score=round(probability_score, 1),
                probability_label=probability_label,
                probability_reasons=probability_reasons,
                sell_through=sell_through,
                justification=justification,
            )
            candidate.display_author_label = display_author_label
            if candidate.series_name:
                label_tail = f" — {display_author_label}" if display_author_label else ""
                candidate.name = f"Incomplete {candidate.series_name}{label_tail}"
            extras.append(candidate)

        return extras

    def _refresh_single_book(
        self,
        isbn: str,
        *,
        requery_market: bool,
        requery_metadata: bool,
        requery_booksrun: bool = False,
    ) -> Optional[BookEvaluation]:
        normalized = normalise_isbn(isbn)
        if not normalized:
            return None
        existing = self.get_book(normalized)
        if not existing:
            return None

        metadata = existing.metadata
        if requery_metadata:
            payload = fetch_metadata(self.metadata_session, normalized, delay=self.metadata_delay)
            if isinstance(payload, dict):
                metadata = self._build_metadata_from_payload(normalized, payload)

        market_stats = existing.market
        if requery_market:
            market_stats = None
            if self.ebay_app_id:
                try:
                    market_stats = fetch_single_market_stat(
                        isbn=normalized,
                        app_id=self.ebay_app_id,
                        global_id=self.ebay_global_id,
                        max_results=self.ebay_entries,
                    )
                except Exception:
                    market_stats = None

        evaluation = build_book_evaluation(
            isbn=existing.isbn,
            original_isbn=existing.original_isbn,
            metadata=metadata,
            market=market_stats,
            condition=existing.condition,
            edition=existing.edition,
        )
        evaluation.quantity = max(1, getattr(existing, "quantity", 1))

        self._register_book_in_series_index(evaluation)

        if requery_booksrun or requery_market or not getattr(existing, "booksrun", None):
            booksrun_offer = self._fetch_booksrun_offer(normalized, condition=existing.condition)
        else:
            booksrun_offer = getattr(existing, "booksrun", None)
        # Store v2_stats for sold comps persistence
        v2_stats_result = None
        if requery_market:
            try:
                v2_stats_result = fetch_market_stats_v2(normalized)
                median_price = v2_stats_result.get("median_price")
                if isinstance(median_price, (int, float)):
                    evaluation.estimated_price = max(10.0, float(median_price))
            except Exception:
                pass

        self._apply_booksrun_to_evaluation(evaluation, booksrun_offer)
        self._persist_book(evaluation, v2_stats=v2_stats_result)
        return evaluation

    def _build_metadata_from_payload(
        self,
        normalized: str,
        payload: Optional[Dict[str, Any]],
    ) -> BookMetadata:
        metadata: Optional[BookMetadata] = None
        if isinstance(payload, dict):
            meta = dict(payload)
            meta = enrich_authorship(meta)
            try:
                meta = attach_series(meta, normalized, session=self.metadata_session)
            except Exception:
                pass
            series_info_obj = meta.get("series")
            series_info: Dict[str, Any] = series_info_obj if isinstance(series_info_obj, dict) else {}
            series_name = meta.get("series_name") or series_info.get("name")
            series_index = meta.get("series_index")
            if series_index is None and series_info:
                idx_val = series_info.get("index")
                if isinstance(idx_val, (int, str)) and str(idx_val).isdigit():
                    try:
                        series_index = int(idx_val)
                    except Exception:
                        series_index = None
                else:
                    series_index = None
            series_id = meta.get("series_id")
            if not series_id:
                ids = series_info.get("id") or {}
                if isinstance(ids, dict):
                    series_id = (
                        ids.get("openlibrary_work")
                        or ids.get("wikidata_qid")
                        or ids.get("work_qid")
                        or ids.get("id")
                    )
                if not series_id:
                    name_val = series_info.get("name")
                    if isinstance(name_val, str):
                        series_id = name_val
            try:
                metadata = BookMetadata(
                    isbn=normalized,
                    title=meta.get("title") or "",
                    subtitle=meta.get("subtitle"),
                    authors=tuple(meta.get("authors") or []),
                    credited_authors=tuple(meta.get("credited_authors") or []),
                    canonical_author=meta.get("canonical_author"),
                    published_year=meta.get("publication_year"),
                    published_raw=meta.get("published_date"),
                    page_count=meta.get("page_count"),
                    categories=tuple(meta.get("categories") or []),
                    average_rating=meta.get("average_rating"),
                    ratings_count=meta.get("ratings_count"),
                    thumbnail=meta.get("cover_url"),
                    description=meta.get("description"),
                    categories_str=meta.get("categories_str"),
                    cover_url=meta.get("cover_url"),
                    series_name=series_name,
                    series_index=series_index,
                    series_id=series_id,
                    source=str(meta.get("source") or "google_books"),
                    raw=meta,
                )
            except Exception:
                metadata = None
        if metadata is None:
            metadata = BookMetadata(isbn=normalized, title="Unknown Title")
        return metadata

    def _register_book_in_series_index(self, evaluation: BookEvaluation) -> None:
        isbn = getattr(evaluation, "isbn", None)
        if not isbn or isbn in self._series_index_registered_isbns:
            return

        metadata = getattr(evaluation, "metadata", None)
        if not metadata:
            return

        authors = getattr(metadata, "authors", ()) or ()
        author_display = authors[0].strip() if authors else None
        series_name = getattr(metadata, "series_name", None) or getattr(metadata, "series", None)
        if not (author_display and series_name):
            return

        self._ensure_series_catalog(author_display)

        canonical_author_value = canonical_author(author_display)
        canonical_series_value = canonical_series(series_name)
        if not (canonical_author_value and canonical_series_value):
            return

        if canonical_author_value not in self._series_index_bootstrapped:
            try:
                self.series_index.bootstrap_from_local_catalog(author_display, display_author=author_display)
            except Exception:
                pass
            self._series_index_bootstrapped.add(canonical_author_value)

        entry_obj = self.series_index.get_entry(canonical_author_value, canonical_series_value)
        entry_dict: Dict[str, Any] = entry_obj if isinstance(entry_obj, dict) else {}
        expected_map = entry_dict.get("expected_vols", {}) if entry_dict else {}

        volume = getattr(metadata, "series_index", None)
        if volume is None:
            volume = parse_series_volume_hint(getattr(metadata, "title", None))
            if volume is None:
                volume = parse_series_volume_hint(getattr(metadata, "subtitle", None))
        if volume is None and expected_map:
            title_norm = _normalise_title(getattr(metadata, "title", None))
            for vol_key, title in expected_map.items():
                if _normalise_title(title) == title_norm:
                    if isinstance(vol_key, (int, str)) and str(vol_key).isdigit():
                        volume = int(vol_key)
                    else:
                        volume = None
                    break

        title = getattr(metadata, "title", None)
        self.series_index.add_mapping(
            isbn,
            author_display,
            series_name,
            volume=volume,
            title=title,
            enriched_ts=now_ts(),
        )
        self._series_index_registered_isbns.add(isbn)

    def _sync_series_index_books(self, books: Sequence[BookEvaluation]) -> None:
        updated = False
        for book in books:
            try:
                before = len(self._series_index_registered_isbns)
                self._register_book_in_series_index(book)
                if len(self._series_index_registered_isbns) != before:
                    updated = True
            except Exception:
                continue
        if updated:
            self.series_index.save_if_dirty()

    def _lot_book_payload(self, book: BookEvaluation) -> Dict:
        raw = getattr(book.metadata, "raw", {}) or {}
        book_format = None
        if isinstance(raw, dict):
            book_format = raw.get("format") or raw.get("binding") or raw.get("type")

        return {
            "isbn": book.isbn,
            "title": getattr(book.metadata, "title", ""),
            "page_count": getattr(book.metadata, "page_count", None),
            "format": book_format,
            "estimated_price": getattr(book, "estimated_price", 0.0),
        }

    def _lot_cache_key(self, lot) -> str:
        strategy = str(getattr(lot, "strategy", "") or "")
        name = str(getattr(lot, "name", "") or getattr(lot, "label", "") or "")
        book_ids_source = None
        for attr in ("book_isbns", "isbns", "isbn_list"):
            if hasattr(lot, attr) and getattr(lot, attr):
                book_ids_source = getattr(lot, attr)
                break
        book_ids = []
        if book_ids_source:
            book_ids = [str(code) for code in book_ids_source if code]
        book_ids.sort()
        key_tail = "|".join(book_ids)
        return f"{strategy}|{name}|{key_tail}"

    def _update_lot_record(self, lot) -> None:
        name = getattr(lot, "name", None)
        strategy = getattr(lot, "strategy", None)
        if not name or not strategy:
            return

        try:
            est_value = float(getattr(lot, "estimated_value", 0.0) or 0.0)
        except Exception:
            est_value = 0.0
        try:
            prob_score = float(getattr(lot, "probability_score", 0.0) or 0.0)
        except Exception:
            prob_score = 0.0

        justification = getattr(lot, "justification", []) or []
        if isinstance(justification, (list, tuple)):
            justification_text = "\n".join(str(item) for item in justification if item)
        else:
            justification_text = str(justification)

        try:
            conn = self.db._get_connection()
        except Exception:
            return

        try:
            with conn:
                conn.execute(
                    """
                    UPDATE lots
                    SET estimated_value = ?,
                        probability_label = ?,
                        probability_score = ?,
                        sell_through = ?,
                        justification = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE name = ? AND strategy = ?
                    """,
                    (
                        est_value,
                        getattr(lot, "probability_label", "Unknown"),
                        prob_score,
                        getattr(lot, "sell_through", None),
                        justification_text,
                        name,
                        strategy,
                    ),
                )
        except Exception:
            pass

    def _record_lot_signal(self, lot: LotCandidate, snapshot: Dict, score: Dict) -> None:
        lot_key_base = lot.series_name or lot.author or lot.name
        lot_key = f"{lot.strategy}:{lot_key_base}" if lot_key_base else lot.name
        entry = {
            "name": lot.name,
            "strategy": lot.strategy,
            "snapshot": snapshot,
            "score": score,
        }

        for book in lot.books:
            row = self.db.fetch_book(book.isbn)
            if not row:
                continue
            try:
                market_blob = json.loads(row["market_json"]) if row["market_json"] else {}
            except Exception:
                market_blob = {}
            ledger = market_blob.setdefault("lot_signals", {})
            ledger[lot_key] = entry
            self.db.update_book_market_json(book.isbn, market_blob)

    def _fetch_booksrun_offer(self, isbn: str, *, condition: Optional[str]) -> Optional[BooksRunOffer]:
        if not self.booksrun_api_key:
            return None
        cond = normalize_booksrun_condition(condition or "good")
        try:
            offer = fetch_booksrun_offer(
                isbn,
                api_key=self.booksrun_api_key,
                affiliate_id=self.booksrun_affiliate_id,
                condition=cond,
                base_url=self.booksrun_base_url,
                timeout=int(self.booksrun_timeout),
                session=self._booksrun_session,
            )
        except BooksRunAPIError:
            return None
        except Exception:
            return None
        if offer and not offer.url:
            offer.url = self._booksrun_fallback_url(isbn)
        return offer

    def _booksrun_fallback_url(self, isbn: str) -> str:
        root = (self.booksrun_base_url or BOOKSRUN_DEFAULT_BASE_URL).rstrip("/")
        return f"{root}/sell-textbooks/{isbn}"

    @staticmethod
    def _booksrun_best_price(offer: BooksRunOffer) -> Optional[float]:
        prices: List[float] = []
        for value in (offer.cash_price, offer.store_credit):
            if isinstance(value, (int, float)):
                prices.append(float(value))
        if not prices:
            return None
        return max(prices)

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            text = value.strip().replace("$", "")
            try:
                return float(text)
            except Exception:
                return None
        return None

    @staticmethod
    def _classify_booksrun_ratio(ratio: float) -> str:
        if ratio >= 0.8:
            return "High"
        if ratio >= 0.5:
            return "Medium"
        return "Low"

    def _apply_booksrun_to_evaluation(
        self,
        evaluation: BookEvaluation,
        offer: Optional[BooksRunOffer],
    ) -> None:
        evaluation.booksrun = offer
        evaluation.booksrun_value_label = None
        evaluation.booksrun_value_ratio = None
        if not offer:
            return
        best_price = self._booksrun_best_price(offer)
        if best_price is None:
            evaluation.booksrun_value_label = "No Offer"
            return
        try:
            est_price = float(evaluation.estimated_price)
        except Exception:
            est_price = 0.0
        if est_price <= 0:
            return
        ratio = best_price / max(est_price, 1e-6)
        evaluation.booksrun_value_ratio = round(ratio, 3)
        evaluation.booksrun_value_label = self._classify_booksrun_ratio(ratio)

    def _booksrun_from_blob(self, isbn: str, blob: Any) -> Optional[BooksRunOffer]:
        if not isinstance(blob, dict) or not blob:
            return None
        cash_price = self._safe_float(blob.get("cash_price") or blob.get("cash"))
        credit_price = self._safe_float(blob.get("store_credit") or blob.get("credit"))
        currency = blob.get("currency")
        condition = blob.get("condition") or "good"
        url = blob.get("url")
        updated = blob.get("updated_at") or blob.get("updated") or blob.get("timestamp")
        raw_payload: Dict[str, Any] = {}
        raw_val = blob.get("raw") if isinstance(blob, dict) else None
        if isinstance(raw_val, dict):
            try:
                for k, v in raw_val.items():
                    key_str = k.decode() if isinstance(k, (bytes, bytearray)) else str(k)
                    raw_payload[key_str] = v
            except Exception:
                raw_payload = {}
        elif isinstance(blob, dict):
            try:
                for k, v in blob.items():
                    key_str = k.decode() if isinstance(k, (bytes, bytearray)) else str(k)
                    raw_payload[key_str] = v
            except Exception:
                raw_payload = {}
        offer = BooksRunOffer(
            isbn=str(blob.get("isbn") or isbn),
            condition=str(condition),
            cash_price=cash_price,
            store_credit=credit_price,
            currency=str(currency) if isinstance(currency, str) else None,
            url=str(url) if isinstance(url, str) else self._booksrun_fallback_url(isbn),
            updated_at=str(updated) if updated is not None else None,
            raw=raw_payload,
        )
        return offer

    def _persist_book(self, evaluation: BookEvaluation, v2_stats: Optional[Dict[str, Any]] = None) -> None:
        metadata_dict = asdict(evaluation.metadata)
        metadata_dict["authors"] = list(metadata_dict.get("authors") or [])
        metadata_dict["credited_authors"] = list(metadata_dict.get("credited_authors") or [])
        if metadata_dict.get("categories") is not None:
            metadata_dict["categories"] = list(metadata_dict.get("categories") or [])
        metadata_dict = enrich_authorship(metadata_dict)
        market_dict = asdict(evaluation.market) if evaluation.market else {}

        # Merge sold comps from v2_stats into market_dict if available
        if v2_stats:
            if "sold_comps_count" in v2_stats:
                market_dict["sold_comps_count"] = v2_stats["sold_comps_count"]
            if "sold_comps_min" in v2_stats:
                market_dict["sold_comps_min"] = v2_stats["sold_comps_min"]
            if "sold_comps_median" in v2_stats:
                market_dict["sold_comps_median"] = v2_stats["sold_comps_median"]
            if "sold_comps_max" in v2_stats:
                market_dict["sold_comps_max"] = v2_stats["sold_comps_max"]
            if "sold_comps_is_estimate" in v2_stats:
                market_dict["sold_comps_is_estimate"] = v2_stats["sold_comps_is_estimate"]
            if "sold_comps_source" in v2_stats:
                market_dict["sold_comps_source"] = v2_stats["sold_comps_source"]
            if "sold_comps_last_sold_date" in v2_stats:
                market_dict["sold_comps_last_sold_date"] = v2_stats["sold_comps_last_sold_date"]

        booksrun_dict = asdict(evaluation.booksrun) if evaluation.booksrun else {}
        if evaluation.booksrun_value_label:
            booksrun_dict["value_label"] = evaluation.booksrun_value_label
        if evaluation.booksrun_value_ratio is not None:
            booksrun_dict["value_ratio"] = evaluation.booksrun_value_ratio
        payload = {
            "isbn": evaluation.isbn,
            "title": evaluation.metadata.title,
            "authors": "; ".join(evaluation.metadata.authors),
            "publication_year": evaluation.metadata.published_year,
            "edition": evaluation.edition,
            "condition": evaluation.condition,
            "estimated_price": evaluation.estimated_price,
            "price_reference": evaluation.market.sold_avg_price if evaluation.market else None,
            "rarity": evaluation.rarity,
            "probability_label": evaluation.probability_label,
            "probability_score": evaluation.probability_score,
            "probability_reasons": "\n".join(evaluation.justification),
            "sell_through": evaluation.market.sell_through_rate if evaluation.market else None,
            "ebay_active_count": evaluation.market.active_count if evaluation.market else None,
            "ebay_sold_count": evaluation.market.sold_count if evaluation.market else None,
            "ebay_currency": evaluation.market.currency if evaluation.market else None,
            "metadata_json": metadata_dict,
            "market_json": market_dict,
            "booksrun_json": booksrun_dict,
            "source_json": {
                "condition": evaluation.condition,
                "edition": evaluation.edition,
                "quantity": max(1, int(getattr(evaluation, "quantity", 1) or 1)),
            },
        }

        # Add sold comps columns if available from v2_stats
        if v2_stats:
            payload["sold_comps_count"] = v2_stats.get("sold_comps_count")
            payload["sold_comps_min"] = v2_stats.get("sold_comps_min")
            payload["sold_comps_median"] = v2_stats.get("sold_comps_median")
            payload["sold_comps_max"] = v2_stats.get("sold_comps_max")
            payload["sold_comps_is_estimate"] = v2_stats.get("sold_comps_is_estimate", True)
            payload["sold_comps_source"] = v2_stats.get("sold_comps_source")

        self.db.upsert_book(payload)

    def _row_to_evaluation(self, row) -> BookEvaluation:
        metadata_json = row["metadata_json"]
        market_json = row["market_json"]
        metadata_payload = json.loads(metadata_json) if metadata_json else {"isbn": row["isbn"]}
        metadata_dict = dict(metadata_payload)
        market_dict = json.loads(market_json) if market_json else None
        booksrun_blob_raw = None
        try:
            if "booksrun_json" in row.keys():
                booksrun_blob_raw = row["booksrun_json"]
        except Exception:
            booksrun_blob_raw = None
        try:
            booksrun_blob = json.loads(booksrun_blob_raw) if booksrun_blob_raw else {}
        except Exception:
            booksrun_blob = {}
        source_raw = None
        try:
            if "source_json" in row.keys():
                source_raw = row["source_json"]
        except Exception:
            source_raw = None
        try:
            source_dict = json.loads(source_raw) if source_raw else {}
        except Exception:
            source_dict = {}
        try:
            quantity = int(source_dict.get("quantity") or 1)
        except Exception:
            quantity = 1
        if quantity <= 0:
            quantity = 1

        metadata_dict.setdefault("isbn", row["isbn"])
        # Normalize tuple fields
        metadata_dict["authors"] = tuple(metadata_dict.get("authors", []) or [])
        metadata_dict["credited_authors"] = tuple(metadata_dict.get("credited_authors", []) or [])
        metadata_dict["categories"] = tuple(metadata_dict.get("categories", []) or [])
        metadata_dict["identifiers"] = tuple(metadata_dict.get("identifiers", []) or [])
        metadata_dict["canonical_author"] = metadata_dict.get("canonical_author")
        # Map extended normalized fields if present in metadata_json
        if "categories_str" in metadata_dict:
            metadata_dict["categories_str"] = metadata_dict.get("categories_str")
        if "cover_url" in metadata_dict:
            metadata_dict["cover_url"] = metadata_dict.get("cover_url")
            # Backfill thumbnail if not present
            metadata_dict.setdefault("thumbnail", metadata_dict["cover_url"])
        if "series_name" in metadata_dict:
            metadata_dict["series_name"] = metadata_dict.get("series_name")
        if "series_index" in metadata_dict:
            try:
                si = metadata_dict.get("series_index")
                metadata_dict["series_index"] = int(si) if isinstance(si, (int, str)) and str(si).isdigit() else None
            except Exception:
                metadata_dict["series_index"] = None
        # Filter out keys not accepted by BookMetadata (e.g., authors_str, publisher, published_date, etc.)
        allowed_keys = {f.name for f in fields(BookMetadata)}
        metadata_dict = {k: v for k, v in metadata_dict.items() if k in allowed_keys}
        metadata = BookMetadata(**metadata_dict)
        try:
            metadata.raw = metadata_payload
        except Exception:
            pass

        market = None
        market_blob = market_dict if isinstance(market_dict, dict) else {}
        if market_blob:
            allowed_market_keys = {f.name for f in fields(EbayMarketStats)}
            payload = {k: market_blob.get(k) for k in allowed_market_keys if k in market_blob}

            def _to_float(v: Any) -> Optional[float]:
                try:
                    return float(v)
                except Exception:
                    return None

            def _to_int(v: Any) -> int:
                try:
                    return int(v)
                except Exception:
                    return 0

            isbn_val = str(payload.get("isbn") or row["isbn"] or "")
            active_count = _to_int(payload.get("active_count"))
            sold_count = _to_int(payload.get("sold_count"))
            unsold_count = None
            if "unsold_count" in payload and payload.get("unsold_count") is not None:
                val: Any = payload.get("unsold_count")
                try:
                    unsold_count = int(val)
                except Exception:
                    unsold_count = None

            market = EbayMarketStats(
                isbn=isbn_val,
                active_count=active_count,
                active_avg_price=_to_float(payload.get("active_avg_price")),
                sold_count=sold_count,
                sold_avg_price=_to_float(payload.get("sold_avg_price")),
                sell_through_rate=_to_float(payload.get("sell_through_rate")),
                currency=(str(payload.get("currency")) if payload.get("currency") else None),
                active_median_price=_to_float(payload.get("active_median_price")),
                sold_median_price=_to_float(payload.get("sold_median_price")),
                unsold_count=unsold_count,
                raw_active=payload.get("raw_active"),
                raw_sold=payload.get("raw_sold"),
                sold_comps_count=_to_int(payload.get("sold_comps_count")) if payload.get("sold_comps_count") is not None else None,
                sold_comps_min=_to_float(payload.get("sold_comps_min")),
                sold_comps_median=_to_float(payload.get("sold_comps_median")),
                sold_comps_max=_to_float(payload.get("sold_comps_max")),
                sold_comps_is_estimate=bool(payload.get("sold_comps_is_estimate", True)),
                sold_comps_source=payload.get("sold_comps_source"),
                sold_comps_last_sold_date=payload.get("sold_comps_last_sold_date"),
            )
        justification_lines = (row["probability_reasons"] or "").split("\n") if row["probability_reasons"] else []
        evaluation = BookEvaluation(
            isbn=row["isbn"],
            original_isbn=row["isbn"],
            metadata=metadata,
            market=market,
            estimated_price=row["estimated_price"] or 0.0,
            condition=row["condition"] or "Good",
            edition=row["edition"],
            rarity=row["rarity"],
            probability_score=row["probability_score"] or 0.0,
            probability_label=row["probability_label"] or "Unknown",
            justification=justification_lines,
            suppress_single=(row["estimated_price"] or 0.0) < 10,
            quantity=quantity,
        )
        booksrun_offer = self._booksrun_from_blob(row["isbn"], booksrun_blob)
        self._apply_booksrun_to_evaluation(evaluation, booksrun_offer)
        try:
            if "created_at" in row.keys():
                setattr(evaluation, "created_at", row["created_at"])
        except Exception:
            pass
        try:
            if "updated_at" in row.keys():
                setattr(evaluation, "updated_at", row["updated_at"])
        except Exception:
            pass
        return evaluation
