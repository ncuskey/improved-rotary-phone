"""Cover image caching service."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

import httpx

from ..config import settings
from shared.database import DatabaseManager


class CoverCacheService:
    """Service for caching book cover images."""

    def __init__(self, cache_dir: Path = settings.COVER_CACHE_DIR):
        """Initialize the cover cache service.

        Args:
            cache_dir: Directory to store cached covers
        """
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, isbn: str, size: str = "L") -> Path:
        """Get the cache file path for an ISBN.

        Args:
            isbn: Book ISBN
            size: Cover size (S, M, L) - defaults to L for largest quality

        Returns:
            Path to the cached cover file
        """
        # Use hash to create a flat directory structure
        filename = f"{isbn}_{size}.jpg"
        return self.cache_dir / filename

    async def get_cover(self, isbn: str, size: str = "L") -> Optional[bytes]:
        """Get a cover image, from cache or by downloading.

        Args:
            isbn: Book ISBN
            size: Cover size (S, M, L) - defaults to L for largest quality

        Returns:
            Cover image bytes, or None if not available
        """
        cache_path = self._get_cache_path(isbn, size)

        # Check cache first
        if cache_path.exists():
            return cache_path.read_bytes()

        # Try to get cover URL from database metadata first
        cover_url = None
        try:
            db = DatabaseManager(settings.DATABASE_PATH)
            book = db.fetch_book(isbn)
            if book and book["metadata_json"]:
                metadata = json.loads(book["metadata_json"])
                # Check both cover_url and thumbnail fields
                cover_url = metadata.get("cover_url") or metadata.get("thumbnail")

                # If we have a cover URL, adjust size if needed
                if cover_url and "openlibrary.org" in cover_url:
                    # Replace size suffix if present
                    cover_url = cover_url.replace("-S.jpg", f"-{size}.jpg")
                    cover_url = cover_url.replace("-M.jpg", f"-{size}.jpg")
                    cover_url = cover_url.replace("-L.jpg", f"-{size}.jpg")
        except Exception as e:
            # Log but don't fail - we'll fall back to Open Library
            print(f"Error checking database for cover: {e}")

        # If no URL from database, use Open Library default
        if not cover_url:
            cover_url = f"https://covers.openlibrary.org/b/isbn/{isbn}-{size}.jpg"

        # Download the cover
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(cover_url)
                if response.status_code == 200 and len(response.content) > 1000:  # Ensure it's not a placeholder
                    # Save to cache
                    cache_path.write_bytes(response.content)
                    return response.content
        except Exception as e:
            print(f"Error downloading cover from {cover_url}: {e}")

        return None

    def clear_cache(self) -> int:
        """Clear all cached covers.

        Returns:
            Number of files deleted
        """
        count = 0
        for cache_file in self.cache_dir.glob("*.jpg"):
            cache_file.unlink()
            count += 1
        return count


# Global instance
cover_cache = CoverCacheService()
