from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from shared.author_aliases import canonical_author as alias_canonical_author, display_label
from shared.models import BookEvaluation, LotSuggestion


def _series_fields(book: BookEvaluation) -> tuple[str | None, int | None, str | None]:
    name = getattr(book.metadata, "series_name", None) or getattr(book.metadata, "series", None)
    name = name.strip() if isinstance(name, str) else None
    idx = getattr(book.metadata, "series_index", None)
    try:
        idx_int = int(idx) if idx is not None else None
    except Exception:
        idx_int = None
    series_id = getattr(book.metadata, "series_id", None)
    raw = getattr(book.metadata, "raw", {}) or {}
    if isinstance(raw, dict):
        series_meta = raw.get("series")
        if isinstance(series_meta, dict):
            ids = series_meta.get("id") or {}
            if isinstance(ids, dict):
                series_id = ids.get("openlibrary_work") or ids.get("wikidata_qid") or ids.get("work_qid") or series_id
            if not name and series_meta.get("name"):
                name = series_meta.get("name")
            if idx_int is None and isinstance(series_meta.get("index"), (int, float)):
                try:
                    idx_int = int(series_meta.get("index"))
                except Exception:
                    idx_int = None
    if not series_id and name:
        series_id = name
    return name, idx_int, series_id

def _series_missing(indices: list[int]) -> list[int]:
    if not indices:
        return []
    n = max(i for i in indices if isinstance(i, int))
    have = set(i for i in indices if isinstance(i, int) and i > 0)
    return [i for i in range(1, n + 1) if i not in have]


def _author_labels(books: Sequence[BookEvaluation]) -> Tuple[str | None, List[str], str]:
    credited_all: List[str] = []
    canonical_candidates: List[str] = []
    for book in books:
        credited = list(getattr(book.metadata, "credited_authors", ())) or [
            a.strip() for a in getattr(book.metadata, "authors", ()) if a and a.strip()
        ]
        for name in credited:
            if name and name not in credited_all:
                credited_all.append(name)
        canon = getattr(book.metadata, "canonical_author", None)
        if canon:
            canonical_candidates.append(canon)
    canonical_value = None
    if canonical_candidates:
        canonical_value = canonical_candidates[0]
    elif credited_all:
        canonical_value = alias_canonical_author(credited_all[0]) or credited_all[0]
    display = display_label(credited_all) if credited_all else (canonical_value or "Unknown")
    return canonical_value, credited_all, display

def _first_genre(book: BookEvaluation) -> str | None:
    cat_str = getattr(book.metadata, "categories_str", None)
    if isinstance(cat_str, str) and cat_str.strip():
        first = cat_str.split(",")[0].strip()
        return first or None
    cats = getattr(book.metadata, "categories", ()) or ()
    if isinstance(cats, (list, tuple)) and cats:
        first = str(cats[0]).strip()
        return first or None
    return None


def generate_lot_suggestions(books: Sequence[BookEvaluation], db_path: Optional[Path] = None) -> List[LotSuggestion]:
    """
    Generate lot suggestions using multiple strategies.

    Args:
        books: List of book evaluations
        db_path: Optional path to books.db for enhanced series matching

    Returns:
        List of lot suggestions
    """
    suggestions: List[LotSuggestion] = []
    using_enhanced_series = False

    # Try enhanced series lots using bookseries.org data (if db_path provided)
    if db_path:
        try:
            from isbn_lot_optimizer.series_lots import build_series_lots_enhanced
            enhanced_series_lots = build_series_lots_enhanced(books, db_path)
            suggestions.extend(enhanced_series_lots)
            using_enhanced_series = True
        except Exception:
            pass  # Fall back to regular series grouping

    # Group by canonical author
    author_groups: defaultdict[str, List[BookEvaluation]] = defaultdict(list)
    author_credits: defaultdict[str, List[str]] = defaultdict(list)
    for book in books:
        canonical_value, credited_list, _display = _author_labels((book,))
        key = canonical_value or (credited_list[0] if credited_list else None)
        if not key:
            continue
        author_groups[key].append(book)
        for name in credited_list:
            if name and name not in author_credits[key]:
                author_credits[key].append(name)

    for canonical_name, author_books in author_groups.items():
        if len(author_books) < 2:
            continue
        display = display_label(author_credits[canonical_name]) if author_credits[canonical_name] else canonical_name
        lot_name = f"{display} Collection"
        suggestion = _compose_lot(
            name=lot_name,
            strategy="author",
            books=author_books,
            justification=[
                f"Multiple titles by {display}",
                f"Combined estimated value ${_sum_price(author_books):.2f}",
                _probability_summary(author_books),
            ],
        )
        if suggestion:
            suggestion.canonical_author = canonical_name
            suggestion.display_author_label = display
            suggestions.append(suggestion)

    # Group by series identifier/name (author-agnostic)
    # Skip if we're using enhanced series lots from bookseries.org
    if not using_enhanced_series:
        series_groups: defaultdict[str, List[BookEvaluation]] = defaultdict(list)
        series_meta: dict[str, dict] = {}
        for book in books:
            series_name, series_index, series_id = _series_fields(book)
            key = series_id or (series_name.lower().strip() if isinstance(series_name, str) else None)
            if not key:
                continue
            series_groups[key].append(book)
            data = series_meta.setdefault(key, {"name": series_name, "indices": []})
            if series_name and not data.get("name"):
                data["name"] = series_name
            if isinstance(series_index, int):
                data.setdefault("indices", []).append(series_index)

        for key, series_books in series_groups.items():
            if len(series_books) < 2:
                continue
            info = series_meta.get(key, {})
            series_name = info.get("name")
            if not series_name:
                first_name, _, _ = _series_fields(series_books[0])
                series_name = first_name or "Series"
            indices = info.get("indices", [])
            missing = _series_missing(indices)
            if missing:
                missing_str = f"Missing volumes: {', '.join('#'+str(i) for i in missing)}"
            else:
                missing_str = "No missing early volumes inferred"
            canonical_name, _credited_names, display = _author_labels(series_books)
            justification = [
                f"Titles from the {series_name} series",
                missing_str,
                f"Bundled pricing lifts total to ${_sum_price(series_books):.2f}",
                _probability_summary(series_books),
            ]
            suggestion = _compose_lot(
                name=f"{series_name} Series",
                strategy="series",
                books=series_books,
                justification=justification,
            )
            if suggestion:
                suggestion.series_name = series_name
                suggestion.canonical_author = canonical_name
                suggestion.display_author_label = display
                suggestion.canonical_series = key
                suggestions.append(suggestion)

    # Fallback: bundle low-value singles by top category
    low_value = [book for book in books if book.suppress_single]
    if len(low_value) >= 2:
        suggestion = _compose_lot(
            name="Value Bundle",
            strategy="value",
            books=low_value,
            justification=[
                "Combines sub-$10 books to exceed listing threshold",
                f"Aggregate estimated value ${_sum_price(low_value):.2f}",
                _probability_summary(low_value),
            ],
        )
        if suggestion:
            suggestions.append(suggestion)

    # Sort lots by probability then value
    suggestions.sort(key=lambda lot: (lot.probability_score, lot.estimated_value), reverse=True)
    return suggestions


def _compose_lot(name: str, strategy: str, books: Sequence[BookEvaluation], justification: Sequence[str]) -> LotSuggestion | None:
    estimated_value = _sum_price(books)
    if estimated_value < 10:
        return None
    avg_probability = sum(book.probability_score for book in books) / len(books)
    # Slight bump for grouping synergy
    probability_score = min(100.0, avg_probability + 8)
    sell_through_values = [book.market.sell_through_rate for book in books if book.market and book.market.sell_through_rate]
    sell_through = sum(sell_through_values) / len(sell_through_values) if sell_through_values else None
    label = _classify(probability_score)
    return LotSuggestion(
        name=name,
        strategy=strategy,
        book_isbns=[book.isbn for book in books],
        estimated_value=round(estimated_value, 2),
        probability_score=round(probability_score, 1),
        probability_label=label,
        sell_through=sell_through,
        justification=list(justification),
    )


def _sum_price(books: Sequence[BookEvaluation]) -> float:
    return sum(book.estimated_price for book in books)


def _classify(score: float) -> str:
    if score >= 70:
        return "High"
    if score >= 45:
        return "Medium"
    return "Low"


def _probability_summary(books: Sequence[BookEvaluation]) -> str:
    labels = {book.probability_label for book in books}
    if len(labels) == 1:
        label = labels.pop()
    else:
        label = ", ".join(sorted(labels))
    return f"Book probability mix: {label}"


def _infer_series_name(book: BookEvaluation) -> str | None:
    if book.metadata.series:
        return book.metadata.series
    if book.metadata.subtitle and len(book.metadata.subtitle) > 3:
        return book.metadata.subtitle
    # Try to infer from title patterns (e.g., "Title: A Novel")
    title = book.metadata.title or ""
    if ":" in title:
        return title.split(":", 1)[0].strip()
    return None


def build_lots_with_strategies(books: Sequence[BookEvaluation], strategies: set[str]) -> List[LotSuggestion]:
    """
    Build lots using only the selected strategies from {'author','series','genre'}.
    Falls back gracefully if metadata is missing.
    """
    selected = set(strategies or ()) & {"author", "series", "genre"}
    if not selected:
        return []

    suggestions: List[LotSuggestion] = []

    # Author grouping
    if "author" in selected:
        author_groups = defaultdict(list)
        for book in books:
            if not book.metadata.authors:
                continue
            author = book.metadata.authors[0].strip()
            if not author:
                continue
            author_groups[author].append(book)
        for author, author_books in author_groups.items():
            if len(author_books) < 2:
                continue
            suggestion = _compose_lot(
                name=f"{author} Collection",
                strategy="author",
                books=author_books,
                justification=[
                    f"Multiple titles by {author}",
                    f"Combined estimated value ${_sum_price(author_books):.2f}",
                    _probability_summary(author_books),
                ],
            )
            if suggestion:
                suggestions.append(suggestion)

    # Series grouping (explicit series_name + series_index)
    if "series" in selected:
        series_groups: defaultdict[str, List[BookEvaluation]] = defaultdict(list)
        series_meta: dict[str, dict] = {}
        for book in books:
            series_name, series_index, series_id = _series_fields(book)
            key = series_id or (series_name.lower().strip() if isinstance(series_name, str) else None)
            if not key:
                continue
            series_groups[key].append(book)
            data = series_meta.setdefault(key, {"name": series_name, "indices": []})
            if series_name and not data.get("name"):
                data["name"] = series_name
            if isinstance(series_index, int):
                data.setdefault("indices", []).append(series_index)
        for key, series_books in series_groups.items():
            if len(series_books) < 2:
                continue
            info = series_meta.get(key, {})
            series_name = info.get("name")
            if not series_name:
                first_name, _, _ = _series_fields(series_books[0])
                series_name = first_name or "Series"
            indices = info.get("indices", [])
            missing = _series_missing(indices)
            missing_str = f"Missing volumes: {', '.join('#'+str(i) for i in missing)}" if missing else None
            justification = [
                f"Titles from the {series_name} series",
                f"Bundled pricing lifts total to ${_sum_price(series_books):.2f}",
                _probability_summary(series_books),
            ]
            if missing_str:
                justification.insert(1, missing_str)
            suggestion = _compose_lot(
                name=f"{series_name} Series Set",
                strategy="series",
                books=series_books,
                justification=justification,
            )
            if suggestion:
                suggestion.series_name = series_name
                suggestion.canonical_series = key
                suggestions.append(suggestion)

    # Genre grouping - prefer categories_str from normalized metadata_json
    if "genre" in selected:
        genre_groups = defaultdict(list)
        for book in books:
            genre = _first_genre(book)
            if genre:
                genre_groups[genre].append(book)
        for genre, genre_books in genre_groups.items():
            if len(genre_books) < 2:
                continue
            suggestion = _compose_lot(
                name=f"{genre} Genre",
                strategy="genre",
                books=genre_books,
                justification=[
                    f"Books in the '{genre}' genre",
                    f"Aggregate estimated value ${_sum_price(genre_books):.2f}",
                    _probability_summary(genre_books),
                ],
            )
            if suggestion:
                suggestions.append(suggestion)

    # Sort lots by probability then value
    suggestions.sort(key=lambda lot: (lot.probability_score, lot.estimated_value), reverse=True)
    return suggestions
