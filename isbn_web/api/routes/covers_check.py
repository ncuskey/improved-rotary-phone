"""API routes for checking and fixing missing book covers."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from isbn_lot_optimizer.service import BookService
from isbn_web.services.cover_cache import cover_cache
from ..dependencies import get_book_service

router = APIRouter()


class CoverStatsResponse(BaseModel):
    """Response with cover image statistics."""
    total_books: int
    with_covers: int
    without_covers: int
    coverage_percentage: float
    missing_isbns: List[str]


class CoverCheckRequest(BaseModel):
    """Request to check specific ISBNs for covers."""
    isbns: List[str]


class CoverCheckResponse(BaseModel):
    """Response with cover check results."""
    total_checked: int
    valid: int
    missing: int
    details: Dict[str, Dict[str, Any]]


class FixCoversRequest(BaseModel):
    """Request to fix missing covers."""
    isbns: List[str] = []  # Empty = fix all missing
    force_recheck: bool = False


class FixCoversResponse(BaseModel):
    """Response after fixing covers."""
    job_id: str
    books_queued: int
    message: str


@router.get("/stats", response_model=CoverStatsResponse)
async def get_cover_statistics(
    service: BookService = Depends(get_book_service),
) -> CoverStatsResponse:
    """
    Get statistics about book cover image coverage.

    Returns counts and percentages of books with/without covers,
    plus a list of ISBNs that are missing covers.
    """
    # Get counts from database
    stats = service.db.count_books_with_covers()

    # Get ISBNs of books missing covers
    missing_books = service.db.fetch_books_with_missing_covers()
    missing_isbns = [book["isbn"] for book in missing_books[:100]]  # Limit to 100

    return CoverStatsResponse(
        total_books=stats["total"],
        with_covers=stats["with_covers"],
        without_covers=stats["without_covers"],
        coverage_percentage=stats["coverage_percentage"],
        missing_isbns=missing_isbns,
    )


@router.post("/check", response_model=CoverCheckResponse)
async def check_cover_availability(
    request: CoverCheckRequest,
    service: BookService = Depends(get_book_service),
) -> CoverCheckResponse:
    """
    Check if cover images exist and are accessible for given ISBNs.

    This doesn't download the covers, just checks if URLs are valid
    and images are available.
    """
    import httpx
    import json

    results = {
        "total_checked": len(request.isbns),
        "valid": 0,
        "missing": 0,
        "details": {},
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        for isbn in request.isbns:
            # Get book from database
            row = service.db.fetch_book(isbn)
            if not row:
                results["missing"] += 1
                results["details"][isbn] = {
                    "status": "book_not_found",
                    "has_cover": False,
                }
                continue

            # Extract cover URL from metadata
            metadata_json = row.get("metadata_json")
            cover_url = None
            if metadata_json:
                try:
                    metadata = json.loads(metadata_json)
                    cover_url = metadata.get("cover_url") or metadata.get("thumbnail")
                except Exception:
                    pass

            if not cover_url:
                results["missing"] += 1
                results["details"][isbn] = {
                    "status": "no_cover_url",
                    "has_cover": False,
                }
                continue

            # Check if URL is accessible
            try:
                response = await client.head(cover_url, follow_redirects=True)
                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "")
                    if content_type.startswith("image/"):
                        results["valid"] += 1
                        results["details"][isbn] = {
                            "status": "valid",
                            "has_cover": True,
                            "cover_url": cover_url,
                            "content_type": content_type,
                        }
                    else:
                        results["missing"] += 1
                        results["details"][isbn] = {
                            "status": "not_an_image",
                            "has_cover": False,
                            "cover_url": cover_url,
                        }
                else:
                    results["missing"] += 1
                    results["details"][isbn] = {
                        "status": "http_error",
                        "has_cover": False,
                        "cover_url": cover_url,
                        "status_code": response.status_code,
                    }
            except Exception as e:
                results["missing"] += 1
                results["details"][isbn] = {
                    "status": "network_error",
                    "has_cover": False,
                    "cover_url": cover_url,
                    "error": str(e),
                }

    return CoverCheckResponse(**results)


@router.post("/fix", response_model=FixCoversResponse)
async def fix_missing_covers(
    request: FixCoversRequest,
    background_tasks: BackgroundTasks,
    service: BookService = Depends(get_book_service),
) -> FixCoversResponse:
    """
    Attempt to download and fix missing book covers.

    If no ISBNs provided, will fix all books with missing covers.
    This runs as a background task to avoid blocking.
    """
    from datetime import datetime

    # Determine which books to fix
    if request.isbns:
        # Fix specific ISBNs
        books_to_fix = [
            service.db.fetch_book(isbn) for isbn in request.isbns
            if service.db.fetch_book(isbn) is not None
        ]
    else:
        # Fix all books with missing covers
        books_to_fix = service.db.fetch_books_with_missing_covers()

    job_id = f"fix_covers_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    # Queue background task
    background_tasks.add_task(
        _fix_covers_background,
        service=service,
        books=books_to_fix,
        force_recheck=request.force_recheck,
        job_id=job_id,
    )

    return FixCoversResponse(
        job_id=job_id,
        books_queued=len(books_to_fix),
        message=f"Queued {len(books_to_fix)} books for cover fixing",
    )


async def _fix_covers_background(
    service: BookService,
    books: List[Dict[str, Any]],
    force_recheck: bool,
    job_id: str,
) -> None:
    """
    Background task to fix missing covers.

    Tries multiple sources to find working cover images.
    """
    import logging
    import json
    import httpx

    logger = logging.getLogger(__name__)
    logger.info(f"Starting cover fix job {job_id} for {len(books)} books")

    success_count = 0
    error_count = 0

    # Cover URL templates to try
    templates = [
        "https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg",
        "https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg",
    ]

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for idx, book in enumerate(books):
            isbn = book["isbn"]
            title = book.get("title") or isbn

            try:
                # Extract current metadata
                metadata_json = book.get("metadata_json")
                if metadata_json:
                    try:
                        metadata = json.loads(metadata_json)
                    except Exception:
                        metadata = {}
                else:
                    metadata = {}

                current_cover = metadata.get("cover_url") or metadata.get("thumbnail")

                # Skip if already has valid cover (unless force_recheck)
                if current_cover and not force_recheck:
                    continue

                # Try each template
                working_url = None
                for template in templates:
                    test_url = template.format(isbn=isbn)

                    try:
                        response = await client.head(test_url)
                        if response.status_code == 200:
                            content_type = response.headers.get("content-type", "")
                            if content_type.startswith("image/"):
                                working_url = test_url
                                break
                    except Exception:
                        continue

                if working_url:
                    # Update metadata with working URL
                    metadata["cover_url"] = working_url
                    metadata["thumbnail"] = working_url

                    # Update database
                    service.db.upsert_book({
                        "isbn": isbn,
                        "metadata_json": metadata,
                        # Include required fields
                        "title": book.get("title"),
                        "authors": book.get("authors"),
                        "publication_year": book.get("publication_year"),
                        "condition": book.get("condition") or "Good",
                        "estimated_price": book.get("estimated_price") or 0.0,
                        "probability_label": book.get("probability_label") or "Unknown",
                        "probability_score": book.get("probability_score") or 0.0,
                    })

                    success_count += 1
                    logger.info(f"✅ Fixed cover for: {title[:50]}")
                else:
                    error_count += 1
                    logger.warning(f"❌ No cover found for: {title[:50]}")

            except Exception as e:
                logger.error(f"Failed to fix cover for {isbn}: {e}")
                error_count += 1

            # Log progress every 10 books
            if (idx + 1) % 10 == 0:
                logger.info(
                    f"Cover fix job {job_id} progress: {idx + 1}/{len(books)} "
                    f"(success: {success_count}, errors: {error_count})"
                )

            # Rate limiting: be nice to OpenLibrary
            await asyncio.sleep(0.5)

    logger.info(
        f"Cover fix job {job_id} complete: "
        f"{success_count} successful, {error_count} errors"
    )


@router.get("/jobs/{job_id}")
async def get_cover_fix_job_status(job_id: str) -> Dict[str, Any]:
    """
    Get status of a cover fix job.

    Note: This is a placeholder. For production, implement proper job tracking.
    """
    return {
        "job_id": job_id,
        "status": "running",
        "message": "Job status tracking not yet implemented. Check server logs.",
    }
