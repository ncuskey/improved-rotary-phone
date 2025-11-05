"""API routes for book management."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from isbn_lot_optimizer.service import BookService
from shared.metadata import fetch_metadata, create_http_session
from shared.utils import normalise_isbn
from shared.series_integration import enrich_evaluation_with_series, match_and_attach_series

from ..dependencies import get_book_service
from ...config import settings
from .sphere_viz import viz_broadcaster

router = APIRouter()
templates = Jinja2Templates(directory=str(settings.TEMPLATE_DIR))


@router.get("/stats")
async def get_database_statistics(
    service: BookService = Depends(get_book_service),
) -> JSONResponse:
    """
    Get comprehensive database statistics.

    Returns metrics including:
    - Database file size
    - Book counts and coverage
    - Storage breakdown per API source
    - Probability distribution
    - Price statistics
    - Data freshness timestamps
    """
    try:
        stats = service.get_database_statistics()
        return JSONResponse(content=stats)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "message": "Failed to retrieve statistics"}
        )


def _book_evaluation_to_dict(evaluation) -> Dict[str, Any]:
    """Serialize a BookEvaluation into JSON-friendly dict."""
    metadata = evaluation.metadata
    metadata_dict: Dict[str, Any] | None = None
    if metadata:
        metadata_dict = asdict(metadata)
        metadata_dict.pop("raw", None)
        # Convert tuple fields to lists for JSON compatibility
        for key in ("authors", "credited_authors", "categories", "identifiers"):
            value = metadata_dict.get(key)
            if isinstance(value, tuple):
                metadata_dict[key] = list(value)

    result: Dict[str, Any] = {
        "isbn": evaluation.isbn,
        "original_isbn": evaluation.original_isbn,
        "condition": evaluation.condition,
        "edition": evaluation.edition,
        "quantity": evaluation.quantity,
        "estimated_price": evaluation.estimated_price,
        "probability_score": evaluation.probability_score,
        "probability_label": evaluation.probability_label,
        "justification": list(evaluation.justification) if evaluation.justification else [],
        "metadata": metadata_dict,
    }

    if evaluation.market:
        market = asdict(evaluation.market)
        market.pop("raw_active", None)
        market.pop("raw_sold", None)
        result["market"] = market

    if evaluation.booksrun:
        booksrun = asdict(evaluation.booksrun)
        booksrun.pop("raw", None)
        result["booksrun"] = booksrun
        result["booksrun_value_label"] = evaluation.booksrun_value_label
        result["booksrun_value_ratio"] = evaluation.booksrun_value_ratio

    if evaluation.bookscouter:
        bookscouter = asdict(evaluation.bookscouter)
        bookscouter.pop("raw", None)
        # Convert offers list to dict format
        if "offers" in bookscouter:
            bookscouter["offers"] = [
                asdict(offer) if hasattr(offer, "__dict__") else offer
                for offer in bookscouter["offers"]
            ]
        result["bookscouter"] = bookscouter
        result["bookscouter_value_label"] = evaluation.bookscouter_value_label
        result["bookscouter_value_ratio"] = evaluation.bookscouter_value_ratio

    if evaluation.rarity is not None:
        result["rarity"] = evaluation.rarity

    def _format_timestamp(value: Any) -> str:
        try:
            if isinstance(value, (int, float)):
                return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
            if isinstance(value, str) and value.isdigit():
                return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
            return str(value)
        except Exception:
            return str(value)

    updated_at = getattr(evaluation, "updated_at", None)
    if updated_at is not None:
        result["updated_at"] = _format_timestamp(updated_at)

    created_at = getattr(evaluation, "created_at", None)
    if created_at is not None:
        result["created_at"] = _format_timestamp(created_at)

    return result


@router.get("/all", response_class=JSONResponse)
async def get_all_books_json(
    since: Optional[str] = None,
    service: BookService = Depends(get_book_service),
):
    """
    Return all books and their metadata as JSON.

    Query parameters:
    - since: Optional ISO 8601 timestamp. If provided, only returns books updated after this time.
    """

    if since:
        evaluations = service.get_books_updated_since(since)
    else:
        evaluations = service.get_all_books()

    # Broadcast DB read event
    try:
        await viz_broadcaster.database_read("get_all_books", len(evaluations))
    except Exception:
        pass  # Don't fail request if broadcast fails

    payload = [_book_evaluation_to_dict(evaluation) for evaluation in evaluations]
    return payload


@router.post("/scan", response_class=HTMLResponse)
async def scan_book(
    request: Request,
    response: Response,
    isbn: str = Form(...),
    condition: str = Form("Good"),
    edition: str = Form(""),
    service: BookService = Depends(get_book_service),
):
    """
    Scan a single ISBN and add it to the database.

    Returns the updated book table HTML.
    """
    # Normalize ISBN
    normalized_isbn = normalise_isbn(isbn)

    if not normalized_isbn:
        response.headers["X-Success-Message"] = f"Invalid ISBN: {isbn}"
        # Return current books table
        books = service.list_books()
        return templates.TemplateResponse(
            "components/book_table.html",
            {"request": request, "books": books},
        )

    # Scan the book (adds to DB, fetches metadata, runs market lookup)
    try:
        evaluation = service.scan_isbn(
            raw_isbn=normalized_isbn,
            condition=condition,
            edition=edition or None,
        )

        # Try to match the book to a series (non-blocking)
        try:
            db_path = Path(service.db.db_path)
            series_match = match_and_attach_series(evaluation, db_path, auto_save=True)
            if series_match:
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Matched {normalized_isbn} to series: {series_match['series_title']}")
        except Exception as e:
            # Don't fail the scan if series matching fails
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to match series for {normalized_isbn}: {e}")

        # Set success message header
        response.headers["X-Success-Message"] = f"Added: {evaluation.title or normalized_isbn}"

        # Return updated books list
        books = service.list_books()
        return templates.TemplateResponse(
            "components/book_table.html",
            {"request": request, "books": books, "selected_isbn": normalized_isbn},
        )

    except Exception as e:
        response.headers["X-Success-Message"] = f"Error scanning {normalized_isbn}: {str(e)}"
        books = service.list_books()
        return templates.TemplateResponse(
            "components/book_table.html",
            {"request": request, "books": books},
        )


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def list_books(
    request: Request,
    search: Optional[str] = None,
    selected_isbn: Optional[str] = None,
    service: BookService = Depends(get_book_service),
):
    """
    List all books with optional search filter.

    Returns the book table HTML partial.
    """
    # Handle empty string as None
    normalized_selected = normalise_isbn(selected_isbn) if selected_isbn and selected_isbn.strip() else None

    if search:
        # Search by ISBN, title, or author
        books = service.search_books(search)
    else:
        books = service.list_books()

    return templates.TemplateResponse(
        "components/book_table.html",
        {
            "request": request,
            "books": books,
            "selected_isbn": normalized_selected,
        },
    )


@router.get("/{isbn}/evaluate")
async def get_book_evaluation_json(
    isbn: str,
    condition: Optional[str] = None,
    edition: Optional[str] = None,
    service: BookService = Depends(get_book_service),
) -> JSONResponse:
    """
    Get full evaluation data for a book as JSON (mobile-friendly endpoint).

    Returns complete triage information including:
    - Probability score and label
    - Estimated resale price
    - Justification/reasoning
    - BookScouter offers
    - Amazon sales rank
    - Rarity score
    - Series information
    - Market data (eBay comps)

    If condition or edition are provided, re-calculates evaluation with those attributes.
    """
    normalized_isbn = normalise_isbn(isbn)

    if not normalized_isbn:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid ISBN", "isbn": isbn}
        )

    book = service.get_book(normalized_isbn)

    # Broadcast DB read event
    try:
        await viz_broadcaster.database_read("get_book_evaluation", 1)
    except Exception:
        pass

    if not book:
        return JSONResponse(
            status_code=404,
            content={"error": "Book not found", "isbn": normalized_isbn}
        )

    # Debug: print parameters received
    print(f"DEBUG: Received params - condition={condition!r}, edition={edition!r}")
    print(f"DEBUG: Book from DB - condition={book.condition!r}, edition={book.edition!r}")

    # If condition or edition are provided, rebuild evaluation with new attributes
    if condition is not None or edition is not None:
        from shared.probability import build_book_evaluation
        import logging
        logger = logging.getLogger(__name__)

        # Use provided values or fallback to existing
        eval_condition = condition if condition is not None else book.condition
        eval_edition = edition if edition is not None else book.edition

        logger.info(f"Re-evaluating {normalized_isbn}: condition={eval_condition}, edition={eval_edition}")

        # Get Amazon rank from existing evaluation
        amazon_rank = None
        if book.bookscouter and hasattr(book.bookscouter, 'amazon_sales_rank'):
            amazon_rank = book.bookscouter.amazon_sales_rank

        # Preserve bookscouter and booksrun data before rebuilding
        bookscouter_data = book.bookscouter
        booksrun_data = book.booksrun

        # Broadcast ML prediction event
        try:
            await viz_broadcaster.ml_prediction("re_evaluation", 1)
        except Exception:
            pass

        # Rebuild evaluation with new attributes
        book = build_book_evaluation(
            isbn=book.isbn,
            original_isbn=book.original_isbn,
            metadata=book.metadata,
            market=book.market,
            condition=eval_condition,
            edition=eval_edition,
            amazon_rank=amazon_rank,
        )

        print(f"DEBUG: After rebuild - book.condition={book.condition!r}, book.edition={book.edition!r}")
        logger.info(f"After rebuild: book.condition={book.condition}, book.edition={book.edition}")

        # Restore bookscouter and booksrun data
        book.bookscouter = bookscouter_data
        book.booksrun = booksrun_data

    result_dict = _book_evaluation_to_dict(book)
    print(f"DEBUG: Result dict - condition={result_dict.get('condition')!r}, edition={result_dict.get('edition')!r}")
    return JSONResponse(content=result_dict)


@router.get("/{isbn}/price-variants")
async def get_price_variants(
    isbn: str,
    condition: Optional[str] = None,
    service: BookService = Depends(get_book_service),
) -> JSONResponse:
    """
    Get price variants for different conditions and special features.

    This endpoint analyzes sold comps to show how price varies based on:
    - Different conditions (New, Like New, Very Good, Good, Acceptable)
    - Special features (Signed, First Edition, Dust Jacket, etc.)

    Uses real market data when available (sample_size >= 2), falls back to
    estimated multipliers when data is sparse.

    Returns:
        {
            "base_price": float,
            "current_condition": str,
            "current_price": float,
            "condition_variants": [...],  # Sorted by price (highest first)
            "feature_variants": [...]     # Sorted by value add (highest first)
        }
    """
    from shared.probability import calculate_price_variants

    normalized_isbn = normalise_isbn(isbn)

    if not normalized_isbn:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid ISBN", "isbn": isbn}
        )

    book = service.get_book(normalized_isbn)

    if not book:
        return JSONResponse(
            status_code=404,
            content={"error": "Book not found", "isbn": normalized_isbn}
        )

    # Use provided condition or book's current condition
    eval_condition = condition if condition is not None else book.condition

    # Calculate price variants
    variants = calculate_price_variants(
        metadata=book.metadata,
        market=book.market,
        current_condition=eval_condition,
        current_price=book.estimated_price,
        bookscouter=book.bookscouter,
    )

    return JSONResponse(content=variants)


@router.get("/{isbn}/sold-statistics")
async def get_sold_statistics(
    isbn: str,
    service: BookService = Depends(get_book_service),
) -> JSONResponse:
    """
    Get detailed sold listings statistics including demand signals and platform breakdown.

    Leverages enriched sold listings data (96.2% coverage) to provide:
    - Demand signal (count × avg_price)
    - Platform distribution (eBay, Amazon, Mercari percentages)
    - Signed/unsigned detection
    - Price distribution metrics
    - Data quality indicators

    Returns:
        {
            "demand_signal": float,
            "platform_breakdown": {
                "ebay_pct": float,
                "amazon_pct": float,
                "mercari_pct": float
            },
            "features": {
                "signed_pct": float,
                "hardcover_pct": float,
                "avg_price": float,
                "price_range": float
            },
            "data_quality": {
                "total_count": int,
                "single_sales_count": int,
                "lot_sales_count": int,
                "data_completeness": float
            }
        }
    """
    from shared.sold_features import extract_sold_ml_features

    normalized_isbn = normalise_isbn(isbn)

    if not normalized_isbn:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid ISBN", "isbn": isbn}
        )

    # Extract sold listings features
    features = extract_sold_ml_features(normalized_isbn)

    # Calculate demand signal (count × avg_price)
    demand_signal = None
    if features.get('sold_sales_count') and features.get('sold_avg_price'):
        demand_signal = features['sold_sales_count'] * features['sold_avg_price']

    # Calculate platform breakdown percentages
    total_count = features.get('sold_sales_count', 0)
    platform_breakdown = {
        "ebay_pct": 0.0,
        "amazon_pct": 0.0,
        "mercari_pct": 0.0
    }

    if total_count > 0:
        ebay_count = features.get('sold_ebay_count', 0)
        amazon_count = features.get('sold_amazon_count', 0)
        mercari_count = features.get('sold_mercari_count', 0)

        platform_breakdown = {
            "ebay_pct": (ebay_count / total_count * 100) if ebay_count else 0.0,
            "amazon_pct": (amazon_count / total_count * 100) if amazon_count else 0.0,
            "mercari_pct": (mercari_count / total_count * 100) if mercari_count else 0.0
        }

    # Calculate price range
    price_range = None
    if features.get('sold_max_price') and features.get('sold_min_price'):
        price_range = features['sold_max_price'] - features['sold_min_price']

    # Build response
    result = {
        "demand_signal": demand_signal,
        "platform_breakdown": platform_breakdown,
        "features": {
            "signed_pct": features.get('sold_signed_pct'),
            "hardcover_pct": features.get('sold_hardcover_pct'),
            "avg_price": features.get('sold_avg_price'),
            "price_range": price_range
        },
        "data_quality": {
            "total_count": total_count,
            "single_sales_count": features.get('sold_single_sales_count', 0),
            "lot_sales_count": features.get('sold_lot_sales_count', 0),
            "data_completeness": features.get('sold_data_completeness', 0.0)
        }
    }

    return JSONResponse(content=result)


@router.post("/{isbn}/accept")
async def accept_book(
    isbn: str,
    background_tasks: BackgroundTasks,
    condition: Optional[str] = None,
    edition: Optional[str] = None,
    service: BookService = Depends(get_book_service),
) -> JSONResponse:
    """
    Accept a book and add it to inventory.

    This endpoint explicitly adds the book to the database inventory.
    Books should only be added when the user accepts them (taps "Accept" button),
    not automatically when scanned.

    Lot regeneration runs in the background to avoid blocking other requests.

    Args:
        isbn: The ISBN to accept
        condition: Book condition (default: "Good")
        edition: Edition notes (optional)

    Returns:
        JSON with the accepted book's full evaluation data
    """
    normalized_isbn = normalise_isbn(isbn)

    if not normalized_isbn:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid ISBN", "isbn": isbn}
        )

    try:
        # Accept book WITHOUT lot regeneration (returns immediately)
        book = service.accept_book(
            normalized_isbn,
            condition=condition or "Good",
            edition=edition,
            recalc_lots=False,  # Don't block - regenerate in background
        )

        # Broadcast DB write event
        try:
            await viz_broadcaster.database_write("accept_book", 1)
        except Exception:
            pass  # Don't fail request if broadcast fails

        # Schedule INCREMENTAL lot update in background (only updates affected lots)
        # This is much faster than full regeneration: 1-3 eBay calls instead of 122
        background_tasks.add_task(service.update_lots_for_isbn, normalized_isbn)

        result_dict = _book_evaluation_to_dict(book)
        return JSONResponse(
            status_code=200,
            content={"success": True, "book": result_dict}
        )

    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "message": f"Failed to accept book {normalized_isbn}"}
        )


@router.post("/{isbn}/refresh", response_class=HTMLResponse)
async def refresh_book_data(
    request: Request,
    isbn: str,
    service: BookService = Depends(get_book_service),
):
    """
    Refresh book data by re-fetching from external APIs (eBay, BookScouter, etc.).

    This forces a fresh scan which updates:
    - eBay market data (sold comps)
    - BookScouter buyback offers
    - BooksRun data
    - Metadata if needed

    Returns the updated book detail HTML partial.
    """
    normalized_isbn = normalise_isbn(isbn)

    if not normalized_isbn:
        return templates.TemplateResponse(
            "components/book_detail.html",
            {"request": request, "book": None, "error": "Invalid ISBN"},
        )

    try:
        # Use refresh_book_market to update market data from eBay, BookScouter, etc.
        # This method fetches fresh data and persists it to the database
        book = service.refresh_book_market(
            normalized_isbn,
            recalc_lots=False,  # Don't recalculate lots on refresh
        )

        if not book:
            # Book doesn't exist in database, scan it fresh
            book = service.scan_isbn(
                normalized_isbn,
                condition="Good",
                edition=None,
                include_market=True,
                recalc_lots=False,
            )
        else:
            # Reload from database to get the persisted v2_stats (sold_comps) data
            # refresh_book_market persists the data but doesn't return the complete object
            book = service.get_book(normalized_isbn)

        return templates.TemplateResponse(
            "components/book_detail.html",
            {"request": request, "book": book},
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to refresh book data for {normalized_isbn}: {e}")
        return templates.TemplateResponse(
            "components/book_detail.html",
            {"request": request, "book": None, "error": f"Failed to refresh data: {str(e)}"},
        )


@router.get("/{isbn}", response_class=HTMLResponse)
async def get_book_detail(
    request: Request,
    isbn: str,
    service: BookService = Depends(get_book_service),
):
    """
    Get detailed information about a single book.

    Returns the book detail HTML partial.
    """
    normalized_isbn = normalise_isbn(isbn)

    if not normalized_isbn:
        return templates.TemplateResponse(
            "components/book_detail.html",
            {"request": request, "book": None, "error": "Invalid ISBN"},
        )

    book = service.get_book(normalized_isbn)

    # Enrich with series information if available
    if book:
        try:
            db_path = Path(service.db.db_path)
            book = enrich_evaluation_with_series(book, db_path)
        except Exception as e:
            # Log but don't fail if series enrichment fails
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to enrich book with series: {e}")

    return templates.TemplateResponse(
        "components/book_detail.html",
        {"request": request, "book": book},
    )


@router.patch("/{isbn}")
async def update_book(
    isbn: str,
    request: Request,
    condition: Optional[str] = Form(None),
    edition: Optional[str] = Form(None),
    service: BookService = Depends(get_book_service),
):
    """Update a book's fields."""
    normalized_isbn = normalise_isbn(isbn)

    if not normalized_isbn:
        return JSONResponse({"error": "Invalid ISBN"}, status_code=400)

    fields = {}
    if condition is not None:
        fields["condition"] = condition
    if edition is not None:
        fields["edition"] = edition

    try:
        service.update_book_fields(normalized_isbn, fields)
        return JSONResponse({"message": "Book updated successfully"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.delete("/{isbn}/json")
async def delete_book_json(
    isbn: str,
    service: BookService = Depends(get_book_service),
) -> JSONResponse:
    """Delete a single book (JSON response for mobile)."""
    normalized_isbn = normalise_isbn(isbn)

    if not normalized_isbn:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid ISBN", "isbn": isbn}
        )

    try:
        service.delete_books([normalized_isbn])
        return JSONResponse(content={"message": "Book deleted", "isbn": normalized_isbn})
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "isbn": normalized_isbn}
        )


@router.delete("/{isbn}", response_class=HTMLResponse)
async def delete_book(
    isbn: str,
    request: Request,
    response: Response,
    service: BookService = Depends(get_book_service),
):
    """Delete a single book and return updated table."""
    normalized_isbn = normalise_isbn(isbn)

    if not normalized_isbn:
        books = service.list_books()
        return templates.TemplateResponse(
            "components/book_table.html",
            {"request": request, "books": books},
        )

    # Delete the book
    service.delete_books([normalized_isbn])

    # Set success message
    response.headers["X-Success-Message"] = f"Deleted book: {normalized_isbn}"

    # Return updated book list
    books = service.list_books()
    return templates.TemplateResponse(
        "components/book_table.html",
        {"request": request, "books": books},
    )


@router.post("/bulk-delete", response_class=HTMLResponse)
async def bulk_delete_books(
    request: Request,
    response: Response,
    isbns: str = Form(...),  # Comma-separated ISBNs
    service: BookService = Depends(get_book_service),
):
    """Delete multiple books."""
    isbn_list = [normalise_isbn(isbn.strip()) for isbn in isbns.split(",")]
    isbn_list = [isbn for isbn in isbn_list if isbn]  # Filter out invalid

    if not isbn_list:
        books = service.list_books()
        return templates.TemplateResponse(
            "components/book_table.html",
            {"request": request, "books": books},
        )

    # Delete books
    count = service.delete_books(isbn_list)

    response.headers["X-Success-Message"] = f"Deleted {count} books"

    # Return updated list
    books = service.list_books()
    return templates.TemplateResponse(
        "components/book_table.html",
        {"request": request, "books": books},
    )


class MetadataSearchRequest(BaseModel):
    """Schema for metadata search by title/author."""
    title: str
    author: Optional[str] = None
    publication_year: Optional[int] = None
    edition: Optional[str] = None


class MetadataSearchResult(BaseModel):
    """A single search result with metadata and reference links."""
    isbn_13: Optional[str]
    isbn_10: Optional[str]
    title: str
    subtitle: Optional[str]
    authors: List[str]
    publisher: Optional[str]
    publication_year: Optional[int]
    cover_url: Optional[str]
    description: Optional[str]
    categories: List[str]
    series_name: Optional[str]
    series_index: Optional[int]
    source: str
    ebay_search_url: str
    google_search_url: str


@router.post("/search-metadata")
async def search_metadata(
    data: MetadataSearchRequest,
) -> JSONResponse:
    """
    Search for book metadata by title and author.

    This endpoint helps users find ISBNs for books without barcodes by:
    1. Searching Google Books API by title + author
    2. Returning matching results with ISBNs and metadata
    3. Providing reference links to eBay and Google for manual research

    Returns a list of candidates with:
    - ISBN (if found)
    - Full metadata (title, author, year, cover, etc.)
    - eBay search link for manual price research
    - Google search link for additional information
    """
    import requests

    # Build Google Books search query
    query_parts = []
    if data.title:
        query_parts.append(f'intitle:"{data.title}"')
    if data.author:
        query_parts.append(f'inauthor:"{data.author}"')

    query = " ".join(query_parts)

    if not query:
        return JSONResponse(
            status_code=400,
            content={"error": "Must provide at least title or author"}
        )

    # Fetch from Google Books API
    GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
    params = {
        "q": query,
        "maxResults": "10",
        "printType": "books",
        "fields": (
            "items(volumeInfo/title,volumeInfo/subtitle,volumeInfo/authors,"
            "volumeInfo/publisher,volumeInfo/publishedDate,volumeInfo/pageCount,"
            "volumeInfo/categories,volumeInfo/industryIdentifiers,"
            "volumeInfo/imageLinks/thumbnail,volumeInfo/description)"
        ),
    }

    import os
    api_key = os.getenv("GOOGLE_BOOKS_API_KEY")
    if api_key:
        params["key"] = api_key

    try:
        response = requests.get(GOOGLE_BOOKS_URL, params=params, timeout=15)
        response.raise_for_status()
        payload = response.json() or {}
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"error": f"Failed to search Google Books: {str(e)}"}
        )

    items = payload.get("items") or []
    results = []

    for item in items:
        info = item.get("volumeInfo")
        if not isinstance(info, dict):
            continue

        # Extract ISBNs
        identifiers = info.get("industryIdentifiers") or []
        isbn_10 = None
        isbn_13 = None
        for ident in identifiers:
            if not isinstance(ident, dict):
                continue
            if ident.get("type") == "ISBN_10" and ident.get("identifier"):
                isbn_10 = ident["identifier"].replace("-", "")
            if ident.get("type") == "ISBN_13" and ident.get("identifier"):
                isbn_13 = ident["identifier"].replace("-", "")

        # Skip results without ISBN
        if not isbn_10 and not isbn_13:
            continue

        # Extract metadata
        title = info.get("title") or ""
        subtitle = info.get("subtitle")
        authors = [str(a) for a in info.get("authors", []) if a]
        publisher = info.get("publisher")

        published_date = (info.get("publishedDate") or "").strip()
        import re
        match = re.match(r"^(\d{4})", published_date)
        publication_year = int(match.group(1)) if match else None

        categories = [str(cat) for cat in info.get("categories", []) if cat]

        image_links = info.get("imageLinks") or {}
        cover_url = image_links.get("thumbnail") or image_links.get("smallThumbnail")
        if isinstance(cover_url, str) and cover_url.startswith("http://"):
            cover_url = "https://" + cover_url[7:]

        description = info.get("description")

        # Extract series info from title (Google Books pattern)
        combined_title = " ".join(filter(None, [title, subtitle]))
        series_name = None
        series_index = None
        paren_match = re.search(r"\(([^()]+?),\s*#?(\d+)\)", combined_title)
        if paren_match:
            series_name = paren_match.group(1).strip()
            try:
                series_index = int(paren_match.group(2))
            except ValueError:
                pass

        # Build search query for reference links
        search_query = title
        if authors:
            search_query += f" {authors[0]}"
        if data.edition:
            search_query += f" {data.edition}"

        # eBay search URL (books category, sorted by sold listings)
        ebay_query = quote_plus(search_query)
        ebay_url = (
            f"https://www.ebay.com/sch/i.html?_nkw={ebay_query}"
            f"&_sacat=267&LH_Sold=1&LH_Complete=1&_sop=13"
        )

        # Google search URL
        google_query = quote_plus(f"{search_query} book value price")
        google_url = f"https://www.google.com/search?q={google_query}"

        results.append({
            "isbn_13": isbn_13,
            "isbn_10": isbn_10,
            "title": title,
            "subtitle": subtitle,
            "authors": authors,
            "publisher": publisher,
            "publication_year": publication_year,
            "cover_url": cover_url,
            "description": description,
            "categories": categories,
            "series_name": series_name,
            "series_index": series_index,
            "source": "google_books",
            "ebay_search_url": ebay_url,
            "google_search_url": google_url,
        })

    return JSONResponse(content={"results": results, "total": len(results)})


class ScanDecisionRequest(BaseModel):
    """Schema for logging a scan decision."""
    isbn: str
    decision: str  # ACCEPT, REJECT, SKIP, etc.
    location_name: Optional[str] = None
    location_address: Optional[str] = None
    location_latitude: Optional[float] = None
    location_longitude: Optional[float] = None
    location_accuracy: Optional[float] = None
    device_id: Optional[str] = None
    app_version: Optional[str] = None
    notes: Optional[str] = None


@router.post("/log-scan")
async def log_scan_decision(
    data: ScanDecisionRequest,
    service: BookService = Depends(get_book_service),
) -> JSONResponse:
    """
    Log a scan decision (ACCEPT, REJECT, SKIP, etc.) to scan history.

    This endpoint allows the iOS app and other clients to log all scan decisions,
    including rejected books, with optional location data.

    The scan will be logged even if the book doesn't exist in the catalog yet
    (useful for logging rejects before full evaluation).
    """
    normalized_isbn = normalise_isbn(data.isbn)
    if not normalized_isbn:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid ISBN", "isbn": data.isbn}
        )

    # Try to get existing book evaluation for richer data
    book = service.get_book(normalized_isbn)

    if book:
        # Log with full book evaluation data
        scan_id = service.log_scan(
            evaluation=book,
            decision=data.decision,
            location_name=data.location_name,
            location_address=data.location_address,
            location_latitude=data.location_latitude,
            location_longitude=data.location_longitude,
            location_accuracy=data.location_accuracy,
            device_id=data.device_id,
            app_version=data.app_version,
            notes=data.notes,
        )
    else:
        # Book not in catalog yet - log with minimal data
        scan_id = service.db.log_scan(
            isbn=normalized_isbn,
            decision=data.decision,
            location_name=data.location_name,
            location_address=data.location_address,
            location_latitude=data.location_latitude,
            location_longitude=data.location_longitude,
            location_accuracy=data.location_accuracy,
            device_id=data.device_id,
            app_version=data.app_version,
            notes=data.notes,
        )

    return JSONResponse(content={
        "success": True,
        "scan_id": scan_id,
        "isbn": normalized_isbn,
        "decision": data.decision
    })


@router.get("/scan-history")
async def get_scan_history(
    limit: int = 100,
    isbn: Optional[str] = None,
    location_name: Optional[str] = None,
    decision: Optional[str] = None,
    service: BookService = Depends(get_book_service),
) -> JSONResponse:
    """
    Get scan history with optional filters.

    Query parameters:
    - limit: Maximum number of scans to return (default 100)
    - isbn: Filter by ISBN
    - location_name: Filter by location name
    - decision: Filter by decision (ACCEPT, REJECT, SKIP, etc.)
    """
    scans = service.db.get_scan_history(
        limit=limit,
        isbn=normalise_isbn(isbn) if isbn else None,
        location_name=location_name,
        decision=decision,
    )

    return JSONResponse(content={
        "scans": [dict(scan) for scan in scans],
        "total": len(scans)
    })


@router.get("/scan-locations")
async def get_scan_locations(
    service: BookService = Depends(get_book_service),
) -> JSONResponse:
    """
    Get summary of all scan locations with acceptance rates.

    Returns location names, scan counts, acceptance rates, and last visit dates.
    """
    locations = service.db.get_scan_locations()

    return JSONResponse(content={
        "locations": locations,
        "total": len(locations)
    })


@router.get("/scan-stats")
async def get_scan_stats(
    service: BookService = Depends(get_book_service),
) -> JSONResponse:
    """
    Get overall scan statistics.

    Returns total scans, unique books, acceptance rates, date ranges, etc.
    """
    stats = service.db.get_scan_stats()

    return JSONResponse(content=stats)


class EstimatePriceRequest(BaseModel):
    """Request body for dynamic price estimation."""
    condition: str = "Good"
    is_hardcover: Optional[bool] = None
    is_paperback: Optional[bool] = None
    is_mass_market: Optional[bool] = None
    is_signed: Optional[bool] = None
    is_first_edition: Optional[bool] = None


class AttributeDelta(BaseModel):
    """Price change for a single attribute."""
    attribute: str
    label: str
    delta: float  # Price change (positive or negative)
    enabled: bool  # Whether this attribute is currently enabled


class EstimatePriceResponse(BaseModel):
    """Response with dynamic price estimate and deltas."""
    estimated_price: float
    baseline_price: float  # Price with no attributes
    confidence: float
    deltas: List[AttributeDelta]
    model_version: str


@router.post("/{isbn}/estimate_price")
async def estimate_price_with_attributes(
    isbn: str,
    request_body: EstimatePriceRequest,
    service: BookService = Depends(get_book_service),
) -> JSONResponse:
    """
    Estimate book price with user-specified attributes.

    Calculates baseline price (no attributes) and delta for each attribute
    to show how each one affects the estimate.

    Args:
        isbn: Book ISBN
        request_body: Condition and attribute flags

    Returns:
        EstimatePriceResponse with price estimate and attribute deltas
    """
    from isbn_lot_optimizer.ml import get_ml_estimator
    from copy import deepcopy

    normalized_isbn = normalise_isbn(isbn)
    if not normalized_isbn:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid ISBN"}
        )

    # Get book from database (returns BookEvaluation with parsed objects)
    book = service.get_book(normalized_isbn)
    if not book:
        return JSONResponse(
            status_code=404,
            content={"error": "Book not found"}
        )

    # Get ML estimator
    estimator = get_ml_estimator()
    if not estimator.is_ready():
        return JSONResponse(
            status_code=503,
            content={"error": "ML model not available"}
        )

    # Use parsed objects from BookEvaluation
    metadata = book.metadata
    market = book.market
    bookscouter = book.bookscouter

    # Calculate baseline price (no attributes)
    baseline_metadata = deepcopy(metadata) if metadata else None
    if baseline_metadata:
        baseline_metadata.cover_type = None
        baseline_metadata.signed = False
        baseline_metadata.printing = None

    baseline_estimate = estimator.estimate_price(
        baseline_metadata,
        market,
        bookscouter,
        request_body.condition
    )
    baseline_price = baseline_estimate.price or 10.0

    # Calculate price with user-selected attributes
    final_metadata = deepcopy(metadata) if metadata else None
    if final_metadata:
        # Apply user selections
        if request_body.is_hardcover:
            final_metadata.cover_type = "Hardcover"
        elif request_body.is_paperback:
            final_metadata.cover_type = "Paperback"
        elif request_body.is_mass_market:
            final_metadata.cover_type = "Mass Market"
        else:
            final_metadata.cover_type = None

        final_metadata.signed = request_body.is_signed or False
        final_metadata.printing = "1st" if request_body.is_first_edition else None

    final_estimate = estimator.estimate_price(
        final_metadata,
        market,
        bookscouter,
        request_body.condition
    )
    final_price = final_estimate.price or baseline_price

    # Calculate deltas for each attribute
    deltas = []

    # Hardcover delta
    if request_body.is_hardcover or request_body.is_paperback or request_body.is_mass_market:
        # Calculate price without format
        no_format_metadata = deepcopy(final_metadata) if final_metadata else None
        if no_format_metadata:
            no_format_metadata.cover_type = None
        no_format_estimate = estimator.estimate_price(no_format_metadata, market, bookscouter, request_body.condition)
        no_format_price = no_format_estimate.price or baseline_price

        if request_body.is_hardcover:
            deltas.append(AttributeDelta(
                attribute="is_hardcover",
                label="Hardcover",
                delta=round(final_price - no_format_price, 2),
                enabled=True
            ))
        elif request_body.is_paperback:
            deltas.append(AttributeDelta(
                attribute="is_paperback",
                label="Paperback",
                delta=round(final_price - no_format_price, 2),
                enabled=True
            ))
        elif request_body.is_mass_market:
            deltas.append(AttributeDelta(
                attribute="is_mass_market",
                label="Mass Market",
                delta=round(final_price - no_format_price, 2),
                enabled=True
            ))

    # Signed delta
    if request_body.is_signed:
        no_signed_metadata = deepcopy(final_metadata) if final_metadata else None
        if no_signed_metadata:
            no_signed_metadata.signed = False
        no_signed_estimate = estimator.estimate_price(no_signed_metadata, market, bookscouter, request_body.condition)
        no_signed_price = no_signed_estimate.price or baseline_price

        deltas.append(AttributeDelta(
            attribute="is_signed",
            label="Signed/Autographed",
            delta=round(final_price - no_signed_price, 2),
            enabled=True
        ))

    # First edition delta
    if request_body.is_first_edition:
        no_first_metadata = deepcopy(final_metadata) if final_metadata else None
        if no_first_metadata:
            no_first_metadata.printing = None
        no_first_estimate = estimator.estimate_price(no_first_metadata, market, bookscouter, request_body.condition)
        no_first_price = no_first_estimate.price or baseline_price

        deltas.append(AttributeDelta(
            attribute="is_first_edition",
            label="First Edition",
            delta=round(final_price - no_first_price, 2),
            enabled=True
        ))

    response = EstimatePriceResponse(
        estimated_price=round(final_price, 2),
        baseline_price=round(baseline_price, 2),
        confidence=final_estimate.confidence,
        deltas=deltas,
        model_version=final_estimate.model_version
    )

    return JSONResponse(content=response.dict())


class UpdateAttributesRequest(BaseModel):
    """Request body for saving user-selected attributes."""
    cover_type: Optional[str] = None  # "Hardcover", "Paperback", "Mass Market", or null
    signed: bool = False
    printing: Optional[str] = None  # "1st" for first edition, or null


@router.put("/{isbn}/attributes")
async def update_book_attributes(
    isbn: str,
    request_body: UpdateAttributesRequest,
    service: BookService = Depends(get_book_service),
) -> JSONResponse:
    """
    Save user-selected book attributes to database.

    Updates cover_type, signed, and printing fields based on user selections
    from the book detail page.

    Args:
        isbn: Book ISBN
        request_body: Attribute values to save

    Returns:
        Success message with updated attributes
    """
    normalized_isbn = normalise_isbn(isbn)
    if not normalized_isbn:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid ISBN"}
        )

    # Update attributes in database
    try:
        service.db.update_book_attributes(
            normalized_isbn,
            cover_type=request_body.cover_type,
            signed=request_body.signed,
            printing=request_body.printing
        )

        return JSONResponse(content={
            "success": True,
            "isbn": normalized_isbn,
            "attributes": {
                "cover_type": request_body.cover_type,
                "signed": request_body.signed,
                "printing": request_body.printing
            }
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to update attributes: {str(e)}"}
        )
