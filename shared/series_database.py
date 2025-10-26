"""
Database manager for book series and author data integration.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class SeriesDatabaseManager:
    """Manages book series and author data storage and matching."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._local = threading.local()
        self._initialize()

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a thread-local database connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def close(self) -> None:
        """Close the database connection for the current thread."""
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            finally:
                self._local.conn = None

    def _initialize(self) -> None:
        """Create series and authors tables if they don't exist."""
        with self._get_connection() as conn:
            conn.executescript("""
                -- Authors table
                CREATE TABLE IF NOT EXISTS authors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    name_normalized TEXT,
                    bio TEXT,
                    source_url TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                -- Series table
                CREATE TABLE IF NOT EXISTS series (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    author_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    title_normalized TEXT,
                    book_count INTEGER DEFAULT 0,
                    source_url TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE,
                    UNIQUE(author_id, title)
                );

                -- Series books table (links series to book titles)
                CREATE TABLE IF NOT EXISTS series_books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    series_id INTEGER NOT NULL,
                    book_title TEXT NOT NULL,
                    book_title_normalized TEXT,
                    series_position INTEGER,
                    source_link TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (series_id) REFERENCES series(id) ON DELETE CASCADE
                );

                -- Book series matches (links ISBNs to detected series)
                CREATE TABLE IF NOT EXISTS book_series_matches (
                    isbn TEXT NOT NULL,
                    series_id INTEGER NOT NULL,
                    confidence REAL DEFAULT 0.0,
                    match_method TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (isbn, series_id),
                    FOREIGN KEY (series_id) REFERENCES series(id) ON DELETE CASCADE
                );

                -- Indexes for efficient queries
                CREATE INDEX IF NOT EXISTS idx_authors_name_normalized
                    ON authors(name_normalized);

                CREATE INDEX IF NOT EXISTS idx_series_author_id
                    ON series(author_id);

                CREATE INDEX IF NOT EXISTS idx_series_title_normalized
                    ON series(title_normalized);

                CREATE INDEX IF NOT EXISTS idx_series_books_series_id
                    ON series_books(series_id);

                CREATE INDEX IF NOT EXISTS idx_series_books_title_normalized
                    ON series_books(book_title_normalized);

                CREATE INDEX IF NOT EXISTS idx_book_series_matches_isbn
                    ON book_series_matches(isbn);

                CREATE INDEX IF NOT EXISTS idx_book_series_matches_series_id
                    ON book_series_matches(series_id);
            """)

    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Normalize text for fuzzy matching.
        Lowercase, remove articles, punctuation, extra spaces.
        """
        if not text:
            return ""

        # Lowercase
        text = text.lower()

        # Remove common articles at start
        for article in ['the ', 'a ', 'an ']:
            if text.startswith(article):
                text = text[len(article):]
                break

        # Remove punctuation and normalize spaces
        import re
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    def upsert_author(self, name: str, bio: str = "", source_url: str = "") -> int:
        """
        Insert or update an author and return their ID.

        Args:
            name: Author's name
            bio: Author biography
            source_url: URL to author's page

        Returns:
            Author ID
        """
        normalized = self.normalize_text(name)

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO authors (name, name_normalized, bio, source_url, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    bio = COALESCE(excluded.bio, bio),
                    source_url = COALESCE(excluded.source_url, source_url),
                    updated_at = CURRENT_TIMESTAMP
            """, (name, normalized, bio, source_url))

            cursor = conn.execute(
                "SELECT id FROM authors WHERE name = ?", (name,)
            )
            row = cursor.fetchone()
            return row['id'] if row else 0

    def upsert_series(
        self,
        author_id: int,
        title: str,
        book_count: int = 0,
        source_url: str = ""
    ) -> int:
        """
        Insert or update a series and return its ID.

        Args:
            author_id: Author's database ID
            title: Series title
            book_count: Number of books in series
            source_url: URL to series page

        Returns:
            Series ID
        """
        normalized = self.normalize_text(title)

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO series (author_id, title, title_normalized, book_count, source_url, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(author_id, title) DO UPDATE SET
                    book_count = excluded.book_count,
                    source_url = COALESCE(excluded.source_url, source_url),
                    updated_at = CURRENT_TIMESTAMP
            """, (author_id, title, normalized, book_count, source_url))

            cursor = conn.execute(
                "SELECT id FROM series WHERE author_id = ? AND title = ?",
                (author_id, title)
            )
            row = cursor.fetchone()
            return row['id'] if row else 0

    def add_series_book(
        self,
        series_id: int,
        book_title: str,
        series_position: Optional[int] = None,
        source_link: str = ""
    ) -> None:
        """
        Add a book to a series.

        Args:
            series_id: Series database ID
            book_title: Title of the book
            series_position: Position in series (if known)
            source_link: URL to book page
        """
        normalized = self.normalize_text(book_title)

        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO series_books
                    (series_id, book_title, book_title_normalized, series_position, source_link)
                VALUES (?, ?, ?, ?, ?)
            """, (series_id, book_title, normalized, series_position, source_link))

    def match_book_to_series(
        self,
        isbn: str,
        series_id: int,
        confidence: float,
        match_method: str
    ) -> None:
        """
        Record a match between a book (ISBN) and a series.

        Args:
            isbn: Book's ISBN
            series_id: Series database ID
            confidence: Match confidence (0.0 to 1.0)
            match_method: Description of how match was found
        """
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO book_series_matches
                    (isbn, series_id, confidence, match_method, created_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (isbn, series_id, confidence, match_method))

    def get_series_for_isbn(self, isbn: str) -> List[Dict[str, Any]]:
        """
        Get all series matches for a given ISBN.

        Args:
            isbn: Book's ISBN

        Returns:
            List of series info dicts with author details
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT
                    s.id as series_id,
                    s.title as series_title,
                    s.book_count,
                    a.id as author_id,
                    a.name as author_name,
                    m.confidence,
                    m.match_method
                FROM book_series_matches m
                JOIN series s ON m.series_id = s.id
                JOIN authors a ON s.author_id = a.id
                WHERE m.isbn = ?
                ORDER BY m.confidence DESC
            """, (isbn,))

            return [dict(row) for row in cursor.fetchall()]

    def get_series_books(self, series_id: int) -> List[Dict[str, Any]]:
        """
        Get all books in a series.

        Args:
            series_id: Series database ID

        Returns:
            List of book info dicts
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT
                    book_title,
                    series_position,
                    source_link
                FROM series_books
                WHERE series_id = ?
                ORDER BY COALESCE(series_position, 999999), book_title
            """, (series_id,))

            return [dict(row) for row in cursor.fetchall()]

    def search_series_by_title(
        self,
        title_query: str,
        author_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for series by title (fuzzy).

        Args:
            title_query: Title to search for
            author_name: Optional author name filter

        Returns:
            List of matching series with author info
        """
        normalized_query = f"%{self.normalize_text(title_query)}%"

        with self._get_connection() as conn:
            if author_name:
                normalized_author = f"%{self.normalize_text(author_name)}%"
                cursor = conn.execute("""
                    SELECT
                        s.id as series_id,
                        s.title as series_title,
                        s.book_count,
                        a.id as author_id,
                        a.name as author_name
                    FROM series s
                    JOIN authors a ON s.author_id = a.id
                    WHERE s.title_normalized LIKE ?
                      AND a.name_normalized LIKE ?
                    ORDER BY a.name, s.title
                """, (normalized_query, normalized_author))
            else:
                cursor = conn.execute("""
                    SELECT
                        s.id as series_id,
                        s.title as series_title,
                        s.book_count,
                        a.id as author_id,
                        a.name as author_name
                    FROM series s
                    JOIN authors a ON s.author_id = a.id
                    WHERE s.title_normalized LIKE ?
                    ORDER BY a.name, s.title
                """, (normalized_query,))

            return [dict(row) for row in cursor.fetchall()]

    def get_author_series(self, author_name: str) -> List[Dict[str, Any]]:
        """
        Get all series for an author.

        Args:
            author_name: Author's name

        Returns:
            List of series dicts
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT
                    s.id as series_id,
                    s.title as series_title,
                    s.book_count
                FROM series s
                JOIN authors a ON s.author_id = a.id
                WHERE a.name = ?
                ORDER BY s.title
            """, (author_name,))

            return [dict(row) for row in cursor.fetchall()]

    def get_author_series_by_normalized_name(self, author_name_normalized: str) -> List[Dict[str, Any]]:
        """
        Get all series for an author using normalized name matching.

        This allows matching authors even when the name format differs
        (e.g., "Martin,George R.R." vs "George R R Martin").

        Args:
            author_name_normalized: Normalized author name (lowercase, no punctuation)

        Returns:
            List of series dicts
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT
                    s.id as series_id,
                    s.title as series_title,
                    s.book_count,
                    a.name as author_name
                FROM series s
                JOIN authors a ON s.author_id = a.id
                WHERE a.name_normalized = ?
                ORDER BY s.title
            """, (author_name_normalized,))

            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> Dict[str, int]:
        """Get database statistics."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT
                    (SELECT COUNT(*) FROM authors) as author_count,
                    (SELECT COUNT(*) FROM series) as series_count,
                    (SELECT COUNT(*) FROM series_books) as series_books_count,
                    (SELECT COUNT(*) FROM book_series_matches) as matches_count
            """)
            row = cursor.fetchone()
            return dict(row) if row else {}

    def clear_all(self) -> None:
        """Clear all series data (use with caution)."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM book_series_matches")
            conn.execute("DELETE FROM series_books")
            conn.execute("DELETE FROM series")
            conn.execute("DELETE FROM authors")
