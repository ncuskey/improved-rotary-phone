"""
Metadata cache database for fast ISBN lookups.

This database stores lightweight book metadata without expensive eBay
sold comp data. Used for fast lookups to avoid repeated API calls.

Distinct from training_data.db which contains high-quality training
examples with full eBay market data.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CachedBook:
    """
    Lightweight book metadata for fast lookups.

    Attributes:
        isbn: Primary ISBN (ISBN-13 preferred)
        title: Book title
        authors: Comma-separated author names
        publisher: Publisher name
        publication_year: Year published
        binding: Format (Hardcover, Paperback, Mass Market, etc.)
        page_count: Number of pages
        language: Language code (e.g., 'en')
        isbn13: ISBN-13 (if available)
        isbn10: ISBN-10 (if available)
        thumbnail_url: Cover image URL
        description: Short book description
        source: API source (google_books, openlibrary, etc.)
        created_at: When added to cache
        updated_at: Last metadata update
        quality_score: 0-1 score of metadata completeness
    """
    isbn: str
    title: Optional[str] = None
    authors: Optional[str] = None
    publisher: Optional[str] = None
    publication_year: Optional[int] = None
    binding: Optional[str] = None
    page_count: Optional[int] = None
    language: Optional[str] = None
    isbn13: Optional[str] = None
    isbn10: Optional[str] = None
    thumbnail_url: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    quality_score: float = 0.0


class MetadataCacheDB:
    """
    Manage metadata cache database for fast ISBN lookups.

    This database stores lightweight metadata from Google Books and
    OpenLibrary. It does NOT contain eBay sold comp data.

    Purpose:
    - Fast ISBN metadata lookups without API calls
    - Reduce load on rate-limited APIs
    - Support large-scale ISBN discovery

    Database location: ~/.isbn_lot_optimizer/metadata_cache.db
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize metadata cache database.

        Args:
            db_path: Path to database file (default: ~/.isbn_lot_optimizer/metadata_cache.db)
        """
        if db_path is None:
            db_path = Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_database()

    def _init_database(self):
        """Create database tables if they don't exist."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Main metadata cache table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cached_books (
                isbn TEXT PRIMARY KEY,
                title TEXT,
                authors TEXT,
                publisher TEXT,
                publication_year INTEGER,
                binding TEXT,
                page_count INTEGER,
                language TEXT,
                isbn13 TEXT,
                isbn10 TEXT,
                thumbnail_url TEXT,
                description TEXT,
                source TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                quality_score REAL DEFAULT 0.0
            )
        ''')

        # Index on common query fields
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cached_books_isbn13
            ON cached_books(isbn13)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cached_books_isbn10
            ON cached_books(isbn10)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cached_books_source
            ON cached_books(source)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cached_books_quality
            ON cached_books(quality_score)
        ''')

        # Collection stats table (track collection runs)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS collection_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_type TEXT,
                books_collected INTEGER,
                books_failed INTEGER,
                started_at TEXT,
                completed_at TEXT,
                notes TEXT
            )
        ''')

        conn.commit()
        conn.close()

        logger.info(f"Metadata cache database initialized at {self.db_path}")

    def store_book(self, book: CachedBook) -> bool:
        """
        Store book metadata in cache.

        Args:
            book: CachedBook instance

        Returns:
            True if stored successfully, False otherwise
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Calculate quality score
            quality_score = self._calculate_quality_score(book)

            # Insert or replace book
            cursor.execute('''
                INSERT OR REPLACE INTO cached_books (
                    isbn, title, authors, publisher, publication_year,
                    binding, page_count, language, isbn13, isbn10,
                    thumbnail_url, description, source, updated_at, quality_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                book.isbn,
                book.title,
                book.authors,
                book.publisher,
                book.publication_year,
                book.binding,
                book.page_count,
                book.language,
                book.isbn13,
                book.isbn10,
                book.thumbnail_url,
                book.description,
                book.source,
                datetime.now().isoformat(),
                quality_score
            ))

            conn.commit()
            conn.close()

            return True

        except Exception as e:
            logger.error(f"Error storing book {book.isbn}: {e}")
            return False

    def get_book(self, isbn: str) -> Optional[CachedBook]:
        """
        Retrieve book metadata from cache.

        Args:
            isbn: ISBN to lookup (can be ISBN-10 or ISBN-13)

        Returns:
            CachedBook if found, None otherwise
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Try exact match first
            cursor.execute('''
                SELECT * FROM cached_books
                WHERE isbn = ? OR isbn13 = ? OR isbn10 = ?
            ''', (isbn, isbn, isbn))

            row = cursor.fetchone()
            conn.close()

            if row:
                return CachedBook(
                    isbn=row['isbn'],
                    title=row['title'],
                    authors=row['authors'],
                    publisher=row['publisher'],
                    publication_year=row['publication_year'],
                    binding=row['binding'],
                    page_count=row['page_count'],
                    language=row['language'],
                    isbn13=row['isbn13'],
                    isbn10=row['isbn10'],
                    thumbnail_url=row['thumbnail_url'],
                    description=row['description'],
                    source=row['source'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    quality_score=row['quality_score']
                )

            return None

        except Exception as e:
            logger.error(f"Error retrieving book {isbn}: {e}")
            return None

    def has_isbn(self, isbn: str) -> bool:
        """
        Check if ISBN exists in cache.

        Args:
            isbn: ISBN to check

        Returns:
            True if ISBN exists in cache, False otherwise
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute('''
                SELECT 1 FROM cached_books
                WHERE isbn = ? OR isbn13 = ? OR isbn10 = ?
                LIMIT 1
            ''', (isbn, isbn, isbn))

            exists = cursor.fetchone() is not None
            conn.close()

            return exists

        except Exception as e:
            logger.error(f"Error checking ISBN {isbn}: {e}")
            return False

    def get_count(self) -> int:
        """Get total number of books in cache."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) FROM cached_books')
            count = cursor.fetchone()[0]

            conn.close()
            return count

        except Exception as e:
            logger.error(f"Error getting count: {e}")
            return 0

    def get_stats(self) -> Dict:
        """
        Get statistics about metadata cache.

        Returns:
            Dict with cache statistics
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Total books
            cursor.execute('SELECT COUNT(*) FROM cached_books')
            total = cursor.fetchone()[0]

            # By source
            cursor.execute('''
                SELECT source, COUNT(*)
                FROM cached_books
                GROUP BY source
            ''')
            by_source = dict(cursor.fetchall())

            # By binding
            cursor.execute('''
                SELECT binding, COUNT(*)
                FROM cached_books
                WHERE binding IS NOT NULL
                GROUP BY binding
            ''')
            by_binding = dict(cursor.fetchall())

            # Quality distribution
            cursor.execute('''
                SELECT
                    CASE
                        WHEN quality_score >= 0.8 THEN 'high'
                        WHEN quality_score >= 0.5 THEN 'medium'
                        ELSE 'low'
                    END as quality_tier,
                    COUNT(*)
                FROM cached_books
                GROUP BY quality_tier
            ''')
            by_quality = dict(cursor.fetchall())

            conn.close()

            return {
                'total_books': total,
                'by_source': by_source,
                'by_binding': by_binding,
                'by_quality': by_quality
            }

        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}

    def _calculate_quality_score(self, book: CachedBook) -> float:
        """
        Calculate quality score based on metadata completeness.

        Args:
            book: CachedBook instance

        Returns:
            Quality score from 0.0 to 1.0
        """
        score = 0.0

        # Essential fields (0.6 total)
        if book.title:
            score += 0.2
        if book.authors:
            score += 0.2
        if book.publication_year:
            score += 0.2

        # Important fields (0.3 total)
        if book.binding:
            score += 0.1
        if book.publisher:
            score += 0.1
        if book.page_count and book.page_count > 0:
            score += 0.1

        # Nice-to-have fields (0.1 total)
        if book.thumbnail_url:
            score += 0.05
        if book.description:
            score += 0.05

        return min(score, 1.0)

    def record_collection_run(self, run_type: str, books_collected: int,
                            books_failed: int, started_at: str,
                            completed_at: str, notes: str = '') -> int:
        """
        Record a collection run for tracking purposes.

        Args:
            run_type: Type of collection (e.g., 'metadata_only', 'bulk_import')
            books_collected: Number of books successfully collected
            books_failed: Number of books that failed
            started_at: ISO timestamp of start
            completed_at: ISO timestamp of completion
            notes: Optional notes about the run

        Returns:
            Run ID
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO collection_runs (
                    run_type, books_collected, books_failed,
                    started_at, completed_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (run_type, books_collected, books_failed,
                  started_at, completed_at, notes))

            run_id = cursor.lastrowid
            conn.commit()
            conn.close()

            return run_id

        except Exception as e:
            logger.error(f"Error recording collection run: {e}")
            return -1
