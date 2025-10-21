"""API routes for book management."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from isbn_lot_optimizer.service import BookService
from isbn_lot_optimizer.utils import normalise_isbn
from isbn_lot_optimizer.series_integration import enrich_evaluation_with_series, match_and_attach_series

from ..dependencies import get_book_service
from ...config import settings

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

    return result


@router.get("/all", response_class=JSONResponse)
async def get_all_books_json(
    service: BookService = Depends(get_book_service),
):
    """Return all books and their metadata as JSON."""

    evaluations = service.get_all_books()
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
        from isbn_lot_optimizer.probability import build_book_evaluation
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
