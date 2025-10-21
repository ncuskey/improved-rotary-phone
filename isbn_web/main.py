"""FastAPI application entry point for ISBN Lot Optimizer web interface."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import sys

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response as FastAPIResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:  # Ensure package imports work when run as a script
    sys.path.insert(0, str(PROJECT_ROOT))

from isbn_web.api.dependencies import cleanup_book_service, get_book_service
from isbn_web.api.routes import actions, books, covers, covers_check, events, lots, refresh
from isbn_web.config import settings

if TYPE_CHECKING:  # pragma: no cover - import only for typing
    from isbn_lot_optimizer.service import BookService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup: ensure directories exist
    settings.COVER_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    yield

    # Shutdown: cleanup resources
    cleanup_book_service()


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Middleware to add cache-control headers to prevent browser caching during development."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Add no-cache headers for HTML and API responses
        if isinstance(response, Response):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


class NoCacheStaticFiles(StaticFiles):
    """StaticFiles subclass that adds no-cache headers to all responses."""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        # Force no caching for all static files
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


# Initialize FastAPI app
app = FastAPI(
    title="ISBN Lot Optimizer",
    description="Web interface for cataloguing books and generating profitable eBay lots",
    version="1.0.0",
    lifespan=lifespan,
)

# Add no-cache middleware to prevent browser caching issues
app.add_middleware(NoCacheMiddleware)

# Mount static files with no-cache headers
app.mount("/static", NoCacheStaticFiles(directory=str(settings.STATIC_DIR)), name="static")

# Mount cover cache for serving images (covers can be cached since they rarely change)
if settings.COVER_CACHE_DIR.exists():
    app.mount("/covers", StaticFiles(directory=str(settings.COVER_CACHE_DIR)), name="covers")

# Include API routes
app.include_router(books.router, prefix="/api/books", tags=["books"])
app.include_router(lots.router, prefix="/api/lots", tags=["lots"])
app.include_router(actions.router, prefix="/api/actions", tags=["actions"])
app.include_router(events.router, prefix="/api/events", tags=["events"])
app.include_router(covers.router, prefix="/api", tags=["covers"])
app.include_router(covers_check.router, prefix="/api/covers", tags=["covers"])
app.include_router(refresh.router, prefix="/api/refresh", tags=["refresh"])

# Setup Jinja2 templates
templates = Jinja2Templates(directory=str(settings.TEMPLATE_DIR))


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": "ISBN Lot Optimizer",
        },
    )


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy"}


class ISBNRequest(BaseModel):
    """Schema for incoming ISBN lookup requests."""

    isbn: str
    condition: str | None = None
    edition: str | None = None
    cover_type: str | None = None
    printing: str | None = None
    signed: bool | None = None


@app.post("/isbn")
async def isbn_lookup(
    data: ISBNRequest,
    service: "BookService" = Depends(get_book_service),
):
    """Return core book metadata for a supplied ISBN."""

    book = service.get_book(data.isbn)

    if book is None:
        try:
            book = service.scan_isbn(
                raw_isbn=data.isbn,
                condition=data.condition or "Good",
                edition=data.edition,
                include_market=True,  # Fetch market data for mobile triage
                recalc_lots=False,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch metadata for ISBN {data.isbn.strip() or data.isbn}",
            ) from exc

    # Update attributes if provided (even if book already exists)
    if data.cover_type or data.printing or data.signed is not None:
        update_fields = {}
        if data.cover_type:
            update_fields["cover_type"] = data.cover_type
        if data.printing:
            update_fields["printing"] = data.printing
        if data.signed is not None:
            update_fields["signed"] = 1 if data.signed else 0
        if update_fields:
            try:
                service.update_book_fields(data.isbn, update_fields)
                book = service.get_book(data.isbn)  # Refresh
            except Exception:
                pass  # Don't fail if attributes update fails

    metadata = book.metadata

    authors = list(metadata.authors) if metadata.authors else []
    if not authors and metadata.canonical_author:
        authors.append(metadata.canonical_author)

    response_payload = {
        "title": metadata.title or "",
        "subtitle": metadata.subtitle,
        "author": authors[0] if authors else None,
        "authors": authors or None,
        "isbn": book.isbn,
        "published_year": metadata.published_year,
        "page_count": metadata.page_count,
        "description": metadata.description,
        "thumbnail": metadata.thumbnail,
        "info_link": metadata.info_link,
        "categories": list(metadata.categories) or None,
    }

    # Remove keys with None values for a cleaner response
    return {key: value for key, value in response_payload.items() if value is not None}
