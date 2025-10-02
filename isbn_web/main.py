"""FastAPI application entry point for ISBN Lot Optimizer web interface."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .api.dependencies import cleanup_book_service
from .api.routes import books, lots, actions, events
from .config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup: ensure directories exist
    settings.COVER_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    yield

    # Shutdown: cleanup resources
    cleanup_book_service()


# Initialize FastAPI app
app = FastAPI(
    title="ISBN Lot Optimizer",
    description="Web interface for cataloguing books and generating profitable eBay lots",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")

# Mount cover cache for serving images
if settings.COVER_CACHE_DIR.exists():
    app.mount("/covers", StaticFiles(directory=str(settings.COVER_CACHE_DIR)), name="covers")

# Include API routes
app.include_router(books.router, prefix="/api/books", tags=["books"])
app.include_router(lots.router, prefix="/api/lots", tags=["lots"])
app.include_router(actions.router, prefix="/api/actions", tags=["actions"])
app.include_router(events.router, prefix="/api/events", tags=["events"])

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
