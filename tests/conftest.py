"""Shared pytest fixtures for all tests."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import Mock

import pytest

from isbn_lot_optimizer.service import BookService
from shared.database import DatabaseManager


@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    """Create a temporary database file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield db_path


@pytest.fixture
def db_manager(temp_db_path: Path) -> DatabaseManager:
    """Create a DatabaseManager with temporary database."""
    return DatabaseManager(temp_db_path)


@pytest.fixture
def book_service(temp_db_path: Path) -> Generator[BookService, None, None]:
    """Create a BookService with temporary database."""
    service = BookService(temp_db_path)
    yield service
    service.close()


@pytest.fixture
def sample_isbn() -> str:
    """Return a sample ISBN for testing."""
    return "9780143127550"  # "The Sympathizer" by Viet Thanh Nguyen


@pytest.fixture
def sample_isbn_10() -> str:
    """Return a sample ISBN-10 for testing."""
    return "0143127551"


@pytest.fixture
def sample_metadata() -> dict:
    """Return sample metadata for testing."""
    return {
        "title": "Test Book",
        "authors": ["Test Author"],
        "isbn_13": "9780143127550",
        "isbn_10": "0143127551",
        "cover_url": "https://example.com/cover.jpg",
        "publisher": "Test Publisher",
        "published_date": "2020-01-01",
        "page_count": 300,
        "description": "A test book for testing purposes.",
    }


@pytest.fixture
def sample_book_data() -> dict:
    """Return sample book data for database operations."""
    return {
        "isbn": "9780143127550",
        "title": "Test Book",
        "authors": "Test Author",
        "publication_year": 2020,
        "condition": "Good",
        "estimated_price": 10.0,
        "probability_label": "High",
        "probability_score": 0.8,
        "probability_reasons": "Popular author",
        "sell_through": 0.75,
        "ebay_active_count": 50,
        "ebay_sold_count": 200,
        "ebay_currency": "USD",
        "metadata_json": {},
        "market_json": None,
        "booksrun_json": None,
        "bookscouter_json": None,
        "source_json": None,
    }


@pytest.fixture
def mock_requests_session():
    """Return a mock requests session."""
    session = Mock()
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"items": []}
    session.get.return_value = response
    return session


@pytest.fixture
def mock_metadata_response() -> dict:
    """Return a mock Google Books API response."""
    return {
        "kind": "books#volume",
        "id": "test_id",
        "volumeInfo": {
            "title": "Test Book",
            "authors": ["Test Author"],
            "publisher": "Test Publisher",
            "publishedDate": "2020-01-01",
            "description": "A test book",
            "industryIdentifiers": [
                {"type": "ISBN_13", "identifier": "9780143127550"},
                {"type": "ISBN_10", "identifier": "0143127551"},
            ],
            "pageCount": 300,
            "imageLinks": {
                "thumbnail": "https://example.com/thumb.jpg",
                "small": "https://example.com/small.jpg",
                "medium": "https://example.com/medium.jpg",
            },
        },
    }


@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Set up test environment variables and configurations."""
    # Set test environment variable
    monkeypatch.setenv("TESTING", "1")

    # Disable network calls by default (override in specific tests)
    # Tests that need network should explicitly mock or skip
    yield


# Markers for categorizing tests
def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests (fast, no external dependencies)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (may use database, file system)"
    )
    config.addinivalue_line(
        "markers", "slow: Slow tests (API calls, heavy computation)"
    )
    config.addinivalue_line(
        "markers", "network: Tests that require network access"
    )
    config.addinivalue_line(
        "markers", "database: Tests that use database"
    )
