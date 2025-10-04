"""API routes for lot management."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from isbn_lot_optimizer.models import LotSuggestion
from isbn_lot_optimizer.service import BookService

from ..dependencies import get_book_service
from ...config import settings
from .books import _book_evaluation_to_dict

router = APIRouter()
templates = Jinja2Templates(directory=str(settings.TEMPLATE_DIR))


def _lot_suggestion_to_dict(lot: LotSuggestion) -> dict:
    """Serialize a LotSuggestion for API responses."""

    payload = {
        "name": lot.name,
        "strategy": lot.strategy,
        "book_isbns": list(lot.book_isbns),
        "estimated_value": lot.estimated_value,
        "probability_score": lot.probability_score,
        "probability_label": lot.probability_label,
        "sell_through": lot.sell_through,
        "justification": list(lot.justification),
        "display_author_label": lot.display_author_label,
        "canonical_author": lot.canonical_author,
        "canonical_series": lot.canonical_series,
        "series_name": lot.series_name,
    }

    lot_id = getattr(lot, "id", None)
    if lot_id is not None:
        payload["id"] = lot_id

    if getattr(lot, "books", None):
        payload["books"] = [_book_evaluation_to_dict(book) for book in lot.books]

    market_blob = getattr(lot, "market_json", None)
    if market_blob:
        payload["market_json"] = market_blob

    return payload


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def list_lots(
    request: Request,
    service: BookService = Depends(get_book_service),
):
    """
    List all lot suggestions.

    Returns the lots table HTML partial.
    """
    lots = service.list_lots()

    # Prepare response with lot count update script
    response_html = templates.TemplateResponse(
        "components/lots_table.html",
        {"request": request, "lots": lots},
    )
    
    # Add HTMX trigger to update lot count
    lot_count = len(lots)
    response_html.headers["HX-Trigger-After-Swap"] = f'{{"updateLotCount": {{"count": {lot_count}}}}}'
    
    return response_html


@router.post("/regenerate", response_class=HTMLResponse)
async def regenerate_lots(
    request: Request,
    service: BookService = Depends(get_book_service),
):
    """
    Regenerate lot suggestions based on current books.

    Returns the updated lots table HTML.
    """
    # Regenerate lots
    lots = service.recompute_lots()

    # Prepare response with lot count update script
    response_html = templates.TemplateResponse(
        "components/lots_table.html",
        {"request": request, "lots": lots},
    )
    
    # Add HTMX trigger to update lot count
    lot_count = len(lots)
    response_html.headers["HX-Trigger-After-Swap"] = f'{{"updateLotCount": {{"count": {lot_count}}}}}'
    
    return response_html


@router.get("/all", response_class=JSONResponse)
@router.get("/all.json", response_class=JSONResponse)
@router.get("/list", response_class=JSONResponse)
@router.get("/list.json", response_class=JSONResponse)
async def get_all_lots_json(
    service: BookService = Depends(get_book_service),
):
    """Return persisted lot suggestions as JSON."""

    lots = service.list_lots()
    return [_lot_suggestion_to_dict(lot) for lot in lots]


@router.get("/{lot_id:int}", response_class=HTMLResponse)
async def get_lot_detail(
    request: Request,
    lot_id: int,
    service: BookService = Depends(get_book_service),
):
    """
    Get detailed information about a specific lot.

    Returns the lot detail HTML partial.
    """
    lots = service.list_lots()

    # Find the lot by ID
    lot = None
    for l in lots:
        if l.id == lot_id:
            lot = l
            break

    if not lot:
        return templates.TemplateResponse(
            "components/lot_detail.html",
            {"request": request, "lot": None, "books": [], "error": "Lot not found"},
        )

    # Get books in this lot
    books = service.get_books_for_lot(lot)

    return templates.TemplateResponse(
        "components/lot_detail.html",
        {"request": request, "lot": lot, "books": books},
    )


@router.get("/{lot_id:int}/details", response_class=HTMLResponse)
async def get_lot_details_page(
    request: Request,
    lot_id: int,
    service: BookService = Depends(get_book_service),
):
    """
    Get the full lot details page with 3D carousel.

    Returns the complete lot details page.
    """
    lots = service.list_lots()

    # Find the lot by ID
    lot = None
    for l in lots:
        if l.id == lot_id:
            lot = l
            break

    if not lot:
        return templates.TemplateResponse(
            "lot_details.html",
            {"request": request, "lot": None, "books": [], "error": "Lot not found"},
        )

    # Get books in this lot
    books = service.get_books_for_lot(lot)

    # Convert books to serializable format for Alpine.js
    books_data = []
    for book in books:
        book_data = {
            "isbn": book.isbn,
            "condition": book.condition,
            "estimated_price": book.estimated_price,
            "metadata": {
                "title": book.metadata.title,
                "authors": list(book.metadata.authors) if book.metadata.authors else [],
                "published_year": book.metadata.published_year,
                "series_name": book.metadata.series_name,
            }
        }
        books_data.append(book_data)

    # Calculate lot statistics
    total_books = len(books)
    total_value = sum(b.estimated_price or 0 for b in books)
    average_price = total_value / total_books if total_books > 0 else 0
    estimated_profit = total_value * 0.8  # Assume 20% fees
    profit_margin = (estimated_profit / total_value * 100) if total_value > 0 else 0

    lot_stats = {
        "total_books": total_books,
        "total_value": total_value,
        "average_price": average_price,
        "estimated_profit": estimated_profit,
        "profit_margin": profit_margin,
    }

    return templates.TemplateResponse(
        "lot_details.html",
        {"request": request, "lot": lot, "books": books, "books_data": books_data, "stats": lot_stats},
    )


@router.get("/{lot_id:int}/edit", response_class=HTMLResponse)
async def get_lot_edit_form(
    request: Request,
    lot_id: int,
    service: BookService = Depends(get_book_service),
):
    """
    Get the lot edit form.

    Returns the edit form HTML partial.
    """
    lots = service.list_lots()
    lot = None
    for l in lots:
        if l.id == lot_id:
            lot = l
            break

    if not lot:
        return templates.TemplateResponse(
            "components/lot_edit_form.html",
            {"request": request, "lot": None, "error": "Lot not found"},
        )

    return templates.TemplateResponse(
        "components/lot_edit_form.html",
        {"request": request, "lot": lot},
    )


@router.put("/{lot_id:int}", response_class=HTMLResponse)
async def update_lot(
    request: Request,
    lot_id: int,
    service: BookService = Depends(get_book_service),
):
    """
    Update a lot's details.

    Returns the updated lot details page.
    """
    # Get form data from request
    form_data = await request.form()
    
    lots = service.list_lots()
    lot = None
    for l in lots:
        if l.id == lot_id:
            lot = l
            break

    if not lot:
        return templates.TemplateResponse(
            "lot_details.html",
            {"request": request, "lot": None, "books": [], "error": "Lot not found"},
        )

    # Update lot properties (in a real implementation, you'd update the database)
    lot.name = form_data.get("name", lot.name)
    lot.strategy = form_data.get("strategy", lot.strategy)
    lot.estimated_value = float(form_data.get("estimated_value", lot.estimated_value or 0))
    lot.probability_score = float(form_data.get("probability_score", lot.probability_score or 0))
    lot.probability_label = form_data.get("probability_label", lot.probability_label)
    lot.sell_through = float(form_data.get("sell_through", lot.sell_through or 0)) if form_data.get("sell_through") else lot.sell_through
    
    justification_text = form_data.get("justification", "")
    if justification_text:
        lot.justification = [line.strip() for line in justification_text.split('\n') if line.strip()]

    # Get books in this lot
    books = service.get_books_for_lot(lot)

    # Calculate lot statistics
    total_books = len(books)
    total_value = sum(b.estimated_price or 0 for b in books)
    average_price = total_value / total_books if total_books > 0 else 0
    estimated_profit = total_value * 0.8  # Assume 20% fees
    profit_margin = (estimated_profit / total_value * 100) if total_value > 0 else 0

    lot_stats = {
        "total_books": total_books,
        "total_value": total_value,
        "average_price": average_price,
        "estimated_profit": estimated_profit,
        "profit_margin": profit_margin,
    }

    return templates.TemplateResponse(
        "lot_details.html",
        {"request": request, "lot": lot, "books": books, "stats": lot_stats},
    )


@router.delete("/{lot_id:int}/book/{book_id}", response_class=HTMLResponse)
async def remove_book_from_lot(
    request: Request,
    lot_id: int,
    book_id: str,
    service: BookService = Depends(get_book_service),
):
    """
    Remove a book from a lot.

    Returns the updated carousel HTML partial.
    """
    # This would need to be implemented in the service
    # For now, return a placeholder response
    lots = service.list_lots()
    lot = None
    for l in lots:
        if l.id == lot_id:
            lot = l
            break

    if not lot:
        return templates.TemplateResponse(
            "components/carousel.html",
            {"request": request, "books": [], "error": "Lot not found"},
        )

    # Get updated books list (in a real implementation, you'd remove the book)
    books = service.get_books_for_lot(lot)
    # Filter out the removed book
    books = [b for b in books if b.isbn != book_id]

    return templates.TemplateResponse(
        "components/carousel.html",
        {"request": request, "books": books},
    )
