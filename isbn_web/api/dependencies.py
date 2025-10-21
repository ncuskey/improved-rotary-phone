"""Dependency injection for FastAPI routes."""
from __future__ import annotations

import sqlite3
from typing import Generator

from shared.database import DatabaseManager
from isbn_lot_optimizer.service import BookService

from ..config import settings

# Global BookService instance (shared across requests)
_book_service: BookService | None = None


class ThreadSafeDatabaseManager(DatabaseManager):
    """Database manager that creates thread-safe connections for FastAPI."""

    def __init__(self, db_path):
        """Initialize with a single shared connection."""
        self._conn = None  # Initialize before super().__init__ calls _get_connection
        super().__init__(db_path)

    def _get_connection(self) -> sqlite3.Connection:
        """
        Create a thread-safe connection for web requests.

        Override parent method to use check_same_thread=False,
        which is safe in FastAPI's single-threaded request handling.
        """
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False  # Allow use across FastAPI threads
            )
            self._conn.row_factory = sqlite3.Row
        return self._conn


def get_book_service() -> Generator[BookService, None, None]:
    """
    FastAPI dependency that provides a BookService instance.

    The service is initialized once and reused across requests.
    Uses a thread-safe database connection for FastAPI compatibility.
    """
    global _book_service

    if _book_service is None:
        _book_service = BookService(
            database_path=settings.DATABASE_PATH,
            ebay_app_id=settings.EBAY_APP_ID,
            ebay_global_id=settings.EBAY_GLOBAL_ID,
            ebay_delay=settings.EBAY_DELAY,
            ebay_entries=settings.EBAY_ENTRIES,
            metadata_delay=settings.METADATA_DELAY,
            booksrun_api_key=settings.BOOKSRUN_KEY,
            booksrun_affiliate_id=settings.BOOKSRUN_AFFILIATE_ID,
            booksrun_base_url=settings.BOOKSRUN_BASE_URL,
            booksrun_timeout=settings.BOOKSRUN_TIMEOUT,
        )
        # Replace with thread-safe database manager
        _book_service.db = ThreadSafeDatabaseManager(settings.DATABASE_PATH)

    yield _book_service


def cleanup_book_service() -> None:
    """Cleanup function to close database connections on shutdown."""
    global _book_service
    if _book_service is not None:
        # Close database connection if needed
        if hasattr(_book_service.db, 'close'):
            _book_service.db.close()
        _book_service = None
