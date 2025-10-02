"""API routes for book management."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from isbn_lot_optimizer.service import BookService
from isbn_lot_optimizer.utils import normalise_isbn

from ..dependencies import get_book_service
from ...config import settings

router = APIRouter()
templates = Jinja2Templates(directory=str(settings.TEMPLATE_DIR))


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
    service: BookService = Depends(get_book_service),
):
    """
    List all books with optional search filter.

    Returns the book table HTML partial.
    """
    if search:
        # Search by ISBN, title, or author
        books = service.search_books(search)
    else:
        books = service.list_books()

    return templates.TemplateResponse(
        "components/book_table.html",
        {"request": request, "books": books},
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
