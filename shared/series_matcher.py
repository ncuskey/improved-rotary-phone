"""
Intelligent matching system to link scanned books to series from bookseries.org data.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from shared.series_database import SeriesDatabaseManager


class SeriesMatcher:
    """Matches books to series using various strategies."""

    def __init__(self, db_path: Path):
        self.series_db = SeriesDatabaseManager(db_path)

    def close(self) -> None:
        """Close database connection."""
        self.series_db.close()

    @staticmethod
    def normalize_for_matching(text: str) -> str:
        """Normalize text for fuzzy matching."""
        if not text:
            return ""

        # Lowercase
        text = text.lower()

        # Remove common subtitle separators and everything after
        text = re.split(r'[:\(\[]', text)[0]

        # Remove articles
        for article in ['the ', 'a ', 'an ']:
            if text.startswith(article):
                text = text[len(article):]
                break

        # Remove punctuation and extra spaces
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    @staticmethod
    def similarity_score(str1: str, str2: str) -> float:
        """Calculate similarity between two strings (0.0 to 1.0)."""
        return SequenceMatcher(None, str1, str2).ratio()

    def match_book(
        self,
        isbn: str,
        book_title: str,
        book_authors: List[str],
        auto_save: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Match a book to potential series using multiple strategies.

        Args:
            isbn: Book's ISBN
            book_title: Book's title
            book_authors: List of book authors
            auto_save: If True, automatically save high-confidence matches to DB

        Returns:
            List of potential series matches with confidence scores
        """
        matches: List[Dict[str, Any]] = []

        if not book_title or not book_authors:
            return matches

        normalized_title = self.normalize_for_matching(book_title)

        # Strategy 1: Author + Title exact/fuzzy matching
        for author in book_authors:
            author_series = self.series_db.get_author_series(author)

            for series_info in author_series:
                series_id = series_info['series_id']
                series_title = series_info['series_title']
                series_books = self.series_db.get_series_books(series_id)

                # Check if book title matches any book in this series
                for series_book in series_books:
                    book_in_series_title = series_book['book_title']
                    normalized_series_book = self.normalize_for_matching(book_in_series_title)

                    similarity = self.similarity_score(normalized_title, normalized_series_book)

                    if similarity >= 0.8:  # High confidence threshold
                        confidence = similarity
                        match_method = f"title_match_{similarity:.2f}"

                        matches.append({
                            'series_id': series_id,
                            'series_title': series_title,
                            'author_name': author,
                            'book_count': series_info['book_count'],
                            'matched_book': book_in_series_title,
                            'confidence': confidence,
                            'match_method': match_method
                        })

                        # Auto-save high confidence matches
                        if auto_save and confidence >= 0.9:
                            self.series_db.match_book_to_series(
                                isbn=isbn,
                                series_id=series_id,
                                confidence=confidence,
                                match_method=match_method
                            )

                        break  # Found best match for this series

        # Strategy 2: Series name in metadata
        # (This would use series_name from metadata_json if available)

        # Deduplicate and sort by confidence
        seen_series = set()
        unique_matches = []

        for match in sorted(matches, key=lambda x: x['confidence'], reverse=True):
            series_id = match['series_id']
            if series_id not in seen_series:
                seen_series.add(series_id)
                unique_matches.append(match)

        return unique_matches

    def bulk_match_books(
        self,
        books: List[Dict[str, Any]],
        auto_save: bool = True,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Match multiple books to series in bulk.

        Args:
            books: List of book dicts with 'isbn', 'title', 'authors' keys
            auto_save: If True, automatically save high-confidence matches
            progress_callback: Optional callback function(current, total)

        Returns:
            Dict mapping ISBN to list of matches
        """
        results = {}
        total = len(books)

        for i, book in enumerate(books, 1):
            isbn = book.get('isbn', '')
            title = book.get('title', '')
            authors = book.get('authors', [])

            if isinstance(authors, str):
                # Parse comma/semicolon separated authors
                authors = [a.strip() for a in re.split(r'[;,]', authors) if a.strip()]

            matches = self.match_book(
                isbn=isbn,
                book_title=title,
                book_authors=authors,
                auto_save=auto_save
            )

            if matches:
                results[isbn] = matches

            if progress_callback:
                progress_callback(i, total)

        return results

    def get_series_info_for_isbn(self, isbn: str) -> Optional[Dict[str, Any]]:
        """
        Get the best series match for an ISBN (if any).

        Args:
            isbn: Book's ISBN

        Returns:
            Series info dict or None
        """
        matches = self.series_db.get_series_for_isbn(isbn)

        if not matches:
            return None

        # Return highest confidence match
        best_match = max(matches, key=lambda x: x['confidence'])

        # Get all books in this series
        series_books = self.series_db.get_series_books(best_match['series_id'])

        return {
            'series_id': best_match['series_id'],
            'series_title': best_match['series_title'],
            'author_name': best_match['author_name'],
            'book_count': best_match['book_count'],
            'confidence': best_match['confidence'],
            'match_method': best_match['match_method'],
            'books': [b['book_title'] for b in series_books]
        }

    def search_series(
        self,
        query: str,
        author: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for series by name.

        Args:
            query: Series name to search for
            author: Optional author name filter

        Returns:
            List of matching series
        """
        return self.series_db.search_series_by_title(query, author)

    def get_series_stats(self) -> Dict[str, int]:
        """Get series database statistics."""
        return self.series_db.get_stats()


def normalize_author_name(name: str) -> str:
    """
    Normalize author names for better matching.

    Examples:
        "Smith, John" -> "John Smith"
        "J.K. Rowling" -> "J K Rowling"
    """
    if not name:
        return ""

    # Handle "Last, First" format
    if ',' in name:
        parts = name.split(',', 1)
        if len(parts) == 2:
            name = f"{parts[1].strip()} {parts[0].strip()}"

    # Remove periods from initials
    name = name.replace('.', ' ')

    # Normalize spaces
    name = re.sub(r'\s+', ' ', name).strip()

    return name
