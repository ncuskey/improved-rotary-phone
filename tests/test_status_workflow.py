"""Tests for status-based workflow and cover image quality improvements."""
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from isbn_lot_optimizer.service import BookService
from isbn_lot_optimizer.metadata import _fetch_google_books_raw, _normalize_from_gbooks
from shared.database import DatabaseManager


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield db_path


@pytest.fixture
def service(temp_db):
    """Create a BookService with temporary database."""
    svc = BookService(temp_db)
    yield svc
    svc.close()


@pytest.fixture
def db_manager(temp_db):
    """Create a DatabaseManager with temporary database."""
    return DatabaseManager(temp_db)


class TestStatusWorkflow:
    """Test status-based book workflow (REJECT by default, ACCEPT when user accepts)."""

    def test_scan_isbn_defaults_to_reject_status(self, service):
        """Test that scanning an ISBN persists with status='REJECT' by default."""
        # Mock the metadata fetch to avoid network calls
        with patch('isbn_lot_optimizer.metadata.fetch_metadata') as mock_fetch:
            mock_fetch.return_value = {
                'title': 'Test Book',
                'authors': ['Test Author'],
                'isbn_13': '9780143127550',
                'cover_url': 'https://example.com/cover.jpg',
                'publisher': 'Test Publisher',
                'published_date': '2020-01-01',
            }

            # Scan ISBN without specifying status (should default to REJECT)
            book = service.scan_isbn(
                '9780143127550',
                condition='Good',
                include_market=False,
                recalc_lots=False,
            )

            # Verify book was persisted with REJECT status
            conn = service.db.conn
            cursor = conn.execute(
                "SELECT status FROM books WHERE isbn = ?",
                ('9780143127550',)
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == 'REJECT'

    def test_scan_isbn_with_explicit_accept_status(self, service):
        """Test that scanning with status='ACCEPT' persists as accepted."""
        with patch('isbn_lot_optimizer.metadata.fetch_metadata') as mock_fetch:
            mock_fetch.return_value = {
                'title': 'Test Book 2',
                'authors': ['Test Author 2'],
                'isbn_13': '9780143127551',
                'cover_url': 'https://example.com/cover2.jpg',
            }

            # Scan ISBN with explicit ACCEPT status
            book = service.scan_isbn(
                '9780143127551',
                condition='Good',
                include_market=False,
                recalc_lots=False,
                status='ACCEPT',
            )

            # Verify book was persisted with ACCEPT status
            conn = service.db.conn
            cursor = conn.execute(
                "SELECT status FROM books WHERE isbn = ?",
                ('9780143127551',)
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == 'ACCEPT'

    def test_accept_book_updates_status_to_accept(self, service):
        """Test that accept_book updates an existing REJECT book to ACCEPT."""
        with patch('isbn_lot_optimizer.metadata.fetch_metadata') as mock_fetch:
            mock_fetch.return_value = {
                'title': 'Test Book 3',
                'authors': ['Test Author 3'],
                'isbn_13': '9780143127552',
                'cover_url': 'https://example.com/cover3.jpg',
            }

            # First scan with REJECT status
            service.scan_isbn(
                '9780143127552',
                condition='Good',
                include_market=False,
                recalc_lots=False,
                status='REJECT',
            )

            # Verify initial REJECT status
            conn = service.db.conn
            cursor = conn.execute(
                "SELECT status FROM books WHERE isbn = ?",
                ('9780143127552',)
            )
            row = cursor.fetchone()
            assert row[0] == 'REJECT'

            # Now accept the book
            service.accept_book(
                '9780143127552',
                condition='Good',
                recalc_lots=False,
            )

            # Verify status was updated to ACCEPT
            cursor = conn.execute(
                "SELECT status FROM books WHERE isbn = ?",
                ('9780143127552',)
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == 'ACCEPT'

    def test_accept_book_creates_book_if_not_exists(self, service):
        """Test that accept_book creates a new book with ACCEPT status if it doesn't exist."""
        with patch('isbn_lot_optimizer.metadata.fetch_metadata') as mock_fetch:
            mock_fetch.return_value = {
                'title': 'Test Book 4',
                'authors': ['Test Author 4'],
                'isbn_13': '9780143127553',
                'cover_url': 'https://example.com/cover4.jpg',
            }

            # Accept a book that was never scanned before
            service.accept_book(
                '9780143127553',
                condition='Good',
                recalc_lots=False,
            )

            # Verify book was created with ACCEPT status
            conn = service.db.conn
            cursor = conn.execute(
                "SELECT status FROM books WHERE isbn = ?",
                ('9780143127553',)
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == 'ACCEPT'


class TestDatabaseFiltering:
    """Test that database queries filter by status='ACCEPT'."""

    def test_fetch_all_books_filters_by_accept_status(self, service, db_manager):
        """Test that fetch_all_books only returns books with status='ACCEPT'."""
        with patch('isbn_lot_optimizer.metadata.fetch_metadata') as mock_fetch:
            # Create books with different statuses
            mock_fetch.return_value = {
                'title': 'Accepted Book',
                'authors': ['Author A'],
                'isbn_13': '9780143127560',
                'cover_url': 'https://example.com/cover_a.jpg',
            }
            service.scan_isbn('9780143127560', include_market=False, recalc_lots=False, status='ACCEPT')

            mock_fetch.return_value = {
                'title': 'Rejected Book',
                'authors': ['Author B'],
                'isbn_13': '9780143127561',
                'cover_url': 'https://example.com/cover_b.jpg',
            }
            service.scan_isbn('9780143127561', include_market=False, recalc_lots=False, status='REJECT')

            mock_fetch.return_value = {
                'title': 'Another Accepted Book',
                'authors': ['Author C'],
                'isbn_13': '9780143127562',
                'cover_url': 'https://example.com/cover_c.jpg',
            }
            service.scan_isbn('9780143127562', include_market=False, recalc_lots=False, status='ACCEPT')

        # Fetch all books - should only return ACCEPT books
        books = db_manager.fetch_all_books()

        # Should return 2 books (both ACCEPT)
        assert len(books) == 2

        # All returned books should have status='ACCEPT'
        for book in books:
            assert book['status'] == 'ACCEPT'

        # Verify ISBNs are the accepted ones
        isbns = {book['isbn'] for book in books}
        assert isbns == {'9780143127560', '9780143127562'}

    def test_search_books_filters_by_accept_status(self, service, db_manager):
        """Test that search_books only returns books with status='ACCEPT'."""
        with patch('isbn_lot_optimizer.metadata.fetch_metadata') as mock_fetch:
            # Create books with different statuses
            mock_fetch.return_value = {
                'title': 'Dune (ACCEPTED)',
                'authors': ['Frank Herbert'],
                'isbn_13': '9780143127570',
                'cover_url': 'https://example.com/dune.jpg',
            }
            service.scan_isbn('9780143127570', include_market=False, recalc_lots=False, status='ACCEPT')

            mock_fetch.return_value = {
                'title': 'Dune Messiah (REJECTED)',
                'authors': ['Frank Herbert'],
                'isbn_13': '9780143127571',
                'cover_url': 'https://example.com/dune2.jpg',
            }
            service.scan_isbn('9780143127571', include_market=False, recalc_lots=False, status='REJECT')

        # Search for "Dune" - should only return ACCEPT books
        results = db_manager.search_books('Dune')

        # Should return 1 book (only the ACCEPT one)
        assert len(results) == 1
        assert results[0]['status'] == 'ACCEPT'
        assert results[0]['isbn'] == '9780143127570'
        assert 'ACCEPTED' in results[0]['title']

    def test_scan_history_preserves_all_scans(self, service):
        """Test that scan history preserves both REJECT and ACCEPT scans."""
        with patch('isbn_lot_optimizer.metadata.fetch_metadata') as mock_fetch:
            mock_fetch.return_value = {
                'title': 'Scan History Test',
                'authors': ['Test Author'],
                'isbn_13': '9780143127580',
                'cover_url': 'https://example.com/cover.jpg',
            }

            # Scan with REJECT
            service.scan_isbn('9780143127580', include_market=False, recalc_lots=False, status='REJECT')

            # Accept the book
            service.accept_book('9780143127580', recalc_lots=False)

        # Check scan history - should have both REJECT and ACCEPT entries
        conn = service.db.conn
        cursor = conn.execute(
            "SELECT decision FROM scan_history WHERE isbn = ? ORDER BY timestamp",
            ('9780143127580',)
        )
        decisions = [row[0] for row in cursor.fetchall()]

        # Should have at least the REJECT and ACCEPT decisions logged
        assert 'REJECT' in decisions
        assert 'ACCEPT' in decisions


class TestCoverImageQuality:
    """Test cover image quality improvements."""

    def test_google_books_requests_all_image_sizes(self):
        """Test that Google Books API request includes all imageLinks fields."""
        # Check the API request parameters
        with patch('requests.Session.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {'items': []}

            import requests
            session = requests.Session()
            _fetch_google_books_raw('9780143127550', None, session)

            # Verify the API was called with imageLinks (not just thumbnail)
            call_args = mock_get.call_args
            params = call_args[1]['params']

            # The fields parameter should request imageLinks (not just thumbnail)
            assert 'imageLinks' in params['fields']
            assert 'volumeInfo/imageLinks' in params['fields']
            # Should NOT request only thumbnail
            assert 'volumeInfo/imageLinks/thumbnail' not in params['fields']

    def test_prioritizes_highest_resolution_images(self):
        """Test that image URL selection prioritizes highest resolution."""
        # Mock a Google Books response with multiple image sizes
        mock_volume_info = {
            'title': 'Test Book',
            'authors': ['Test Author'],
            'industryIdentifiers': [
                {'type': 'ISBN_13', 'identifier': '9780143127550'}
            ],
            'imageLinks': {
                'smallThumbnail': 'https://example.com/small.jpg',
                'thumbnail': 'https://example.com/thumbnail.jpg',
                'small': 'https://example.com/small_size.jpg',
                'medium': 'https://example.com/medium.jpg',
                'large': 'https://example.com/large.jpg',
                'extraLarge': 'https://example.com/extralarge.jpg',
            }
        }

        result = _normalize_from_gbooks(mock_volume_info)

        # Should prioritize extraLarge over all others
        assert result['cover_url'] == 'https://example.com/extralarge.jpg'

    def test_falls_back_to_lower_resolution_if_high_not_available(self):
        """Test that image selection falls back gracefully when high-res not available."""
        # Mock response with only medium and thumbnail
        mock_volume_info = {
            'title': 'Test Book',
            'authors': ['Test Author'],
            'industryIdentifiers': [
                {'type': 'ISBN_13', 'identifier': '9780143127550'}
            ],
            'imageLinks': {
                'thumbnail': 'https://example.com/thumbnail.jpg',
                'medium': 'https://example.com/medium.jpg',
            }
        }

        result = _normalize_from_gbooks(mock_volume_info)

        # Should select medium (higher than thumbnail)
        assert result['cover_url'] == 'https://example.com/medium.jpg'

    def test_zoom_parameter_enhanced_to_zero(self):
        """Test that Google Books URLs get zoom=0 parameter for highest quality."""
        mock_volume_info = {
            'title': 'Test Book',
            'authors': ['Test Author'],
            'industryIdentifiers': [
                {'type': 'ISBN_13', 'identifier': '9780143127550'}
            ],
            'imageLinks': {
                'thumbnail': 'https://books.google.com/cover.jpg?id=abc',
            }
        }

        result = _normalize_from_gbooks(mock_volume_info)

        # Should add zoom=0 parameter
        assert 'zoom=0' in result['cover_url']

    def test_upgrades_zoom_5_to_zoom_0(self):
        """Test that existing zoom=5 parameters are upgraded to zoom=0."""
        mock_volume_info = {
            'title': 'Test Book',
            'authors': ['Test Author'],
            'industryIdentifiers': [
                {'type': 'ISBN_13', 'identifier': '9780143127550'}
            ],
            'imageLinks': {
                'thumbnail': 'https://books.google.com/cover.jpg?id=abc&zoom=5',
            }
        }

        result = _normalize_from_gbooks(mock_volume_info)

        # Should replace zoom=5 with zoom=0
        assert 'zoom=0' in result['cover_url']
        assert 'zoom=5' not in result['cover_url']


class TestIntegration:
    """Integration tests for the complete workflow."""

    def test_complete_scan_to_accept_workflow(self, service, db_manager):
        """Test the complete workflow: scan (REJECT) -> accept (ACCEPT) -> verify filtering."""
        with patch('isbn_lot_optimizer.metadata.fetch_metadata') as mock_fetch:
            mock_fetch.return_value = {
                'title': 'Integration Test Book',
                'authors': ['Integration Author'],
                'isbn_13': '9780143127590',
                'cover_url': 'https://example.com/integration.jpg',
            }

            # Step 1: Scan book (should default to REJECT)
            service.scan_isbn(
                '9780143127590',
                condition='Good',
                include_market=False,
                recalc_lots=False,
            )

            # Step 2: Verify book is NOT in inventory (fetch_all_books filters REJECT)
            books = db_manager.fetch_all_books()
            assert not any(b['isbn'] == '9780143127590' for b in books)

            # Step 3: Accept the book
            service.accept_book('9780143127590', recalc_lots=False)

            # Step 4: Verify book IS now in inventory
            books = db_manager.fetch_all_books()
            assert any(b['isbn'] == '9780143127590' and b['status'] == 'ACCEPT' for b in books)

            # Step 5: Verify searchable
            search_results = db_manager.search_books('Integration')
            assert len(search_results) == 1
            assert search_results[0]['isbn'] == '9780143127590'
            assert search_results[0]['status'] == 'ACCEPT'
