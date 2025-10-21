"""
Enhanced series-based lot building using bookseries.org data.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from shared.models import BookEvaluation, LotSuggestion
from .series_database import SeriesDatabaseManager


def build_series_lots_enhanced(
    books: Sequence[BookEvaluation],
    db_path: Path,
    min_books: int = 2,
    min_value: float = 10.0
) -> List[LotSuggestion]:
    """
    Build series-based lots using bookseries.org data.

    This uses the actual series data to:
    - Group books by their matched series
    - Show which books in the series you have
    - Show which books are missing
    - Calculate completion percentage

    Args:
        books: List of book evaluations
        db_path: Path to books.db with series data
        min_books: Minimum books needed to create a lot
        min_value: Minimum estimated value for a lot

    Returns:
        List of series-based lot suggestions
    """
    series_db = SeriesDatabaseManager(db_path)
    suggestions: List[LotSuggestion] = []

    try:
        # Group books by their matched series
        series_groups: Dict[int, List[BookEvaluation]] = defaultdict(list)

        for book in books:
            # Get series matches for this ISBN
            series_matches = series_db.get_series_for_isbn(book.isbn)

            if series_matches:
                # Use the highest confidence match
                best_match = series_matches[0]
                series_id = best_match['series_id']
                series_groups[series_id].append(book)

        # Build lots for each series
        for series_id, series_books in series_groups.items():
            if len(series_books) < min_books:
                continue

            # Get series information
            series_info = series_db.get_series_for_isbn(series_books[0].isbn)
            if not series_info:
                continue

            series_title = series_info[0]['series_title']
            author_name = series_info[0]['author_name']
            book_count = series_info[0]['book_count']

            # Get complete list of books in this series
            all_series_books = series_db.get_series_books(series_id)

            # Determine which books we have
            have_titles = {_normalize_title(book.metadata.title) for book in series_books if book.metadata}
            series_book_titles = [b['book_title'] for b in all_series_books]

            have_positions = []
            missing_positions = []

            for pos, book_title in enumerate(series_book_titles, 1):
                normalized = _normalize_title(book_title)
                if normalized in have_titles:
                    have_positions.append(pos)
                else:
                    missing_positions.append(pos)

            # Calculate value
            estimated_value = sum(book.estimated_price for book in series_books)

            if estimated_value < min_value:
                continue

            # Calculate probability
            avg_probability = sum(book.probability_score for book in series_books) / len(series_books)
            probability_score = min(100.0, avg_probability + 10)  # Series bonus

            # Calculate sell-through
            sell_through_values = [
                book.market.sell_through_rate
                for book in series_books
                if book.market and book.market.sell_through_rate
            ]
            sell_through = (
                sum(sell_through_values) / len(sell_through_values)
                if sell_through_values
                else None
            )

            # Build justification with have/missing info
            completion_pct = len(have_positions) / book_count * 100 if book_count > 0 else 0

            justification = [
                f"{series_title} by {author_name}",
                f"Have {len(have_positions)} of {book_count} books ({completion_pct:.0f}% complete)",
            ]

            if have_positions:
                if len(have_positions) <= 10:
                    have_str = ', '.join(f"#{p}" for p in sorted(have_positions))
                    justification.append(f"Have: {have_str}")
                else:
                    justification.append(f"Have: #{min(have_positions)}-#{max(have_positions)} (and more)")

            if missing_positions:
                if len(missing_positions) <= 10:
                    missing_str = ', '.join(f"#{p}" for p in sorted(missing_positions))
                    justification.append(f"Missing: {missing_str}")
                else:
                    justification.append(f"Missing: {len(missing_positions)} books")

            justification.append(f"Estimated value: ${estimated_value:.2f}")

            # Determine strategy and name based on completion
            if completion_pct >= 100:
                strategy = "series_complete"
                completion_label = "Complete"
            elif completion_pct >= 50:
                strategy = "series_partial"
                completion_label = f"{completion_pct:.0f}% Complete"
            else:
                strategy = "series_incomplete"
                completion_label = f"{len(have_positions)}/{book_count} Books"

            # Create informative lot name
            lot_name = f"{series_title} ({completion_label})"

            # Create lot suggestion
            lot = LotSuggestion(
                name=lot_name,
                strategy=strategy,
                book_isbns=[book.isbn for book in series_books],
                estimated_value=round(estimated_value, 2),
                probability_score=round(probability_score, 1),
                probability_label=_classify_probability(probability_score),
                sell_through=sell_through,
                justification=justification,
                series_name=series_title,
                canonical_author=author_name,
                display_author_label=author_name,
                canonical_series=str(series_id),
                books=series_books,
            )

            suggestions.append(lot)

        # Sort by completion percentage (descending), then value
        suggestions.sort(
            key=lambda lot: (
                -_extract_completion_pct(lot.justification),
                -lot.estimated_value
            )
        )

        return suggestions

    finally:
        series_db.close()


def _normalize_title(title: Optional[str]) -> str:
    """Normalize title for comparison."""
    if not title:
        return ""

    import re

    # Lowercase
    title = title.lower()

    # Remove subtitle (after : or -)
    title = re.split(r'[:\-\(]', title)[0]

    # Remove articles
    for article in ['the ', 'a ', 'an ']:
        if title.startswith(article):
            title = title[len(article):]
            break

    # Remove punctuation and normalize spaces
    title = re.sub(r'[^\w\s]', ' ', title)
    title = re.sub(r'\s+', ' ', title).strip()

    return title


def _classify_probability(score: float) -> str:
    """Classify probability score into label."""
    if score >= 70:
        return "High"
    if score >= 45:
        return "Medium"
    return "Low"


def _extract_completion_pct(justification: List[str]) -> float:
    """Extract completion percentage from justification."""
    import re

    for line in justification:
        match = re.search(r'(\d+)% complete', line)
        if match:
            return float(match.group(1))

    return 0.0


def get_series_details_for_lot(
    lot: LotSuggestion,
    db_path: Path
) -> Optional[Dict[str, any]]:
    """
    Get detailed series information for a lot.

    Returns a dict with:
    - series_title
    - author_name
    - total_books
    - have_books (list of titles you have)
    - missing_books (list of titles you're missing)
    - completion_pct

    Args:
        lot: Lot suggestion
        db_path: Path to books.db

    Returns:
        Series details dict or None
    """
    if not lot.book_isbns or lot.strategy != "series_enhanced":
        return None

    series_db = SeriesDatabaseManager(db_path)

    try:
        # Get series info from first book
        first_isbn = lot.book_isbns[0]
        series_matches = series_db.get_series_for_isbn(first_isbn)

        if not series_matches:
            return None

        series_info = series_matches[0]
        series_id = series_info['series_id']
        series_title = series_info['series_title']
        author_name = series_info['author_name']
        book_count = series_info['book_count']

        # Get all books in series
        all_books = series_db.get_series_books(series_id)

        # Get titles from lot books
        have_set = set()
        if hasattr(lot, 'books') and lot.books:
            have_set = {
                _normalize_title(book.metadata.title)
                for book in lot.books
                if book.metadata
            }

        # Determine have vs missing
        have_books = []
        missing_books = []

        for book_data in all_books:
            title = book_data['book_title']
            normalized = _normalize_title(title)

            if normalized in have_set:
                have_books.append(title)
            else:
                missing_books.append(title)

        completion_pct = len(have_books) / book_count * 100 if book_count > 0 else 0

        return {
            'series_title': series_title,
            'author_name': author_name,
            'total_books': book_count,
            'have_books': have_books,
            'missing_books': missing_books,
            'completion_pct': completion_pct,
        }

    finally:
        series_db.close()
