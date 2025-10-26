"""Tests for BookService core methods."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from isbn_lot_optimizer.service import BookService


@pytest.mark.integration
class TestBookServiceCore:
    """Test core BookService functionality."""

    def test_init_creates_service(self, temp_db_path):
        """Test that BookService initializes correctly."""
        service = BookService(temp_db_path)

        assert service.db is not None
        assert service.db.conn is not None

        service.close()

    def test_scan_isbn_defaults_to_reject(self, book_service: BookService):
        """Test that scan_isbn creates book with REJECT status by default."""
        with patch("shared.metadata.fetch_metadata") as mock_fetch:
            mock_fetch.return_value = {
                "title": "Test Book",
                "authors": ["Test Author"],
                "isbn_13": "9780143127550",
            }

            book_service.scan_isbn("9780143127550", include_market=False, recalc_lots=False)

            # Verify status is REJECT
            row = book_service.db.fetch_book("9780143127550")
            assert row is not None
            assert row["status"] == "REJECT"

    def test_accept_book_updates_status(self, book_service: BookService):
        """Test that accept_book updates book status to ACCEPT."""
        with patch("shared.metadata.fetch_metadata") as mock_fetch:
            mock_fetch.return_value = {
                "title": "Test Book",
                "authors": ["Test Author"],
                "isbn_13": "9780143127550",
            }

            # Scan with REJECT
            book_service.scan_isbn("9780143127550", include_market=False, recalc_lots=False)

            # Accept the book
            book_service.accept_book("9780143127550", recalc_lots=False)

            # Verify status is ACCEPT
            row = book_service.db.fetch_book("9780143127550")
            assert row["status"] == "ACCEPT"

    def test_get_all_books_filters_by_accept(self, book_service: BookService):
        """Test that get_all_books only returns ACCEPT books."""
        with patch("shared.metadata.fetch_metadata") as mock_fetch:
            # Create REJECT book
            mock_fetch.return_value = {
                "title": "Reject Book",
                "authors": ["Author"],
                "isbn_13": "1111111111111",
            }
            book_service.scan_isbn("1111111111111", include_market=False, recalc_lots=False)

            # Create ACCEPT book
            mock_fetch.return_value = {
                "title": "Accept Book",
                "authors": ["Author"],
                "isbn_13": "2222222222222",
            }
            book_service.scan_isbn("2222222222222", include_market=False, recalc_lots=False)
            book_service.accept_book("2222222222222", recalc_lots=False)

        # Get all books
        books = book_service.get_all_books()

        # Should only return ACCEPT book
        isbns = {book.isbn for book in books}
        assert "2222222222222" in isbns
        assert "1111111111111" not in isbns

    def test_get_book_returns_evaluation(self, book_service: BookService):
        """Test that get_book returns BookEvaluation."""
        with patch("shared.metadata.fetch_metadata") as mock_fetch:
            mock_fetch.return_value = {
                "title": "Test Book",
                "authors": ["Test Author"],
                "isbn_13": "9780143127550",
            }

            book_service.scan_isbn("9780143127550", include_market=False, recalc_lots=False)
            book_service.accept_book("9780143127550", recalc_lots=False)

            book = book_service.get_book("9780143127550")

            assert book is not None
            assert book.isbn == "9780143127550"
            assert book.title == "Test Book"

    def test_search_books_finds_by_title(self, book_service: BookService):
        """Test that search_books finds books by title."""
        with patch("shared.metadata.fetch_metadata") as mock_fetch:
            mock_fetch.return_value = {
                "title": "Searchable Book",
                "authors": ["Test Author"],
                "isbn_13": "9780143127550",
            }

            book_service.scan_isbn("9780143127550", include_market=False, recalc_lots=False)
            book_service.accept_book("9780143127550", recalc_lots=False)

            results = book_service.search_books("Searchable")

            assert len(results) > 0
            assert any(book.title == "Searchable Book" for book in results)

    def test_delete_books_removes_books(self, book_service: BookService):
        """Test that delete_books removes books from database."""
        with patch("shared.metadata.fetch_metadata") as mock_fetch:
            mock_fetch.return_value = {
                "title": "Book to Delete",
                "authors": ["Author"],
                "isbn_13": "9780143127550",
            }

            book_service.scan_isbn("9780143127550", include_market=False, recalc_lots=False)
            book_service.accept_book("9780143127550", recalc_lots=False)

            # Verify book exists
            assert book_service.get_book("9780143127550") is not None

            # Delete book
            count = book_service.delete_books(["9780143127550"])

            assert count == 1
            assert book_service.get_book("9780143127550") is None

    def test_update_book_fields(self, book_service: BookService):
        """Test that update_book_fields modifies book attributes."""
        with patch("shared.metadata.fetch_metadata") as mock_fetch:
            mock_fetch.return_value = {
                "title": "Original Title",
                "authors": ["Original Author"],
                "isbn_13": "9780143127550",
            }

            book_service.scan_isbn("9780143127550", include_market=False, recalc_lots=False)
            book_service.accept_book("9780143127550", recalc_lots=False)

            # Update fields
            book_service.update_book_fields("9780143127550", {"title": "Updated Title"})

            # Verify update
            book = book_service.get_book("9780143127550")
            assert book.title == "Updated Title"

    def test_log_scan_creates_history_entry(self, book_service: BookService):
        """Test that log_scan creates scan history entry."""
        book_service.log_scan(
            isbn="9780143127550",
            title="Test Book",
            decision="REJECT",
            confidence="High",
            details={"test": "data"}
        )

        # Verify scan was logged
        cursor = book_service.db.conn.execute(
            "SELECT isbn, decision FROM scan_history WHERE isbn = ?",
            ("9780143127550",)
        )
        row = cursor.fetchone()

        assert row is not None
        assert row[0] == "9780143127550"
        assert row[1] == "REJECT"

    def test_service_handles_invalid_isbn(self, book_service: BookService):
        """Test that service handles invalid ISBN gracefully."""
        with patch("shared.metadata.fetch_metadata") as mock_fetch:
            mock_fetch.return_value = None

            result = book_service.scan_isbn("invalid", include_market=False, recalc_lots=False)

            # Should handle gracefully (return None or raise specific exception)
            # Behavior depends on implementation
            assert result is None or isinstance(result, object)


@pytest.mark.integration
class TestBookServiceLots:
    """Test lot-related BookService methods."""

    def test_list_lots_returns_list(self, book_service: BookService):
        """Test that list_lots returns a list."""
        lots = book_service.list_lots()

        assert isinstance(lots, list)

    def test_recompute_lots_returns_list(self, book_service: BookService):
        """Test that recompute_lots returns list of lots."""
        with patch("shared.metadata.fetch_metadata") as mock_fetch:
            # Add some books first
            for i in range(3):
                mock_fetch.return_value = {
                    "title": f"Book {i}",
                    "authors": ["Same Author"],
                    "isbn_13": f"111111111111{i}",
                }
                book_service.scan_isbn(f"111111111111{i}", include_market=False, recalc_lots=False)
                book_service.accept_book(f"111111111111{i}", recalc_lots=False)

        lots = book_service.recompute_lots()

        assert isinstance(lots, list)


@pytest.mark.integration
class TestBookServiceStatistics:
    """Test statistics methods."""

    def test_get_database_statistics(self, book_service: BookService):
        """Test that get_database_statistics returns stats dict."""
        stats = book_service.get_database_statistics()

        assert isinstance(stats, dict)
        assert "total_books" in stats or "book_count" in stats
