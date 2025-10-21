"""
Integration helpers to add series matching to scanned books.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.series_matcher import SeriesMatcher, normalize_author_name
from shared.models import BookEvaluation


def match_and_attach_series(
    evaluation: BookEvaluation,
    db_path: Path,
    auto_save: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Match a book evaluation to series and optionally save the match.

    Args:
        evaluation: BookEvaluation object
        db_path: Path to books.db
        auto_save: If True, save high-confidence matches to DB

    Returns:
        Best series match info or None
    """
    if not evaluation or not evaluation.metadata:
        return None

    title = evaluation.metadata.title
    authors = list(evaluation.metadata.authors) if evaluation.metadata.authors else []

    if not title or not authors:
        return None

    matcher = SeriesMatcher(db_path)

    try:
        # Normalize author names
        normalized_authors = [normalize_author_name(a) for a in authors if a]

        # Match the book
        matches = matcher.match_book(
            isbn=evaluation.isbn,
            book_title=title,
            book_authors=normalized_authors,
            auto_save=auto_save
        )

        if matches:
            # Return best match (highest confidence)
            best_match = matches[0]
            return best_match

        return None

    finally:
        matcher.close()


def get_series_info_for_isbn(isbn: str, db_path: Path) -> Optional[Dict[str, Any]]:
    """
    Get series information for an ISBN if it has been matched.

    Args:
        isbn: Book's ISBN
        db_path: Path to books.db

    Returns:
        Series info dict or None
    """
    matcher = SeriesMatcher(db_path)

    try:
        return matcher.get_series_info_for_isbn(isbn)
    finally:
        matcher.close()


def enrich_evaluation_with_series(
    evaluation: BookEvaluation,
    db_path: Path
) -> BookEvaluation:
    """
    Enrich a BookEvaluation with series information from the database.

    This checks if the ISBN has already been matched to a series and
    adds that information to the metadata.

    Args:
        evaluation: BookEvaluation to enrich
        db_path: Path to books.db

    Returns:
        Modified evaluation (same object, modified in place)
    """
    series_info = get_series_info_for_isbn(evaluation.isbn, db_path)

    if series_info and evaluation.metadata:
        # Add series info to metadata if not already present
        if not evaluation.metadata.series_name:
            evaluation.metadata.series_name = series_info['series_title']

        # Store full series info in raw field for access in templates
        if not evaluation.metadata.raw.get('bookseries_org'):
            evaluation.metadata.raw['bookseries_org'] = series_info

    return evaluation
