"""Cover image caching service."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import httpx

from ..config import settings


class CoverCacheService:
    """Service for caching book cover images."""

    def __init__(self, cache_dir: Path = settings.COVER_CACHE_DIR):
        """Initialize the cover cache service.

        Args:
            cache_dir: Directory to store cached covers
        """
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, isbn: str, size: str = "M") -> Path:
        """Get the cache file path for an ISBN.

        Args:
            isbn: Book ISBN
            size: Cover size (S, M, L)

        Returns:
            Path to the cached cover file
        """
        # Use hash to create a flat directory structure
        filename = f"{isbn}_{size}.jpg"
        return self.cache_dir / filename

    async def get_cover(self, isbn: str, size: str = "M") -> Optional[bytes]:
        """Get a cover image, from cache or by downloading.

        Args:
            isbn: Book ISBN
            size: Cover size (S, M, L)

        Returns:
            Cover image bytes, or None if not available
        """
        cache_path = self._get_cache_path(isbn, size)

        # Check cache first
        if cache_path.exists():
            return cache_path.read_bytes()

        # Download from OpenLibrary
        url = f"https://covers.openlibrary.org/b/isbn/{isbn}-{size}.jpg"
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(url)
                if response.status_code == 200 and len(response.content) > 0:
                    # Save to cache
                    cache_path.write_bytes(response.content)
                    return response.content
        except Exception:
            pass

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
