"""API routes for book cover images."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ...services.cover_cache import cover_cache

router = APIRouter()


@router.get("/covers/{isbn}")
async def get_cover(isbn: str, size: str = "M"):
    """Get a book cover image.

    Args:
        isbn: Book ISBN
        size: Cover size (S, M, L), defaults to M

    Returns:
        JPEG image
    """
    # Validate size parameter
    if size not in ("S", "M", "L"):
        raise HTTPException(status_code=400, detail="Size must be S, M, or L")

    # Get cover from cache or download
    cover_bytes = await cover_cache.get_cover(isbn, size)

    if cover_bytes is None:
        raise HTTPException(status_code=404, detail="Cover not found")

    return Response(content=cover_bytes, media_type="image/jpeg")
