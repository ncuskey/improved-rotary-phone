"""API routes for lot management."""
from __future__ import annotations

from typing import List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from shared.models import LotSuggestion
from isbn_lot_optimizer.service import BookService

from ..dependencies import get_book_service
from ...config import settings
from .books import _book_evaluation_to_dict

router = APIRouter()
templates = Jinja2Templates(directory=str(settings.TEMPLATE_DIR))


class LotPriceEstimateRequest(BaseModel):
    """Request body for lot price estimation."""
    series_id: int
    series_title: str
    lot_size: int
    is_complete_set: bool = False
    condition: str = "https://schema.org/UsedCondition"
    is_sold: bool = False
    price_per_book: float = 0.0
    inferred_series_size: int = None


class LotPriceEstimateResponse(BaseModel):
    """Response body for lot price estimation."""
    estimated_price: float
    price_per_book: float
    completion_pct: float
    is_near_complete: bool
    model_version: str
    model_mae: float
    model_r2: float


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

    # Convert lots to serializable dictionaries for Alpine.js
    lots_data = [_lot_suggestion_to_dict(lot) for lot in lots]

    # Prepare response with lot count update script
    response_html = templates.TemplateResponse(
        "components/lots_table.html",
        {"request": request, "lots": lots_data},
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

    # Convert lots to serializable dictionaries for Alpine.js
    lots_data = [_lot_suggestion_to_dict(lot) for lot in lots]

    # Prepare response with lot count update script
    response_html = templates.TemplateResponse(
        "components/lots_table.html",
        {"request": request, "lots": lots_data},
    )

    # Add HTMX trigger to update lot count
    lot_count = len(lots)
    response_html.headers["HX-Trigger-After-Swap"] = f'{{"updateLotCount": {{"count": {lot_count}}}}}'

    return response_html


@router.post("/regenerate.json", response_class=JSONResponse)
async def regenerate_lots_json(
    service: BookService = Depends(get_book_service),
):
    """
    Regenerate lot suggestions and return them as JSON.

    This triggers a full recalculation of lots with the latest data,
    including lot market pricing integration.
    """
    # Recalculate lots (includes lot pricing integration)
    lots = service.recompute_lots()

    return [_lot_suggestion_to_dict(lot) for lot in lots]


@router.get("/all", response_class=JSONResponse)
@router.get("/all.json", response_class=JSONResponse)
@router.get("/list", response_class=JSONResponse)
@router.get("/list.json", response_class=JSONResponse)
async def get_all_lots_json(
    service: BookService = Depends(get_book_service),
):
    """
    Return persisted lot suggestions as JSON.

    Filters out lots where:
    - Books have been deleted from catalog
    - Books have status != 'ACCEPT'
    - Fewer than 2 accepted books remain
    """
    lots = service.list_lots()
    valid_lots = []

    for lot in lots:
        # Get ISBNs for this lot
        isbns = list(lot.book_isbns) if hasattr(lot, 'book_isbns') else []

        if not isbns:
            continue

        # Query database directly to check status for each ISBN
        accepted_isbns = []
        for isbn in isbns:
            row = service.db.fetch_book(isbn)
            if row:
                # Check status column (default to 'ACCEPT' for backward compatibility)
                status = row.get('status', 'ACCEPT')
                if status == 'ACCEPT':
                    accepted_isbns.append(isbn)

        # Only include lots with 2+ accepted books
        if len(accepted_isbns) >= 2:
            # Get full book evaluations for accepted books only
            accepted_books = []
            for isbn in accepted_isbns:
                row = service.db.fetch_book(isbn)
                if row:
                    accepted_books.append(service._row_to_evaluation(row))

            # Attach accepted books to lot for serialization
            lot.books = tuple(accepted_books)
            valid_lots.append(lot)

    return [_lot_suggestion_to_dict(lot) for lot in valid_lots]


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

    # Convert books to serializable format for Alpine.js/carousel
    books_data = []
    for book in books:
        book_data = {
            "isbn": book.isbn,
            "condition": book.condition,
            "estimated_price": book.estimated_price,
            "metadata": {
                "title": book.metadata.title if book.metadata else "Unknown Title",
                "authors": list(book.metadata.authors) if book.metadata and book.metadata.authors else [],
                "published_year": book.metadata.published_year if book.metadata else None,
                "series_name": book.metadata.series_name if book.metadata else None,
            } if book.metadata else None
        }
        books_data.append(book_data)

    return templates.TemplateResponse(
        "components/lot_detail.html",
        {"request": request, "lot": lot, "books": books_data},
    )


@router.get("/{lot_id:int}/carousel", response_class=HTMLResponse)
async def get_lot_carousel(
    request: Request,
    lot_id: int,
    service: BookService = Depends(get_book_service),
):
    """
    Get the carousel HTML for a specific lot.

    Returns only the carousel partial (no lot details).
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
            "components/lot_carousel.html",
            {"request": request, "books": [], "error": "Lot not found"},
        )

    # Get books in this lot
    books = service.get_books_for_lot(lot)

    # Convert books to serializable format for carousel
    books_data = []
    for book in books:
        book_data = {
            "isbn": book.isbn,
            "condition": book.condition,
            "estimated_price": book.estimated_price,
            "metadata": {
                "title": book.metadata.title if book.metadata else "Unknown Title",
                "authors": list(book.metadata.authors) if book.metadata and book.metadata.authors else [],
                "published_year": book.metadata.published_year if book.metadata else None,
                "series_name": book.metadata.series_name if book.metadata else None,
            } if book.metadata else None
        }
        books_data.append(book_data)

    return templates.TemplateResponse(
        "components/lot_carousel.html",
        {"request": request, "books": books_data},
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


@router.post("/estimate_price", response_class=JSONResponse)
async def estimate_lot_price(
    request_body: LotPriceEstimateRequest,
) -> LotPriceEstimateResponse:
    """
    Estimate lot price using the trained lot specialist model.

    Uses the lot model to predict the total price based on:
    - Lot size and series information
    - Completion percentage (relative to inferred series size)
    - Condition and other attributes
    - Individual book pricing if available

    Returns:
        LotPriceEstimateResponse with predicted price and metadata
    """
    import joblib
    import numpy as np
    import json
    from pathlib import Path

    try:
        # Load the lot model
        model_dir = Path(__file__).parent.parent.parent.parent / 'isbn_lot_optimizer' / 'models' / 'stacking'
        model_path = model_dir / 'lot_model.pkl'
        scaler_path = model_dir / 'lot_scaler.pkl'
        metadata_path = model_dir / 'lot_metadata.json'

        if not model_path.exists():
            return JSONResponse(
                status_code=503,
                content={"error": "Lot prediction model not found"}
            )

        model = joblib.load(model_path)
        scaler = joblib.load(scaler_path)

        with open(metadata_path, 'r') as f:
            model_metadata = json.load(f)

        # Calculate inferred series size (use provided or lot_size as fallback)
        inferred_series_size = request_body.inferred_series_size or request_body.lot_size
        completion_pct = request_body.lot_size / inferred_series_size if inferred_series_size > 0 else 0

        # Condition mapping
        condition_map = {
            'https://schema.org/NewCondition': 1.0,
            'https://schema.org/UsedCondition': 0.6,
            'https://schema.org/RefurbishedCondition': 0.8,
            'https://schema.org/DamagedCondition': 0.3,
        }
        condition_value = condition_map.get(request_body.condition, 0.5)

        # Build feature vector (must match training order)
        features = [
            request_body.lot_size,  # lot_size
            1 if request_body.is_complete_set else 0,  # is_complete_set
            1 if request_body.is_sold else 0,  # is_sold
            request_body.price_per_book,  # price_per_book
            condition_value,  # condition_score
            1 if request_body.lot_size <= 3 else 0,  # is_small_lot
            1 if 4 <= request_body.lot_size <= 7 else 0,  # is_medium_lot
            1 if 8 <= request_body.lot_size <= 12 else 0,  # is_large_lot
            1 if request_body.lot_size > 12 else 0,  # is_very_large_lot
            request_body.series_id,  # series_id
        ]

        # Scale features
        X = np.array([features])
        X_scaled = scaler.transform(X)

        # Predict
        predicted_price = float(model.predict(X_scaled)[0])

        # Calculate price per book from prediction
        price_per_book = predicted_price / request_body.lot_size if request_body.lot_size > 0 else 0

        return LotPriceEstimateResponse(
            estimated_price=round(predicted_price, 2),
            price_per_book=round(price_per_book, 2),
            completion_pct=round(completion_pct, 3),
            is_near_complete=(completion_pct >= 0.9),
            model_version=model_metadata.get('trained_at', 'unknown'),
            model_mae=round(model_metadata.get('test_mae', 0), 2),
            model_r2=round(model_metadata.get('test_r2', 0), 3),
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to estimate lot price: {str(e)}"}
        )
