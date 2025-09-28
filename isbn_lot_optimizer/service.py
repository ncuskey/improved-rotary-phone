from __future__ import annotations

import json
from collections import Counter, defaultdict
import re
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

from .author_aliases import canonical_author as alias_canonical_author, display_label as alias_display_label
from .database import DatabaseManager
from .metadata import create_http_session, enrich_authorship, fetch_metadata
from .series_index import (
    SeriesIndex,
    canonical_author,
    canonical_series,
    now_ts,
    parse_series_volume_hint,
)
from .models import BookEvaluation, BookMetadata, EbayMarketStats, LotCandidate, LotSuggestion
from .probability import build_book_evaluation
from .lots import build_lots_with_strategies, generate_lot_suggestions
from .series_catalog import get_or_fetch_series_for_authors
from .series_finder import attach_series
from .market import fetch_single_market_stat, fetch_market_stats_v2
from .lot_market import market_snapshot_for_lot
from .lot_scoring import score_lot
from .utils import normalise_isbn, read_isbn_csv


_TITLE_NORMALIZER = re.compile(r"[^a-z0-9]+")

COVER_CHOICES = [
    "Hardcover",
    "Trade Paperback",
    "Mass Market Paperback",
    "Library Binding",
    "Unknown",
]


def _normalise_title(text: Optional[str]) -> str:
    if not text:
        return ""
    value = str(text).lower()
    return _TITLE_NORMALIZER.sub(" ", value).strip()


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

    # ------------------------------------------------------------------
    # Public API

    def close(self) -> None:
        self.metadata_session.close()
        self.series_index.save_if_dirty()

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
        try:
            v2_stats = fetch_market_stats_v2(normalized)
            median_price = v2_stats.get("median_price")
            if isinstance(median_price, (int, float)):
                evaluation.estimated_price = max(10.0, float(median_price))
        except Exception:
            pass

        self._persist_book(evaluation)
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
        try:
            v2_stats = fetch_market_stats_v2(isbn)
            median_price = v2_stats.get("median_price")
            if isinstance(median_price, (int, float)):
                evaluation.estimated_price = max(10.0, float(median_price))
        except Exception:
            pass

        self._persist_book(evaluation)
        if recalc_lots:
            self.recalculate_lots()
        return evaluation

    def list_books(self) -> List[BookEvaluation]:
        rows = self.db.fetch_all_books()
        return [self._row_to_evaluation(row) for row in rows]

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

    def update_book_fields(self, isbn: str, fields: Dict[str, Any]) -> None:
        normalized = normalise_isbn(isbn)
        if not normalized:
            raise ValueError("Invalid ISBN")
        row = self.db.fetch_book(normalized)
        if not row:
            raise ValueError(f"Book {isbn} not found")

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
        self.db.update_book_record(normalized, columns=column_updates, metadata=metadata_payload)

        updated = self.get_book(normalized)
        if updated:
            self._register_book_in_series_index(updated)
        self.series_index.save_if_dirty()
        self.recalculate_lots()

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
                    if match.volume:
                        volumes[key].add(int(match.volume))
                    if match.display_series:
                        display_map.setdefault(key, match.display_series)
                    if not match.volume:
                        volume_hint = getattr(book.metadata, "series_index", None) or parse_series_volume_hint(
                            getattr(book.metadata, "title", None)
                        ) or parse_series_volume_hint(getattr(book.metadata, "subtitle", None))
                        if volume_hint:
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
                if volume_hint:
                    volumes[key].add(int(volume_hint))

            if not hits:
                return None, None, None, None, False

            (best_author, best_series), _ = hits.most_common(1)[0]
            entry = self.series_index.get_entry(best_author, best_series)
            series_display = display_map.get((best_author, best_series))
            if entry:
                series_display = entry.get("display_series") or series_display
                expected_map = entry.get("expected_vols", {})
            else:
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

            entries = self.series_index.series_entries_for_author(author)
            for canonical_series_value, entry in entries.items():
                series_display = entry.get("display_series") or canonical_series_value
                expected_map = entry.get("expected_vols", {}) or {}
                expected_norm: Dict[str, Optional[int]] = {}
                for vol_key, title in expected_map.items():
                    norm = _normalise_title(title)
                    if not norm:
                        continue
                    try:
                        expected_norm[norm] = int(vol_key)
                    except Exception:
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
                        if match.volume:
                            have_numbers.add(int(match.volume))
                        continue
                    meta_series = getattr(book.metadata, "series_name", None) or getattr(book.metadata, "series", None)
                    if meta_series and canonical_series(meta_series) == canonical_series_value:
                        in_series.append(book)
                        seen_isbns.add(book.isbn)
                        vol_hint = getattr(book.metadata, "series_index", None) or parse_series_volume_hint(
                            getattr(book.metadata, "title", None)
                        ) or parse_series_volume_hint(getattr(book.metadata, "subtitle", None))
                        if vol_hint:
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
                    known_vols = {
                        str(meta.get("volume"))
                        for meta in entry.get("known_isbns", {}).values()
                        if meta.get("volume")
                    }
                    owned = len(known_vols) or owned
                    missing = [
                        (int(vol), title)
                        for vol, title in expected_map.items()
                        if vol not in known_vols
                    ]
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
            coverage = entry.get("coverage") or {}
            series_display = coverage.get("series") or entry.get("label") or "Series"
            author = coverage.get("author")
            total_expected = coverage.get("total") or 0
            owned = coverage.get("owned") or 0
            missing = coverage.get("missing") or []
            if owned <= 0:
                continue
            if total_expected and owned >= total_expected:
                continue
            if total_expected == 0 and not missing:
                continue

            canonical_series_value = canonical_series(series_display)
            if canonical_series_value and canonical_series_value in existing_series:
                continue

            books = [b for b in entry.get("books") or [] if isinstance(b, BookEvaluation)]
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

            sell_through_values = [
                float(b.market.sell_through_rate)
                for b in books
                if getattr(b, "market", None) and getattr(b.market, "sell_through_rate", None) is not None
            ]
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

        if requery_market:
            try:
                v2_stats = fetch_market_stats_v2(normalized)
                median_price = v2_stats.get("median_price")
                if isinstance(median_price, (int, float)):
                    evaluation.estimated_price = max(10.0, float(median_price))
            except Exception:
                pass

        self._persist_book(evaluation)
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
            series_info = meta.get("series") if isinstance(meta.get("series"), dict) else {}
            series_name = meta.get("series_name") or series_info.get("name")
            series_index = meta.get("series_index")
            if series_index is None and isinstance(series_info, dict):
                try:
                    series_index = int(series_info.get("index")) if series_info.get("index") is not None else None
                except Exception:
                    series_index = None
            series_id = meta.get("series_id")
            if not series_id and isinstance(series_info, dict):
                ids = series_info.get("id") or {}
                if isinstance(ids, dict):
                    series_id = (
                        ids.get("openlibrary_work")
                        or ids.get("wikidata_qid")
                        or ids.get("work_qid")
                        or ids.get("id")
                    )
                if not series_id and series_info.get("name"):
                    series_id = series_info.get("name")
            try:
                metadata = BookMetadata(
                    isbn=normalized,
                    title=meta.get("title") or "",
                    subtitle=meta.get("subtitle"),
                    authors=tuple(meta.get("authors") or []),
                    credited_authors=tuple(meta.get("credited_authors") or []),
                    canonical_author=meta.get("canonical_author"),
                    series=series_name,
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

        entry = self.series_index.get_entry(canonical_author_value, canonical_series_value)
        expected_map = entry.get("expected_vols", {}) if entry else {}

        volume = getattr(metadata, "series_index", None)
        if volume is None:
            volume = parse_series_volume_hint(getattr(metadata, "title", None))
            if volume is None:
                volume = parse_series_volume_hint(getattr(metadata, "subtitle", None))
        if volume is None and expected_map:
            title_norm = _normalise_title(getattr(metadata, "title", None))
            for vol_key, title in expected_map.items():
                if _normalise_title(title) == title_norm:
                    try:
                        volume = int(vol_key)
                    except Exception:
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

    def _persist_book(self, evaluation: BookEvaluation) -> None:
        metadata_dict = asdict(evaluation.metadata)
        metadata_dict["authors"] = list(metadata_dict.get("authors") or [])
        metadata_dict["credited_authors"] = list(metadata_dict.get("credited_authors") or [])
        if metadata_dict.get("categories") is not None:
            metadata_dict["categories"] = list(metadata_dict.get("categories") or [])
        metadata_dict = enrich_authorship(metadata_dict)
        market_dict = asdict(evaluation.market) if evaluation.market else {}
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
            "source_json": {
                "condition": evaluation.condition,
                "edition": evaluation.edition,
                "quantity": max(1, int(getattr(evaluation, "quantity", 1) or 1)),
            },
        }
        self.db.upsert_book(payload)

    def _row_to_evaluation(self, row) -> BookEvaluation:
        metadata_json = row["metadata_json"]
        market_json = row["market_json"]
        metadata_payload = json.loads(metadata_json) if metadata_json else {"isbn": row["isbn"]}
        metadata_dict = dict(metadata_payload)
        market_dict = json.loads(market_json) if market_json else None
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
