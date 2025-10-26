"""Tests for shared.database module."""
from __future__ import annotations

from pathlib import Path

import pytest

from shared.database import DatabaseManager


@pytest.mark.database
class TestDatabaseManager:
    """Test DatabaseManager functionality."""

    def test_init_creates_database(self, temp_db_path: Path):
        """Test that DatabaseManager creates database file."""
        assert not temp_db_path.exists()

        db = DatabaseManager(temp_db_path)

        assert temp_db_path.exists()
        db.conn.close()

    def test_init_creates_tables(self, db_manager: DatabaseManager):
        """Test that initialization creates required tables."""
        cursor = db_manager.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}

        # Check for essential tables
        assert "books" in tables
        assert "lots" in tables
        assert "scan_history" in tables

    def test_upsert_book_creates_new_record(self, db_manager: DatabaseManager, sample_book_data: dict):
        """Test that upsert_book creates a new book record."""
        db_manager.upsert_book(sample_book_data)

        cursor = db_manager.conn.execute(
            "SELECT isbn, title FROM books WHERE isbn = ?",
            (sample_book_data["isbn"],)
        )
        row = cursor.fetchone()

        assert row is not None
        assert row[0] == sample_book_data["isbn"]
        assert row[1] == sample_book_data["title"]

    def test_upsert_book_updates_existing_record(self, db_manager: DatabaseManager, sample_book_data: dict):
        """Test that upsert_book updates an existing book record."""
        # Insert initial record
        db_manager.upsert_book(sample_book_data)

        # Update with new title
        updated_data = sample_book_data.copy()
        updated_data["title"] = "Updated Title"
        db_manager.upsert_book(updated_data)

        cursor = db_manager.conn.execute(
            "SELECT title FROM books WHERE isbn = ?",
            (sample_book_data["isbn"],)
        )
        row = cursor.fetchone()

        assert row[0] == "Updated Title"

    def test_fetch_book_returns_existing_book(self, db_manager: DatabaseManager, sample_book_data: dict):
        """Test that fetch_book retrieves an existing book."""
        db_manager.upsert_book(sample_book_data)

        result = db_manager.fetch_book(sample_book_data["isbn"])

        assert result is not None
        assert result["isbn"] == sample_book_data["isbn"]
        assert result["title"] == sample_book_data["title"]

    def test_fetch_book_returns_none_for_missing_book(self, db_manager: DatabaseManager):
        """Test that fetch_book returns None for non-existent ISBN."""
        result = db_manager.fetch_book("9999999999999")

        assert result is None

    def test_fetch_all_books_filters_by_accept_status(self, db_manager: DatabaseManager, sample_book_data: dict):
        """Test that fetch_all_books only returns books with status='ACCEPT'."""
        # Insert book with REJECT status
        reject_book = sample_book_data.copy()
        reject_book["isbn"] = "1111111111111"
        reject_book["status"] = "REJECT"
        db_manager.upsert_book(reject_book)

        # Insert book with ACCEPT status
        accept_book = sample_book_data.copy()
        accept_book["isbn"] = "2222222222222"
        accept_book["status"] = "ACCEPT"
        db_manager.upsert_book(accept_book)

        results = db_manager.fetch_all_books()

        # Should only return ACCEPT book
        isbns = {book["isbn"] for book in results}
        assert "2222222222222" in isbns
        assert "1111111111111" not in isbns

    def test_search_books_finds_by_title(self, db_manager: DatabaseManager, sample_book_data: dict):
        """Test that search_books finds books by title."""
        db_manager.upsert_book(sample_book_data)
        # Need to set status to ACCEPT for it to be searchable
        db_manager.conn.execute(
            "UPDATE books SET status = 'ACCEPT' WHERE isbn = ?",
            (sample_book_data["isbn"],)
        )
        db_manager.conn.commit()

        results = db_manager.search_books("Test Book")

        assert len(results) > 0
        assert any(book["isbn"] == sample_book_data["isbn"] for book in results)

    def test_search_books_finds_by_isbn(self, db_manager: DatabaseManager, sample_book_data: dict):
        """Test that search_books finds books by ISBN."""
        db_manager.upsert_book(sample_book_data)
        db_manager.conn.execute(
            "UPDATE books SET status = 'ACCEPT' WHERE isbn = ?",
            (sample_book_data["isbn"],)
        )
        db_manager.conn.commit()

        results = db_manager.search_books(sample_book_data["isbn"])

        assert len(results) > 0
        assert results[0]["isbn"] == sample_book_data["isbn"]

    def test_search_books_filters_by_accept_status(self, db_manager: DatabaseManager, sample_book_data: dict):
        """Test that search_books only returns ACCEPT books."""
        # Insert REJECT book
        reject_book = sample_book_data.copy()
        reject_book["isbn"] = "1111111111111"
        reject_book["status"] = "REJECT"
        reject_book["title"] = "Searchable Title"
        db_manager.upsert_book(reject_book)

        # Insert ACCEPT book
        accept_book = sample_book_data.copy()
        accept_book["isbn"] = "2222222222222"
        accept_book["status"] = "ACCEPT"
        accept_book["title"] = "Searchable Title"
        db_manager.upsert_book(accept_book)

        results = db_manager.search_books("Searchable")

        # Should only return ACCEPT book
        assert len(results) == 1
        assert results[0]["isbn"] == "2222222222222"

    def test_delete_book(self, db_manager: DatabaseManager, sample_book_data: dict):
        """Test that delete_book removes a book from database."""
        db_manager.upsert_book(sample_book_data)

        # Verify book exists
        assert db_manager.fetch_book(sample_book_data["isbn"]) is not None

        # Delete book
        db_manager.conn.execute(
            "DELETE FROM books WHERE isbn = ?",
            (sample_book_data["isbn"],)
        )
        db_manager.conn.commit()

        # Verify book is gone
        assert db_manager.fetch_book(sample_book_data["isbn"]) is None

    def test_multiple_books_operations(self, db_manager: DatabaseManager):
        """Test operations with multiple books."""
        # Insert multiple books
        for i in range(5):
            book_data = {
                "isbn": f"111111111111{i}",
                "title": f"Book {i}",
                "authors": f"Author {i}",
                "status": "ACCEPT",
                "condition": "Good",
                "estimated_price": 10.0 + i,
            }
            db_manager.upsert_book(book_data)

        # Fetch all
        all_books = db_manager.fetch_all_books()

        assert len(all_books) == 5

        # Search for specific book
        results = db_manager.search_books("Book 3")

        assert len(results) == 1
        assert results[0]["title"] == "Book 3"
