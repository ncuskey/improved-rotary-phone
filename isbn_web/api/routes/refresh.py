"""API routes for background data refresh and staleness checking."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from isbn_lot_optimizer.service import BookService
from ..dependencies import get_book_service

router = APIRouter()


class StalenessCheckRequest(BaseModel):
    """Request body for checking staleness of multiple books."""
    isbns: List[str]
    market_max_age_days: int = 7
    bookscouter_max_age_days: int = 14
    metadata_max_age_days: int = 90


class StalenessCheckResponse(BaseModel):
    """Response with fresh vs stale book ISBNs."""
    fresh: List[str]
    stale: List[str]
    stale_details: Dict[str, Dict[str, Any]]


class RefreshJobRequest(BaseModel):
    """Request body for triggering background refresh."""
    max_books: int = 100
    data_types: List[str] = ["market", "bookscouter"]  # What to refresh
    priority: str = "high_value"  # "high_value", "most_stale", "recent"


class RefreshJobResponse(BaseModel):
    """Response after queuing refresh job."""
    job_id: str
    queued_count: int
    message: str


@router.post("/check-staleness", response_model=StalenessCheckResponse)
async def check_book_staleness(
    request: StalenessCheckRequest,
    service: BookService = Depends(get_book_service),
) -> StalenessCheckResponse:
    """
    Check which books need data refresh based on staleness thresholds.

    Returns two lists:
    - fresh: Books with up-to-date data
    - stale: Books that need refresh
    """
    fresh = []
    stale = []
    stale_details = {}

    now = datetime.utcnow()
    market_threshold = now - timedelta(days=request.market_max_age_days)
    bookscouter_threshold = now - timedelta(days=request.bookscouter_max_age_days)
    metadata_threshold = now - timedelta(days=request.metadata_max_age_days)

    for isbn in request.isbns:
        row = service.db.fetch_book(isbn)
        if not row:
            stale.append(isbn)
            stale_details[isbn] = {
                "reason": "not_found",
                "market_is_stale": True,
                "bookscouter_is_stale": True,
                "metadata_is_stale": True,
            }
            continue

        # Check each data type's staleness
        is_stale = False
        details = {}

        # Market data staleness
        market_fetched = row.get("market_fetched_at")
        if market_fetched:
            market_date = datetime.fromisoformat(market_fetched.replace("Z", "+00:00"))
            market_is_stale = market_date < market_threshold
        else:
            market_is_stale = True

        details["market_is_stale"] = market_is_stale
        details["market_fetched_at"] = market_fetched
        if market_is_stale:
            is_stale = True

        # BookScouter data staleness
        bookscouter_fetched = row.get("bookscouter_fetched_at")
        if bookscouter_fetched:
            bookscouter_date = datetime.fromisoformat(bookscouter_fetched.replace("Z", "+00:00"))
            bookscouter_is_stale = bookscouter_date < bookscouter_threshold
        else:
            bookscouter_is_stale = True

        details["bookscouter_is_stale"] = bookscouter_is_stale
        details["bookscouter_fetched_at"] = bookscouter_fetched
        if bookscouter_is_stale:
            is_stale = True

        # Metadata staleness
        metadata_fetched = row.get("metadata_fetched_at")
        if metadata_fetched:
            metadata_date = datetime.fromisoformat(metadata_fetched.replace("Z", "+00:00"))
            metadata_is_stale = metadata_date < metadata_threshold
        else:
            metadata_is_stale = True

        details["metadata_is_stale"] = metadata_is_stale
        details["metadata_fetched_at"] = metadata_fetched

        if is_stale:
            stale.append(isbn)
            stale_details[isbn] = details
        else:
            fresh.append(isbn)

    return StalenessCheckResponse(
        fresh=fresh,
        stale=stale,
        stale_details=stale_details,
    )


@router.post("/refresh-stale-data", response_model=RefreshJobResponse)
async def trigger_stale_data_refresh(
    request: RefreshJobRequest,
    background_tasks: BackgroundTasks,
    service: BookService = Depends(get_book_service),
) -> RefreshJobResponse:
    """
    Trigger background refresh of stale data.

    Queues a background job to refresh data for books with stale information.
    Respects rate limits and prioritizes based on strategy.
    """
    # Get stale books based on data types requested
    stale_books = []

    if "market" in request.data_types:
        market_stale = service.db.fetch_books_needing_market_refresh(max_age_days=7)
        stale_books.extend(market_stale)

    if "bookscouter" in request.data_types:
        bookscouter_stale = service.db.fetch_books_needing_bookscouter_refresh(max_age_days=14)
        # Merge with existing list (avoid duplicates)
        existing_isbns = {book["isbn"] for book in stale_books}
        for book in bookscouter_stale:
            if book["isbn"] not in existing_isbns:
                stale_books.append(book)

    if "metadata" in request.data_types:
        metadata_stale = service.db.fetch_books_needing_metadata_refresh(max_age_days=90)
        existing_isbns = {book["isbn"] for book in stale_books}
        for book in metadata_stale:
            if book["isbn"] not in existing_isbns:
                stale_books.append(book)

    # Apply prioritization
    if request.priority == "high_value":
        # Sort by probability score (highest first)
        stale_books.sort(key=lambda b: b.get("probability_score") or 0, reverse=True)
    elif request.priority == "most_stale":
        # Sort by oldest updated_at
        stale_books.sort(key=lambda b: b.get("updated_at") or "1970-01-01")
    elif request.priority == "recent":
        # Sort by newest created_at
        stale_books.sort(key=lambda b: b.get("created_at") or "1970-01-01", reverse=True)

    # Limit to max_books
    books_to_refresh = stale_books[:request.max_books]

    # Generate job ID
    job_id = f"refresh_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    # Queue background task
    background_tasks.add_task(
        _refresh_books_background,
        service=service,
        books=books_to_refresh,
        data_types=request.data_types,
        job_id=job_id,
    )

    return RefreshJobResponse(
        job_id=job_id,
        queued_count=len(books_to_refresh),
        message=f"Queued {len(books_to_refresh)} books for refresh",
    )


async def _refresh_books_background(
    service: BookService,
    books: List[Dict[str, Any]],
    data_types: List[str],
    job_id: str,
) -> None:
    """
    Background task to refresh data for books.

    Respects rate limits and logs progress.
    """
    import logging
    import time

    logger = logging.getLogger(__name__)
    logger.info(f"Starting refresh job {job_id} for {len(books)} books")

    success_count = 0
    error_count = 0

    for idx, book in enumerate(books):
        isbn = book["isbn"]
        try:
            # Refresh the book (this will fetch fresh data from APIs)
            service.refresh_book_market(
                isbn,
                recalc_lots=False,  # Don't recalculate lots after each book
            )
            success_count += 1

            # Rate limiting: 1 request per second for eBay
            if "market" in data_types and idx < len(books) - 1:
                time.sleep(1.0)

        except Exception as e:
            logger.error(f"Failed to refresh {isbn}: {e}")
            error_count += 1

        # Log progress every 10 books
        if (idx + 1) % 10 == 0:
            logger.info(
                f"Refresh job {job_id} progress: {idx + 1}/{len(books)} "
                f"(success: {success_count}, errors: {error_count})"
            )

    # Recalculate lots once at the end if market data was refreshed
    if "market" in data_types and success_count > 0:
        try:
            service.recalculate_lots()
            logger.info(f"Recalculated lots after refresh job {job_id}")
        except Exception as e:
            logger.error(f"Failed to recalculate lots: {e}")

    logger.info(
        f"Refresh job {job_id} complete: "
        f"{success_count} successful, {error_count} errors"
    )


@router.get("/jobs/{job_id}")
async def get_refresh_job_status(job_id: str) -> Dict[str, Any]:
    """
    Get status of a refresh job.

    Note: This is a placeholder. For production, implement proper job tracking
    using Redis, Celery, or similar task queue.
    """
    # TODO: Implement proper job status tracking
    return {
        "job_id": job_id,
        "status": "running",
        "message": "Job status tracking not yet implemented. Check server logs.",
    }
