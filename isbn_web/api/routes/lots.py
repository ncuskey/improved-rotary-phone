"""API routes for lot management."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from isbn_lot_optimizer.service import BookService

from ..dependencies import get_book_service
from ...config import settings

router = APIRouter()
templates = Jinja2Templates(directory=str(settings.TEMPLATE_DIR))


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


@router.get("/{lot_id}", response_class=HTMLResponse)
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
