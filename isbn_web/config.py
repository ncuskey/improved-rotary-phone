"""Configuration management for ISBN web application."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_PATH: Path = Path.home() / ".isbn_lot_optimizer" / "catalog.db"

    # eBay API
    EBAY_APP_ID: Optional[str] = os.getenv("EBAY_APP_ID")
    EBAY_CLIENT_ID: Optional[str] = os.getenv("EBAY_CLIENT_ID")
    EBAY_CLIENT_SECRET: Optional[str] = os.getenv("EBAY_CLIENT_SECRET")
    EBAY_MARKETPLACE: str = os.getenv("EBAY_MARKETPLACE", "EBAY_US")
    EBAY_GLOBAL_ID: str = "EBAY-US"
    EBAY_DELAY: float = float(os.getenv("EBAY_DELAY", "1.0"))
    EBAY_ENTRIES: int = int(os.getenv("EBAY_ENTRIES", "20"))

    # BooksRun API
    BOOKSRUN_KEY: Optional[str] = os.getenv("BOOKSRUN_KEY")
    BOOKSRUN_AFFILIATE_ID: Optional[str] = os.getenv("BOOKSRUN_AFFILIATE_ID")
    BOOKSRUN_BASE_URL: Optional[str] = os.getenv("BOOKSRUN_BASE_URL")
    BOOKSRUN_TIMEOUT: Optional[float] = (
        float(os.getenv("BOOKSRUN_TIMEOUT")) if os.getenv("BOOKSRUN_TIMEOUT") else None
    )

    # Hardcover API
    HARDCOVER_API_TOKEN: Optional[str] = os.getenv("HARDCOVER_API_TOKEN")

    # Metadata
    METADATA_DELAY: float = float(os.getenv("METADATA_DELAY", "0.0"))

    # Web Server
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

    # Paths
    COVER_CACHE_DIR: Path = Path.home() / ".isbn_lot_optimizer" / "covers"
    TEMPLATE_DIR: Path = Path(__file__).parent / "templates"
    STATIC_DIR: Path = Path(__file__).parent / "static"


settings = Settings()
