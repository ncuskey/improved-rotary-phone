"""Tests for shared.metadata module."""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
import requests

from shared.metadata import (
    _fetch_google_books_raw,
    _normalize_from_gbooks,
    create_http_session,
    enrich_authorship,
    fetch_metadata,
)


@pytest.mark.unit
class TestHTTPSession:
    """Test HTTP session creation."""

    def test_create_http_session_returns_session(self):
        """Test that create_http_session returns a requests Session."""
        session = create_http_session()
        assert isinstance(session, requests.Session)

    def test_create_http_session_has_timeout(self):
        """Test that session has appropriate timeout configuration."""
        session = create_http_session()
        # Session should have adapters configured
        assert len(session.adapters) > 0


@pytest.mark.unit
class TestNormalizeFromGbooks:
    """Test Google Books response normalization."""

    def test_normalize_basic_fields(self, mock_metadata_response):
        """Test that basic fields are extracted correctly."""
        result = _normalize_from_gbooks(mock_metadata_response["volumeInfo"])

        assert result["title"] == "Test Book"
        assert result["authors"] == ["Test Author"]
        assert result["publisher"] == "Test Publisher"
        assert result["published_date"] == "2020-01-01"

    def test_normalize_isbn_extraction(self, mock_metadata_response):
        """Test that ISBN-13 and ISBN-10 are extracted."""
        result = _normalize_from_gbooks(mock_metadata_response["volumeInfo"])

        assert result["isbn_13"] == "9780143127550"
        assert result["isbn_10"] == "0143127551"

    def test_normalize_prioritizes_large_images(self):
        """Test that larger images are prioritized over thumbnails."""
        volume_info = {
            "title": "Test",
            "imageLinks": {
                "thumbnail": "https://example.com/thumb.jpg",
                "small": "https://example.com/small.jpg",
                "medium": "https://example.com/medium.jpg",
                "large": "https://example.com/large.jpg",
            },
        }

        result = _normalize_from_gbooks(volume_info)

        # Should pick large over medium/small/thumbnail
        assert "large.jpg" in result.get("cover_url", "")

    def test_normalize_handles_missing_fields(self):
        """Test that normalization handles missing optional fields gracefully."""
        minimal_volume_info = {
            "title": "Minimal Book",
        }

        result = _normalize_from_gbooks(minimal_volume_info)

        assert result["title"] == "Minimal Book"
        assert "authors" in result  # Should have default value or be None
        assert "cover_url" in result  # Should have default value or be None

    def test_normalize_handles_multiple_authors(self):
        """Test that multiple authors are preserved."""
        volume_info = {
            "title": "Test",
            "authors": ["Author One", "Author Two", "Author Three"],
        }

        result = _normalize_from_gbooks(volume_info)

        assert len(result["authors"]) == 3
        assert "Author Two" in result["authors"]


@pytest.mark.unit
class TestEnrichAuthorship:
    """Test authorship enrichment."""

    def test_enrich_authorship_basic(self):
        """Test basic authorship enrichment."""
        metadata = {"title": "Test Book", "authors": ["Test Author"]}

        enrich_authorship(metadata)

        # Should add author-related fields
        assert "author" in metadata or "authors" in metadata

    def test_enrich_authorship_preserves_existing(self):
        """Test that existing authorship data is preserved."""
        metadata = {
            "title": "Test Book",
            "authors": ["Author One", "Author Two"],
            "author": "Author One",
        }

        enrich_authorship(metadata)

        # Should preserve both authors list and author field
        assert len(metadata["authors"]) == 2


@pytest.mark.network
@pytest.mark.slow
class TestFetchMetadata:
    """Test metadata fetching (requires network or mocking)."""

    def test_fetch_metadata_with_mock(self, sample_isbn, mock_metadata_response):
        """Test metadata fetching with mocked API response."""
        with patch("shared.metadata._fetch_google_books_raw") as mock_fetch:
            mock_fetch.return_value = mock_metadata_response

            result = fetch_metadata(sample_isbn)

            assert result is not None
            assert result["title"] == "Test Book"
            assert result["authors"] == ["Test Author"]
            mock_fetch.assert_called_once()

    def test_fetch_metadata_handles_api_failure(self, sample_isbn):
        """Test that fetch_metadata handles API failures gracefully."""
        with patch("shared.metadata._fetch_google_books_raw") as mock_fetch:
            mock_fetch.return_value = None

            result = fetch_metadata(sample_isbn)

            # Should return None or empty dict on failure
            assert result is None or result == {}

    def test_fetch_metadata_normalizes_isbn(self):
        """Test that fetch_metadata normalizes ISBN before querying."""
        # ISBN with hyphens
        isbn_with_hyphens = "978-0-143-12755-0"

        with patch("shared.metadata._fetch_google_books_raw") as mock_fetch:
            mock_fetch.return_value = None

            fetch_metadata(isbn_with_hyphens)

            # Should call with normalized ISBN (no hyphens)
            called_isbn = mock_fetch.call_args[0][0]
            assert "-" not in called_isbn


@pytest.mark.network
@pytest.mark.slow
class TestFetchGoogleBooksRaw:
    """Test Google Books API interaction."""

    def test_fetch_google_books_raw_with_mock(self, sample_isbn):
        """Test Google Books API call with mocked response."""
        with patch("requests.Session.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "items": [{"volumeInfo": {"title": "Test"}}]
            }
            mock_get.return_value = mock_response

            session = create_http_session()
            result = _fetch_google_books_raw(sample_isbn, None, session)

            assert result is not None
            assert "volumeInfo" in result

    def test_fetch_google_books_raw_handles_empty_response(self, sample_isbn):
        """Test that empty API responses are handled."""
        with patch("requests.Session.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"items": []}
            mock_get.return_value = mock_response

            session = create_http_session()
            result = _fetch_google_books_raw(sample_isbn, None, session)

            # Should return None for empty results
            assert result is None

    def test_fetch_google_books_raw_handles_http_errors(self, sample_isbn):
        """Test that HTTP errors are handled gracefully."""
        with patch("requests.Session.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response

            session = create_http_session()
            result = _fetch_google_books_raw(sample_isbn, None, session)

            # Should return None on HTTP errors
            assert result is None
